import os
import json
from collections import defaultdict
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from typing_extensions import Annotated, TypedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages, REMOVE_ALL_MESSAGES
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from app.agent.tools import (
    criar_agendamento_tool,
    listar_agendamentos_tool,
    listar_servicos_tool,
    listar_servicos_profissional_tool,
    listar_profissionais_tool,
)
from app.utils.qdrant import QdrantMemory

load_dotenv()

svim = os.getenv("SVIM")
cliente_id = os.getenv("CLIENT_ID")
cliente_nome = os.getenv("CLIENT_NOME")
cliente_whatsapp = os.getenv("CLIENT_WHATSAPP")
session_id = os.getenv("SESSION_ID")
qdrant_collection = os.getenv("QDRANT_COLLECTION", "svim_conversations")
embedding_model = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
qdrant_vector_size = int(os.getenv("QDRANT_VECTOR_SIZE", "1536"))
brazil_timezone = ZoneInfo("America/Sao_Paulo")
now_in_brazil = datetime.now(brazil_timezone)

# Format the time into an ISO 8601 string
iso_format_brazil = now_in_brazil.isoformat()


MAX_HISTORY_CHARS = 4000
MAX_STORE_CHARS = 1500
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS_PER_TOOL", "5"))

memory: Optional[QdrantMemory] = None

if os.getenv("QDRANT_URL"):
    memory = QdrantMemory(
        collection_name=qdrant_collection,
        embedding_model=embedding_model,
        vector_size=qdrant_vector_size,
    )

_tool_call_counts: defaultdict[str, defaultdict[str, int]] = defaultdict(
    lambda: defaultdict(int)
)
_tool_cache: defaultdict[str, dict[str, Any]] = defaultdict(dict)


def _thread_id_from_config(config: RunnableConfig | None) -> str:
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
    else:
        configurable = {}
    return str(configurable.get("thread_id") or "anon")


def _reset_tool_counts(thread_id: str) -> None:
    _tool_call_counts.pop(thread_id, None)
    _tool_cache.pop(thread_id, None)


