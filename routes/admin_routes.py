from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from dtos import entrar_dto
from dtos.alterar_pedido_dto import AlterarPedidoDto
from dtos.alterar_produto_dto import AlterarProdutoDto
from dtos.entrar_dto import EntrarDto
from dtos.id_produto_dto import IdProdutoDto
from dtos.inserir_produto_dto import InserirProdutoDto
from dtos.problem_details_dto import ProblemDetailsDto
from models.pedido_model import EstadoPedido
from models.produto_model import Produto
from repositories.pedido_repo import PedidoRepo
from repositories.produto_repo import ProdutoRepo
from repositories.usuario_repo import UsuarioRepo
from util.auth_cookie import conferir_senha, criar_token


router = APIRouter(prefix="/manager")

@router.get("/obter_produtos")
async def obter_produtos():
    produtos = ProdutoRepo.obter_todos()
    return produtos

@router.post("/inserir_produto", status_code=201)
async def inserir_produto(inputDto: InserirProdutoDto) -> Produto:
    novo_produto = Produto(None, inputDto.nome, inputDto.preco, inputDto.descricao, inputDto.estoque)
    novo_produto = ProdutoRepo.inserir(novo_produto)
    return novo_produto

@router.post("/excluir_produto", status_code=204)
async def excluir_produto(inputDto: IdProdutoDto):
    if ProdutoRepo.excluir(inputDto.id_produto): return None
    pd = ProblemDetailsDto("int", f"O produto com id {inputDto.id_produto} não foi encontrado.", "value_not_found", ["body", "id_produto"])
    return JSONResponse(pd.to_dict(), status_code=404)

@router.get("/obter_produto/{id_produto}")
async def obter_produto(id_produto: int = Path(..., title="Id do Produto", ge=1)):
    produto = ProdutoRepo.obter_um(id_produto)
    if produto: return produto
    pd = ProblemDetailsDto("int", f"O produto com id <b>{id_produto} não foi encontrado.", "value_not_found", ["body", "id_produto"])
    return JSONResponse(pd.to_dict(), status_code=404)


@router.post("/alterar_produto", status_code=204)
async def alterar_produto(inputDto: AlterarProdutoDto):
    produto =  Produto(inputDto.id, inputDto.nome, inputDto.preco, inputDto.descricao, inputDto.estoque)
    if ProdutoRepo.alterar(produto): return None
    pd = ProblemDetailsDto("int", f"O produto com id {inputDto.id} não foi encontrado.", "value_not_found", ["body", "id"])
    return JSONResponse(pd.to_dict(), status_code=404)

@router.post("/alterar_pedido", status_code=204)
async def alterar_pedido(inputDto: AlterarPedidoDto):
    if PedidoRepo.alterar_estado(inputDto.id, inputDto.estado.value): return None
    pd = ProblemDetailsDto("int", f"O pedido com id {inputDto.id} não foi encontrado.", "value_not_found", ["body", "id"])
    return JSONResponse(pd.to_dict(), status_code=404)

@router.get("/obter_pedido/{id_pedido}")
async def obter_pedido(id_pedido: int = Path(..., title="Id do Pedido", ge=1)):
    pedido = PedidoRepo.obter_por_id(id_pedido)
    if pedido: return pedido
    pd = ProblemDetailsDto("int", f"O pedido com id {id_pedido} não foi encontrado.", "value_not_found", ["body", "id"])
    return JSONResponse(pd.to_dict(), status_code=404)

@router.get("/obter_pedidos_por_estado/{estado}")
async def obter_pedidos_por_estado(estado: EstadoPedido = Path(..., title="Estado do Pedido")):
    pedidos = PedidoRepo.obter_todos_por_estado(estado.value)
    return pedidos

@router.post("/entrar")
async def entrar(entrarDto: EntrarDto):
        cliente_entrou = UsuarioRepo.obter_por_email(entrarDto.email)
        if ((not cliente_entrou)
            or (not cliente_entrou.senha)
            or (not conferir_senha(entrarDto.senha, cliente_entrou.senha))):
            pd = ProblemDetailsDto("str", f"Credenciais inválidas. Certifique-se de que está cadastrado e de que sua senha está correta.", "value_not_found", ["body", "email", "senha"])
            return JSONResponse(pd.to_dict(), status_code=404)
        token = criar_token(cliente_entrou.id, cliente_entrou.nome, cliente_entrou.email, cliente_entrou.perfil)
        return JSONResponse({"token": token})
