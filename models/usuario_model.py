from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Usuario:
    id: Optional[int] = None
    nome: Optional[str] = None
    cpf: Optional[str] = None
    data_nascimento: Optional[date] = None
    endereco: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    perfil: Optional[int] = None
    senha: Optional[str] = None
    # Usar o campo abaixo somente se for atutenticação por cookie
    # token: Optional[str] = None
