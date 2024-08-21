from datetime import datetime, timedelta
from urllib import request
from fastapi import APIRouter, Form, HTTPException, Path, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import mercadopago as mp
import os

from dtos.alterar_cliente_dto import AlterarClienteDTO
from dtos.alterar_senha_dto import AlterarSenhaDTO
from models.cliente_model import Cliente
from models.item_pedido_model import ItemPedido
from models.pedido_model import EstadoPedido, Pedido
from repositories.cliente_repo import ClienteRepo
from repositories.item_pedido_repo import ItemPedidoRepo
from repositories.pedido_repo import PedidoRepo
from repositories.produto_repo import ProdutoRepo
from util.auth import conferir_senha, obter_hash_senha
from util.cookies import (
    adicionar_mensagem_alerta,
    adicionar_mensagem_erro,
    adicionar_mensagem_sucesso,
    excluir_cookie_auth,
)
from util.templates import obter_jinja_templates

router = APIRouter(prefix="/cliente")
templates = obter_jinja_templates("templates/cliente")


@router.get("/pedidos") 
async def get_pedidos(request: Request, periodo : str = Query("todos")): 
    data_inicial = datetime(1900,1,1) 
    data_final = datetime.now()
    match periodo:
        case "30":
            data_inicial = data_final - timedelta(days=30)
        case "60":
            data_inicial = data_final - timedelta(days=60)        
        case "90":
            data_inicial = data_final - timedelta(days=90)      
    pedidos = PedidoRepo.obter_por_periodo(request.state.cliente.id, data_inicial, data_final) 
    return templates.TemplateResponse( 
        "pages/pedidos.html", 
        {"request": request, "pedidos": pedidos}, 
    )


@router.get("/cadastro")
async def get_cadastro(request: Request):
    return templates.TemplateResponse(
        "pages/cadastro.html",
        {
            "request": request,
        },
    )


@router.post("/post_cadastro", response_class=JSONResponse)
async def post_cadastro(request: Request, alterar_dto: AlterarClienteDTO):
    id = request.state.cliente.id
    cliente_data = alterar_dto.model_dump()
    response = JSONResponse({"redirect": {"url": "/cliente/cadastro"}})
    if ClienteRepo.alterar(Cliente(id, **cliente_data)):
        adicionar_mensagem_sucesso(response, "Cadastro alterado com sucesso!")
    else:
        adicionar_mensagem_erro(
            response, "Não foi possível alterar os dados cadastrais!"
        )
    return response


@router.get("/senha")
async def get_senha(request: Request):
    return templates.TemplateResponse(
        "pages/senha.html",
        {"request": request},
    )


@router.post("/post_senha", response_class=JSONResponse)
async def post_senha(request: Request, alterar_dto: AlterarSenhaDTO):
    email = request.state.cliente.email
    cliente_bd = ClienteRepo.obter_por_email(email)
    nova_senha_hash = obter_hash_senha(alterar_dto.nova_senha)
    response = JSONResponse({"redirect": {"url": "/cliente/senha"}})
    if not conferir_senha(alterar_dto.senha, cliente_bd.senha):
        adicionar_mensagem_erro(response, "Senha atual incorreta!")
        return response
    if ClienteRepo.alterar_senha(cliente_bd.id, nova_senha_hash):
        adicionar_mensagem_sucesso(response, "Senha alterada com sucesso!")
    else:
        adicionar_mensagem_erro(response, "Não foi possível alterar sua senha!")
    return response


@router.get("/sair", response_class=RedirectResponse)
async def get_sair(request: Request):
    if request.state.cliente:
        ClienteRepo.alterar_token(request.state.cliente.email, "")
    response = RedirectResponse("/", status.HTTP_303_SEE_OTHER)
    excluir_cookie_auth(response)
    adicionar_mensagem_sucesso(response, "Saída realizada com sucesso!")
    return response


@router.get("/carrinho")
async def get_carrinho(request: Request):
    pedidos = PedidoRepo.obter_por_estado(
        request.state.cliente.id, EstadoPedido.CARRINHO.value
    )
    pedido_carrinho = pedidos[0] if pedidos else None
    if pedido_carrinho:
        itens_pedido = ItemPedidoRepo.obter_por_pedido(pedido_carrinho.id)
    if not pedido_carrinho or not itens_pedido:
        response = RedirectResponse("/", status.HTTP_303_SEE_OTHER)
        adicionar_mensagem_alerta(
            response, 
            "Seu carrinho está vazio. Adicione produtos para continuar."
        ) 
        return response
    total_pedido = sum([item.valor_item for item in itens_pedido])
    return templates.TemplateResponse(
        "pages/carrinho.html",
        {"request": request, "itens": itens_pedido, "valor_total": total_pedido},
    )


