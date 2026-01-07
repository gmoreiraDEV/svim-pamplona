import json
import re
import unicodedata
from langchain_core.tools import tool
from typing import Any, Dict, Iterable, Callable

from app.utils.http_client import get_http_client
from app.agent.aliases import SERVICE_ALIASES
from app.agent.stop_words import STOPWORDS
from app.utils.logger import get_logger

def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _normalize_service_term(term: str | None) -> str | None:
    if not term:
        return term
    text = _strip_accents(term.lower())
    text = re.sub(r"[^a-z0-9\\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in STOPWORDS]
    if not tokens:
        return term
    normalized = " ".join(tokens)
    return SERVICE_ALIASES.get(normalized, normalized)


def _trim_fields(item: Dict[str, Any], allowed_keys: Iterable[str]) -> Dict[str, Any]:
    """Keep only whitelisted keys from a dict."""
    return {
        key: item[key]
        for key in allowed_keys
        if key in item and item[key] not in (None, "", [])
    }


def _compact_service(item: Dict[str, Any], include_valor: bool = False) -> Dict[str, Any]:
    keys = ["id", "nome", "categoria", "duracaoEmMinutos"]
    if include_valor:
        keys.append("valor")
    service = _trim_fields(item, keys)
    if include_valor and "valor" not in service and "preco" in item:
        service["valor"] = item.get("preco")
    if "descricao" in item:
        service["descricao"] = str(item["descricao"])[:160]
    return service


def _compact_professional(item: Dict[str, Any]) -> Dict[str, Any]:
    return _trim_fields(
        item,
        (
            "id",
            "nome",
            "apelido",
            "categoria",
            "especialidades",
        ),
    )


def _compact_agendamento(item: Dict[str, Any]) -> Dict[str, Any]:
    agendamento = _trim_fields(
        item,
        ("id", "dataHoraInicio", "dataHoraFim", "duracaoEmMinutos", "valor", "status"),
    )
    if isinstance(item.get("servico"), dict):
        agendamento["servico"] = _compact_service(item["servico"])
    if isinstance(item.get("profissional"), dict):
        agendamento["profissional"] = _compact_professional(item["profissional"])
    if isinstance(item.get("cliente"), dict):
        agendamento["cliente"] = _trim_fields(item["cliente"], ("id", "nome"))
    return agendamento


def _compact_response(
    response: Dict[str, Any],
    data_mapper: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Remove campos desnecessários das respostas para economizar tokens."""
    if not isinstance(response, dict):
        return response

    if response.get("error"):
        return response

    compacted: Dict[str, Any] = {}

    data = response.get("data")
    if isinstance(data, list):
        compacted["data"] = [data_mapper(item) for item in data]
    elif isinstance(data, dict):
        compacted["data"] = data_mapper(data)
    else:
        compacted["data"] = data

    # Mantém apenas metadados pequenos relevantes
    for meta_key in ("page", "pageSize", "total", "message"):
        if meta_key in response:
            compacted[meta_key] = response[meta_key]

    return compacted


def _tool_result(payload: Dict[str, Any]) -> str:
    """Serializa o payload em JSON compacto para ser usado pelo agente."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


logger = get_logger(__name__)

@tool
def listar_profissionais_tool(page: int = 1, pageSize: int = 50) -> str:
    """Lista profissionais disponíveis de forma paginada."""
    params = {
        "page": page,
        "pageSize": pageSize,
    }
    logger.info("[tool] listar_profissionais_tool params=%s", params)
    client = get_http_client()
    resp = client.get("/profissionais", params=params)
    return _tool_result(_compact_response(resp, _compact_professional))

@tool
def listar_servicos_profissional_tool(
    profissionalId: int,
    page: int = 1,
    pageSize: int = 50,
    incluirValor: bool = False,
) -> str:
    """Lista os serviços oferecidos por um profissional específico."""
    params = {
        "page": page,
        "pageSize": pageSize,
    }

    logger.info(
        "[tool] listar_servicos_profissional_tool profissionalId=%s page=%s pageSize=%s",
        profissionalId,
        page,
        pageSize,
    )

    if profissionalId is None:
        logger.warning("[tool] listar_servicos_profissional_tool missing profissionalId")
        return _tool_result({"error": "Profissional não informado"})

    http = get_http_client()
    resp = http.get(f"/profissionais/{profissionalId}/servicos", params=params)
    return _tool_result(
        _compact_response(resp, lambda item: _compact_service(item, incluirValor))
    )

@tool
def listar_servicos_tool(
    nome: str | None = None,
    categoria: str | None = None,
    somenteVisiveisCliente: bool | None = None,
    page: int | None = 1,
    pageSize: int | None = 50,
    incluirValor: bool = False,
) -> str:
    """Lista serviços filtrando por nome, categoria e visibilidade."""
    params: Dict[str, Any] = {
        "page": page,
        "pageSize": pageSize,
    }

    if nome is not None:
        params["nome"] = _normalize_service_term(nome)

    if categoria is not None:
        params["categoria"] = _normalize_service_term(categoria)

    logger.info("[tool] listar_servicos_tool params=%s", params)
    if somenteVisiveisCliente is not None:
        params["somenteVisiveisCliente"] = bool(somenteVisiveisCliente)

    http = get_http_client()
    resp = http.get("/servicos", params=params)
    return _tool_result(
        _compact_response(resp, lambda item: _compact_service(item, incluirValor))
    )

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
) -> str:
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
        logger.warning("[tool] criar_agendamento_tool missing=%s", missing)
        return _tool_result({"error": "ARGS_INVALIDOS", "missing": missing})

    # Valida IDs numéricos para evitar chamadas inválidas na API
    if not str(profissionalId).isdigit():
        return _tool_result(
            {
                "error": "PROFISSIONAL_ID_INVALIDO",
                "message": "profissionalId deve ser numérico",
                "value": str(profissionalId),
            }
        )
    if not str(servicoId).isdigit():
        return _tool_result(
            {
                "error": "SERVICO_ID_INVALIDO",
                "message": "servicoId deve ser numérico",
                "value": str(servicoId),
            }
        )

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

    print(f"[SVIM] criar_agendamento_tool payload={payload}")
    http = get_http_client()
    resp = http.post("/agendamentos", json=payload)
    return _tool_result(_compact_response(resp, _compact_agendamento))

@tool
def listar_agendamentos_tool(
    dataInicio: str,
    dataFim: str,
    page: int | None = 1,
    pageSize: int | None = 50,
) -> str:
    """
    Lista todos os agendamentos passando os paramentros de roda data de inicio, data do fim e id do cliente
    """
    params: Dict[str, Any] = {
        "dataInicio": dataInicio,
        "dataFim": dataFim,
        "page": page,
        "pageSize": pageSize,
    }

    logger.info("[tool] listar_agendamentos_tool params=%s", params)
    http = get_http_client()
    resp = http.get("/agendamentos", params=params)
    return _tool_result(_compact_response(resp, _compact_agendamento))