def _limit_tool_calls(tool: BaseTool) -> BaseTool:
    """Wrap tool to guard against repeated calls in uma única solicitação."""
    original_invoke = tool.invoke
    original_ainvoke = tool.ainvoke

    def _exceeded(thread_id: str) -> bool:
        return _tool_call_counts[thread_id][tool.name] >= MAX_TOOL_CALLS

    def _bump(thread_id: str) -> None:
        _tool_call_counts[thread_id][tool.name] += 1

    def limited_invoke(
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        thread_id = _thread_id_from_config(config)
        call_id = input.get("id") if isinstance(input, dict) else thread_id
        cache_key = None
        if isinstance(input, dict):
            payload = input.get("args") if "args" in input else input
            try:
                cache_key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            except Exception:
                cache_key = str(payload)

        # Cache hit: devolve ToolMessage imediato
        if cache_key and cache_key in _tool_cache[thread_id].get(tool.name, {}):
            cached_content = _tool_cache[thread_id][tool.name][cache_key]
            return ToolMessage(
                content=cached_content,
                name=tool.name,
                tool_call_id=call_id,
                status="success",
            )

        if _exceeded(thread_id):
            content = json.dumps(
                {
                    "error": "TOOL_LIMIT",
                    "message": (
                        f"Limite de {MAX_TOOL_CALLS} chamadas atingido "
                        f"para a ferramenta {tool.name}"
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            return ToolMessage(
                content=content,
                name=tool.name,
                tool_call_id=call_id,
                status="error",
            )
        _bump(thread_id)
        resp = original_invoke(input, config=config, **kwargs)
        if isinstance(resp, ToolMessage):
            return resp
        if not isinstance(resp, (str, list)):
            resp = json.dumps(resp, ensure_ascii=False, separators=(",", ":"))
        # Cache only respostas sem error
        try:
            parsed = json.loads(resp) if isinstance(resp, str) else None
            if isinstance(parsed, dict) and not parsed.get("error") and cache_key:
                _tool_cache[thread_id].setdefault(tool.name, {})[cache_key] = resp
        except Exception:
            pass
        return ToolMessage(content=resp, name=tool.name, tool_call_id=call_id)

    async def limited_ainvoke(
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ):
        thread_id = _thread_id_from_config(config)
        call_id = input.get("id") if isinstance(input, dict) else thread_id
        cache_key = None
        if isinstance(input, dict):
            payload = input.get("args") if "args" in input else input
            try:
                cache_key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            except Exception:
                cache_key = str(payload)

        if cache_key and cache_key in _tool_cache[thread_id].get(tool.name, {}):
            cached_content = _tool_cache[thread_id][tool.name][cache_key]
            return ToolMessage(
                content=cached_content,
                name=tool.name,
                tool_call_id=call_id,
                status="success",
            )

        if _exceeded(thread_id):
            content = json.dumps(
                {
                    "error": "TOOL_LIMIT",
                    "message": (
                        f"Limite de {MAX_TOOL_CALLS} chamadas atingido "
                        f"para a ferramenta {tool.name}"
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            return ToolMessage(
                content=content,
                name=tool.name,
                tool_call_id=call_id,
                status="error",
            )
        _bump(thread_id)
        resp = await original_ainvoke(input, config=config, **kwargs)
        if isinstance(resp, ToolMessage):
            return resp
        if not isinstance(resp, (str, list)):
            resp = json.dumps(resp, ensure_ascii=False, separators=(",", ":"))
        try:
            parsed = json.loads(resp) if isinstance(resp, str) else None
            if isinstance(parsed, dict) and not parsed.get("error") and cache_key:
                _tool_cache[thread_id].setdefault(tool.name, {})[cache_key] = resp
        except Exception:
            pass
        return ToolMessage(content=resp, name=tool.name, tool_call_id=call_id)

    # StructuredTool é um Pydantic model; usar object.__setattr__ evita erro de campo desconhecido.
    object.__setattr__(tool, "invoke", limited_invoke)  # type: ignore[method-assign]
    object.__setattr__(tool, "ainvoke", limited_ainvoke)  # type: ignore[method-assign]
    return tool


SYSTEM_PROMPT = f"""
Você é a Maria, assistente do salão {svim} e ajuda clientes a gerenciarem seus horários para atendimento.

PERSONALIDADE:
- Amigável, mas profissional
- Usa linguagem clara e feminina
- As vezes utiliza emojis

ESPECIALIDADES:
- Agendamento de horários
- Sugestão de horários
- Especialista em todos os serviços da {svim}

ESTILO DE RESPOSTA:
- Sempre faz uma pergunta por vez
- Não utiliza bullet points
- Sempre proativa

<agendamento>
PASSOS PARA O AGENDAMENTO
- Capturar o serviço perguntando ao cliente
    - Extrair do resultado o ID do serviço escolhido
- Capturar a preferência de profissional do cliente
    - Verificar se o profissional realiza o serviço escolhido
    - Se não realizar, informar ao cliente e pedir para escolher outro profissional ou serviço
    - Listar os profissionais que realizam o serviço escolhido
    - Verificar se o profissional escolhido está disponível no dia e horário desejado
    - Extrair do resultado o ID do profissional escolhido
- Capturar o dia e horário desejado
    - Verificar se o horário está dentro do horário de funcionamento da {svim}
    - Verificar se o horário está disponível com o profissional escolhido
    - Se não estiver disponível, sugerir próximos 3 horários disponíveis
- Utilize os dados coletaos para o agendamento:
{{
    "servicoId": "str",
    "profissionalId": "str",
    "clienteId": "str",
    "dataHoraInicio": "str",
    "duracaoEmMinutos": "str",
    "valor": "str",
    "observacoes": "str | None",
    "confirmado": "bool | None",
}}
</agendamento>

REGRAS:
- Nunca chame a mesma ferramenta mais de {MAX_TOOL_CALLS} vezes por solicitação do cliente; se precisar de mais dados, peça ao cliente.
- Se já tiver a lista, não repita; apenas pergunte qual item o cliente quer.
- Não realize agendamentos em datas anteriores a hoje: {iso_format_brazil}.

CLIENTE:
ID: {cliente_id}
Nome: {cliente_nome}
WhatsApp: {cliente_whatsapp}

KNOWLEDGE:
- Atendimento da {svim}:
Segunda à Sábado: 14h às 22h
Domingo: 14h às 20h

Bem-vindo ao Svim Pamplona,  somos uma rede de salão presente de norte a sudeste do Brasil onde a nossa missão é revelar belezas escondidas e desconhecidas proporcionando bem estar e cuidado ao próximo, atendendo com excelência e ética. 
Formas de pagamento: Cartão de Crédito, Cartão de Débito, Dinheiro, PIX
Idiomas: Português, Inglês
Facilidades: Wi-Fi, Estacionamento - Pago, Atendemos adultos e crianças, Acesso para Deficientes, Aceita cartão de crédito

Rua Rua Pamplona, 1707, Loja 111, Jardim Paulista, São Paulo, SP - 01405-002
https://maps.google.com/maps?daddr=Rua%20Rua%20Pamplona,%201707,%20Loja%20111,%20Jardim%20Paulista,%20S%C3%A3o%20Paulo,%20SP%20-%2001405-002
"""

model = ChatOpenAI(
    model="gpt-4.1",
    max_tokens=600,
    temperature=0.2,
)

TOOLS = [
    _limit_tool_calls(criar_agendamento_tool),
    _limit_tool_calls(listar_agendamentos_tool),
    _limit_tool_calls(listar_servicos_tool),
    _limit_tool_calls(listar_servicos_profissional_tool),
    _limit_tool_calls(listar_profissionais_tool),
]

agent = create_react_agent(
    model,
    tools=TOOLS,
)


class State(TypedDict):
    cliente_id: str | None
    session_id: str | None
    history: str | None
    messages: Annotated[list[BaseMessage], add_messages]


def _format_messages(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return ""
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


def _to_text(content: Any) -> str:
    """Normaliza conteúdo em string para buscas semânticas."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(_to_text(item) for item in content)
    return str(content)


def load_context(state: State) -> State:
    thread_id = state.get("session_id") or state.get("cliente_id") or "anon"
    _reset_tool_counts(str(thread_id))

    if memory is None:
        return state

    user_id = state.get("cliente_id") or "anon"
    session_id = state.get("session_id")

    query = ""
    last_user = next(
        (m for m in reversed(state.get("messages", [])) if m.type == "human"),
        None,
    )
    if last_user:
        query = _to_text(last_user.content)

    context_messages = memory.get_hybrid_context(
        session_id=session_id,
        user_id=user_id,
        query=query,
        recent_k=4,
        semantic_k=2,
    )

    state["history"] = _format_messages(context_messages)
    print(f"[SVIM] Loaded hybrid context: {len(context_messages)} msgs")

    return state


def inject_system(state: State) -> State:
    msgs = state["messages"]
    history = (state.get("history") or "")[:MAX_HISTORY_CHARS]

    print(
        f"[SVIM] system chars={len(SYSTEM_PROMPT)} "
        f"history chars={len(history)} "
        f"msgs chars={sum(len(getattr(m, 'content', '') or '') for m in msgs)}"
    )

    new_msgs: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]

    if history:
        new_msgs.append(
            SystemMessage(content=f"Contexto recente do cliente:\n{history}")
        )
    new_msgs.extend(m for m in msgs if m.type in ("human", "ai"))

    def _preview(msg: BaseMessage, limit: int = 80) -> str:
        content = (getattr(msg, "content", "") or "").replace("\n", " ")
        return content[:limit]

    print(
        "[SVIM] message order: "
        + " | ".join(
            f"{m.type}:{len(getattr(m, 'content', '') or '')}:{_preview(m)}"
            for m in new_msgs
        )
    )
    
    return {
        "messages": [RemoveMessage(REMOVE_ALL_MESSAGES), *new_msgs],
        "history": history,
        "cliente_id": state.get("cliente_id"),
        "session_id": state.get("session_id"),
    }


def save_context(state: State) -> State:
    if memory is None:
        return state

    user_id = state.get("cliente_id") or "anon"
    session_id = state.get("session_id")

    to_store: List[Dict[str, str]] = []

    for msg in state["messages"]:
        if msg.type in ("human", "ai"):
            role = "user" if msg.type == "human" else "assistant"
            content = (msg.content or "")[:MAX_STORE_CHARS]
            to_store.append({"role": role, "content": content})

    memory.store_messages(
        user_id=user_id,
        session_id=session_id,
        messages=to_store,
    )

    print(f"[SVIM] Stored {len(to_store)} msgs in Qdrant")
    return state


builder = StateGraph(State)

builder.add_node("load_context", load_context)
builder.add_node("inject_system", inject_system)
builder.add_node("agent", agent)
builder.add_node("save_context", save_context)

builder.set_entry_point("load_context")
builder.add_edge("load_context", "inject_system")
builder.add_edge("inject_system", "agent")
builder.add_edge("agent", "save_context")
builder.add_edge("save_context", END)

USE_LANGGRAPH_API = os.getenv("LANGGRAPH_API", "").lower() in ("1", "true", "yes")

if USE_LANGGRAPH_API:
    graph = builder.compile()
else:
    graph = builder.compile(checkpointer=MemorySaver())