@router.get("/confirmacaopedido")
async def get_confirmacaopedido(request: Request):
    pedidos = PedidoRepo.obter_por_estado(
        request.state.cliente.id, EstadoPedido.CARRINHO.value
    )
    pedido_carrinho = pedidos[0] if pedidos else None
    if not pedido_carrinho:
        return RedirectResponse("/cliente/carrinho", status.HTTP_303_SEE_OTHER)
    itens_pedido = ItemPedidoRepo.obter_por_pedido(pedido_carrinho.id)
    if not itens_pedido:
        return RedirectResponse("/cliente/carrinho", status.HTTP_303_SEE_OTHER)
    valor_total = sum([item.valor_produto * item.quantidade for item in itens_pedido])
    PedidoRepo.atualizar_para_fechar(
        pedido_carrinho.id, request.state.cliente.endereco, valor_total
    )
    pedido_carrinho = PedidoRepo.obter_por_id(pedido_carrinho.id)
    pedido_carrinho.endereco_entrega = pedido_carrinho.endereco_entrega.replace(
        "\n", "<br>"
    )
    pedido_carrinho.itens = itens_pedido
    return templates.TemplateResponse(
        "pages/confirmacaopedido.html",
        {"request": request, "pedido": pedido_carrinho},
    )


@router.get("/pagamentopedido/{id_pedido:int}", response_class=HTMLResponse)
async def get_pagamento(request: Request, id_pedido: int = Path(...)):
    pedido = PedidoRepo.obter_por_id(id_pedido)
    # se o pedido não existe, ou não pertence ao cliente logado
    if not pedido or (pedido and (pedido.id_cliente != request.state.cliente.id)):
        response = RedirectResponse(
            url="/cliente/pedidos", status_code=status.HTTP_302_FOUND
        )
        adicionar_mensagem_erro(
            response, f"O pedido {id_pedido:06d} não existe ou não pertence a você."
        )
        return response
    # se o pedido não está em estado que permita pagamento
    if pedido.estado not in [EstadoPedido.CARRINHO.value, EstadoPedido.PENDENTE.value]:
        response = RedirectResponse(
            url="/cliente/carrinho", status_code=status.HTTP_302_FOUND
        )
        adicionar_mensagem_erro(
            response, "O pedido em questão não está apto a receber pagamento."
        )
        return response
    # captura os itens do pedido
    itens = ItemPedidoRepo.obter_por_pedido(pedido.id)
    total_pedido = sum([item.valor_item for item in itens])
    pedido.itens = itens
    PedidoRepo.atualizar_para_fechar(pedido.id, pedido.endereco_entrega, total_pedido)
    # access_token = os.getenv("ACCESS_TOKEN_MP_PROD")
    access_token = os.getenv("ACCESS_TOKEN_MP_TEST")
    print(f"\n\n\nTOKEN: {access_token}\n\n\n")
    sdk = mp.SDK(access_token=access_token)
    url_de_retorno_do_mp = os.getenv("URL_TEST")
    preference = {
        "items": [
            {
                "title": f"Pedido {'{:06d}'.format(pedido.id)}",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": total_pedido,
            }
        ],
        # "payer": {
        #     "name": request.state.usuario.nome,
        #     "email": request.state.usuario.email,
        # },
        "payer": {
            "name": "Test",
            "surname": "Test",
            "email": "test_user_527575677@testuser.com",
        },
        "back_urls": {
            "success": f"{url_de_retorno_do_mp}/cliente/mp/sucesso/{pedido.id}",
            "failure": f"{url_de_retorno_do_mp}/cliente/mp/falha/{pedido.id}",
            "pending": f"{url_de_retorno_do_mp}/cliente/mp/pedente/{pedido.id}",
        },
        "auto_return": "approved",
    }
    preferenceResult = sdk.preference().create(preference)
    print(f"\n\nDados: {preferenceResult}")
    if preferenceResult:
        # url_pagamento_mercado_pago = preferenceResult["response"]["init_point"]
        url_pagamento_mercado_pago = preferenceResult["response"]["sandbox_init_point"]
        return RedirectResponse(
            url=url_pagamento_mercado_pago, status_code=status.HTTP_302_FOUND
        )


