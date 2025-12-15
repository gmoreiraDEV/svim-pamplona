from langchain_core.tools import tool
from typing import Any, Dict

from app.utils.http_client import get_http_client

@tool
def listar_profissionais_tool(page: int = 1, pageSize: int = 50) -> dict:
    """Lista profissionais disponíveis de forma paginada."""
    params = {
        "page": page,
        "pageSize": pageSize,
    }
    client = get_http_client()
    return client.get("/profissionais", params=params)

@tool
def listar_servicos_profissional_tool(
    profissionalId: int,
    page: int = 1,
    pageSize: int = 50,
) -> dict:
    """Lista os serviços oferecidos por um profissional específico."""
    params = {
        "page": page,
        "pageSize": pageSize,
    }

    if profissionalId is None:
        return {"error": "Profissional não informado"}

    http = get_http_client()
    return http.get(f"/profissionais/{profissionalId}/servicos", params=params)

@tool
def listar_servicos_tool(
    nome: str | None = None,
    categoria: str | None = None,
    somenteVisiveisCliente: bool | None = None,
    page: int | None = 1,
    pageSize: int | None = 50
) -> dict:
    """Lista serviços filtrando por nome, categoria e visibilidade."""
    params: Dict[str, Any] = {
        "page": page,
        "pageSize": pageSize,
    }

    if nome is not None:
        params["nome"] = nome

    if categoria is not None:
        params["categoria"] = categoria

    if somenteVisiveisCliente is not None:
        params["somenteVisiveisCliente"] = bool(somenteVisiveisCliente)

    http = get_http_client()
    return http.get("/servicos", params=params)

@tool
def criar_agendamento_tool(
    servicoId: str,
    profissionalId: str,
    clienteId: str,
    dataHoraInicio: str,
    duracaoEmMinutos: str,
    valor: str,
    observacoes: str | None = None,
    confirmado: bool | None = None,
) -> Dict[str, Any]:
    """Cria um agendamento a partir dos dados fornecidos."""

    required_fields = [
        ("servicoId", servicoId),
        ("profissionalId", profissionalId),
        ("clienteId", clienteId),
        ("dataHoraInicio", dataHoraInicio),
        ("duracaoEmMinutos", duracaoEmMinutos),
        ("valor", valor),
    ]
    missing = [name for name, val in required_fields if val in (None, "", [])]
    if missing:
        return {"error": "ARGS_INVALIDOS", "missing": missing}

    payload = {
        "servicoId": servicoId,
        "clienteId": clienteId,
        "profissionalId": profissionalId,
        "dataHoraInicio": dataHoraInicio,
        "duracaoEmMinutos": duracaoEmMinutos,
        "valor": valor,
        "observacoes": observacoes,
        "confirmado": True if confirmado is None else confirmado, 
    }

    http = get_http_client()
    return http.post("/agendamentos", json=payload)

@tool
def listar_agendamentos_tool(
    dataInicio: str,
    dataFim: str,
    page: int | None = 1,
    pageSize: int | None = 50,
) -> Dict[str, Any]:
    """
    Lista todos os agendamentos passando os paramentros de roda data de inicio, data do fim e id do cliente
    """
    params: Dict[str, Any] = {
        "dataInicio": dataInicio,
        "dataFim": dataFim,
        "page": page,
        "pageSize": pageSize,
    }

    http = get_http_client()
    return http.get("/agendamentos", params=params)

