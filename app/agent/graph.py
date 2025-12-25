import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from typing_extensions import Annotated, TypedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
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

memory: Optional[QdrantMemory] = None

if os.getenv("QDRANT_URL"):
    memory = QdrantMemory(
        collection_name=qdrant_collection,
        embedding_model=embedding_model,
        vector_size=qdrant_vector_size,
    )


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
- Você não deve chamar nenhuma ferramenta mais de 1 vez por solicitação do cliente. 
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
    criar_agendamento_tool,
    listar_agendamentos_tool,
    listar_servicos_tool,
    listar_servicos_profissional_tool,
    listar_profissionais_tool,
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


def load_context(state: State) -> State:
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
        query = last_user.content or ""

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
    
    return {
        "messages": new_msgs,
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
