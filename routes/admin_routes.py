from fastapi import APIRouter

from repositories.produto_repo import ProdutoRepo


router = APIRouter(prefix="/manager")

@router.get("/obter_produtos")
async def obter_produtos():
    produtos = ProdutoRepo.obter_todos()
    return produtos

@router.post("/inserir_produto")
async def inserir_produto(produto: NovoProdutoDTO):
    pass