@router.get("/mp/sucesso/{id_pedido:int}", response_class=HTMLResponse)
async def get_mp_sucesso(
    request: Request,
    id_pedido: int = Path(...),
):
    pedido = PedidoRepo.obter_por_id(id_pedido)
    PedidoRepo.alterar_estado(id_pedido, EstadoPedido.PAGO.value)
    return RedirectResponse(f"/cliente/pedidoconfirmado/{id_pedido}")


@router.get("/mp/falha/{id_pedido:int}", response_class=HTMLResponse)
async def get_mp_falha(
    request: Request,
    id_pedido: int = Path(...),
):
    response = RedirectResponse(f"/cliente/resumopedido?id_pedido={id_pedido}")
    adicionar_mensagem_erro(
        response,
        "Houve alguma falha ao processar seu pagamento. Por favor, tente novamente.",
    )
    return response


@router.get("/mp/pendente/{id_pedido:int}", response_class=HTMLResponse)
async def get_mp_pendente(
    request: Request,
    id_pedido: int = Path(...),
):
    pedido = PedidoRepo.obter_por_id(id_pedido)
    PedidoRepo.alterar_estado(id_pedido, EstadoPedido.PAGO.value)
    return RedirectResponse(f"/cliente/detalhespedido/{id_pedido}")


@router.post("/post_adicionar_carrinho", response_class=RedirectResponse)
async def post_adicionar_carrinho(request: Request, id_produto: int = Form(...)):
    produto = ProdutoRepo.obter_um(id_produto)
    mensagem = f"O produto <b>{produto.nome}</b> foi adicionado ao carrinho."
    pedidos = PedidoRepo.obter_por_estado(
        request.state.cliente.id, EstadoPedido.CARRINHO.value
    )
    pedido_carrinho = pedidos[0] if pedidos else None
    if pedido_carrinho == None:
        pedido_carrinho = Pedido(
            0,  # id
            datetime.now(),
            0,  # valor_total
            request.state.cliente.endereco,
            EstadoPedido.CARRINHO.value,
            request.state.cliente.id,
        )
        pedido_carrinho = PedidoRepo.inserir(pedido_carrinho)
    qtde = ItemPedidoRepo.obter_quantidade_por_produto(pedido_carrinho.id, id_produto)
    if qtde == 0:
        item_pedido = ItemPedido(
            pedido_carrinho.id, id_produto, produto.nome, produto.preco, 1, 0
        )
        ItemPedidoRepo.inserir(item_pedido)
    else:
        ItemPedidoRepo.aumentar_quantidade_produto(pedido_carrinho.id, id_produto)
        mensagem = f"O produto <b>{produto.nome}</b> já estava no carrinho e teve sua quantidade aumentada."
        PedidoRepo.atualizar_valor_total(pedido_carrinho.id)
    response = RedirectResponse("/cliente/carrinho", status.HTTP_303_SEE_OTHER)
    adicionar_mensagem_sucesso(response, mensagem)
    return response


@router.post("/post_aumentar_item", response_class=RedirectResponse)
async def post_aumentar_item(request: Request, id_produto: int = Form(0)):
    produto = ProdutoRepo.obter_um(id_produto)
    pedidos = PedidoRepo.obter_por_estado(
        request.state.cliente.id, EstadoPedido.CARRINHO.value
    )
    pedido_carrinho = pedidos[0] if pedidos else None
    if pedido_carrinho == None:
        response = RedirectResponse(
            f"/produto?id={id_produto}", status.HTTP_303_SEE_OTHER
        )
        adicionar_mensagem_alerta(
            f"Seu carrinho não foi encontrado. Adicione este produto ao carrinho novamente."
        )
        return response
    qtde = ItemPedidoRepo.obter_quantidade_por_produto(pedido_carrinho.id, id_produto)
    if qtde == 0:
        response = RedirectResponse(
            f"/produto?id={id_produto}", status.HTTP_303_SEE_OTHER
        )
        adicionar_mensagem_alerta(
            f"Este produto não foi encontrado em seu carrinho. Adicione-o novamente."
        )
        return response
    ItemPedidoRepo.aumentar_quantidade_produto(pedido_carrinho.id, id_produto)
    response = RedirectResponse("/cliente/carrinho", status.HTTP_303_SEE_OTHER)
    adicionar_mensagem_sucesso(
        response,
        f"O produto <b>{produto.nome}</b> teve sua quantidade aumentada para <b>{qtde+1}</b>.",
    )
    return response

@router.post("/post_reduzir_item", response_class=RedirectResponse)
async def post_reduzir_item(request: Request, id_produto: int = Form(0)):
    produto = ProdutoRepo.obter_um(id_produto)
    pedidos = PedidoRepo.obter_por_estado(
        request.state.cliente.id, EstadoPedido.CARRINHO.value
    )
    pedido_carrinho = pedidos[0] if pedidos else None
    response = RedirectResponse("/cliente/carrinho", status.HTTP_303_SEE_OTHER)
    if pedido_carrinho == None:
        adicionar_mensagem_alerta(f"Seu carrinho não foi encontrado.")
        return response
    qtde = ItemPedidoRepo.obter_quantidade_por_produto(pedido_carrinho.id, id_produto)
    if qtde == 0:
        adicionar_mensagem_alerta(
            f"O produto {id_produto} não foi encontrado em seu carrinho."
        )
        return response
    if qtde == 1:
        ItemPedidoRepo.excluir(pedido_carrinho.id, id_produto)
        adicionar_mensagem_sucesso(
            response, f"O produto <b>{produto.nome}</b> foi excluído do carrinho."
        )
        return response
    ItemPedidoRepo.diminuir_quantidade_produto(pedido_carrinho.id, id_produto)
    adicionar_mensagem_sucesso(
        response,
        f"O produto <b>{produto.nome}</b> teve sua quantidade diminuída para <b>{qtde-1}</b>.",
    )
    PedidoRepo.atualizar_valor_total(pedido_carrinho.id)
    return response



@router.post("/post_remover_item", response_class=RedirectResponse)
async def post_remover_item(request: Request, id_produto: int = Form(0)):
    if not id_produto:
        return RedirectResponse("/cliente/carrinho", status.HTTP_304_NOT_MODIFIED)
    produto = ProdutoRepo.obter_um(id_produto)
    if not produto:
        respose = RedirectResponse("cliente/carrinho", status.HTTP_304_NOT_MODIFIED)
        adicionar_mensagem_alerta(response, "Produto não encontrado.")
        return response
    pedidos = PedidoRepo.obter_por_estado(
        request.state.cliente.id, EstadoPedido.CARRINHO.value
    )
    pedido_carrinho = pedidos[0] if pedidos else None
    response = RedirectResponse("/cliente/carrinho", status.HTTP_303_SEE_OTHER)
    if pedido_carrinho == None:
        adicionar_mensagem_alerta(f"Seu carrinho não foi encontrado.")
        return response
    qtde = ItemPedidoRepo.obter_quantidade_por_produto(pedido_carrinho.id, id_produto)
    if qtde == 0:
        adicionar_mensagem_alerta(
            f"O produto {id_produto} não foi encontrado em seu carrinho."
        )
        return response 
    ItemPedidoRepo.excluir(pedido_carrinho.id, id_produto)
    respose = RedirectResponse("cliente/carrinho", status.HTTP_303_SEE_OTHER)
    adicionar_mensagem_sucesso(response, "Item excluído com sucesso")
    PedidoRepo.atualizar_valor_total(pedido_carrinho.id)
    return response



@router.get("/pedidoconfirmado/{id_pedido:int}", response_class=HTMLResponse)
async def get_pedidoconfirmado(
    request: Request,
    id_pedido: int = Path(...),
):
    pedido = PedidoRepo.obter_por_id(id_pedido)
    if pedido.id_cliente != request.state.cliente.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    PedidoRepo.alterar_estado(id_pedido, EstadoPedido.PAGO.value)
    return templates.TemplateResponse(
        "pages/pedidoconfirmado.html",
        {"request": request, "pedido": pedido},
    )


@router.get("/detalhespedido/{id_pedido:int}", response_class=HTMLResponse)
async def get_detalhespedido(
    request: Request,
    id_pedido: int = Path(...),
):
    pedido = PedidoRepo.obter_por_id(id_pedido)
    if pedido.id_usuario != request.state.usuario.id:
        response = RedirectResponse(url="/pedidos", status_code=status.HTTP_302_FOUND)
        return adicionar_mensagem_erro(
            response,
            "Pedido não encontrado. Verifique o número do pedido e tente novamente.",
        )
    itens = ItemPedidoRepo.obter_por_pedido(pedido.id)
    pedido.itens = itens
    return templates.TemplateResponse(
        "pages/detalhespedido.html",
        {"request": request, "pedido": pedido},
    )
