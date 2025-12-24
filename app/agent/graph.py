import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from typing_extensions import Annotated, TypedDict

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
  listar_profissionais_tool
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
memory: Optional[QdrantMemory] = None

MAX_HISTORY_CHARS = 4000

if os.getenv("QDRANT_URL"):
    try:
        memory = QdrantMemory(
            collection_name=qdrant_collection or "svim_conversations",
            embedding_model=embedding_model,
            vector_size=qdrant_vector_size,
        )
        print(f"[SVIM] QDRANT_URL={'set' if os.getenv('QDRANT_URL') else 'missing'}")
        print(f"[SVIM] QDRANT_COLLECTION={qdrant_collection}")
        print(f"[SVIM] Qdrant enabled? {memory is not None}")
    except Exception as e:
        print(f"[SVIM] Qdrant desabilitado: {e}")

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
## PASSOS PARA O AGENDAMENTO
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

model = ChatOpenAI(model="gpt-4.1", max_tokens=600)

TOOLS = [
  criar_agendamento_tool,
  listar_agendamentos_tool,
  listar_servicos_tool,
  listar_servicos_profissional_tool,
  listar_profissionais_tool
]

agent = create_react_agent(
  model,
  tools=TOOLS,
  prompt=SYSTEM_PROMPT
)

class State(TypedDict):
    cliente_id: str | None
    session_id: str | None
    history: str | None
    messages: Annotated[list[BaseMessage], add_messages]

def _format_messages(messages: List[Dict[str, Any]]) -> str:
    """Formata lista de mensagens (role/content) para contexto no prompt."""
    if not messages:
        return ""

    formatted = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


def load_context(state: State) -> State:
    """
    Carrega contexto recente de conversas com esse cliente a partir do Qdrant.
    Adiciona um resumo de histórico no prompt, sem alterar a mensagem do usuário.
    """
    if memory is None:
        return state

    try:
        user_id = cliente_id or state.get("cliente_id") or "anon"
        session_id = state.get("session_id") or os.getenv("SESSION_ID") or None

        state["cliente_id"] = user_id
        state["session_id"] = session_id
        query = ""
        last_user_msg = next((m for m in reversed(state.get("messages", [])) if m.type == "human"), None)
        if last_user_msg:
            query = last_user_msg.content or ""

        context_messages = memory.get_hybrid_context(
            session_id=session_id,
            user_id=user_id,
            query=query,
            recent_k=6,
            semantic_k=4,
        )

        state["history"] = _format_messages(context_messages)
        print(
            f"[SVIM] Loaded hybrid context: {len(context_messages)} msgs "
            f"(user_id={user_id}, session_id={session_id})"
        )

    except Exception as e:
        print(f"[SVIM] Error loading context: {e}")

    return state


def inject_system(state: State) -> State:
    msgs = state["messages"]
    history = (state.get("history") or "")[:MAX_HISTORY_CHARS]

    system_content = SYSTEM_PROMPT

    new_msgs = []
    new_msgs.append(SystemMessage(content=system_content))

    if history:
        new_msgs.append(SystemMessage(content=f"Contexto recente (resumo/trechos):\n{history}"))

    rest = [m for m in msgs if m.type != "system"]
    new_msgs.extend(rest)

    return {
        "messages": new_msgs,
        "history": history,
        "cliente_id": state.get("cliente_id"),
        "session_id": state.get("session_id"),
    }


def save_context(state: State) -> State:
    """Persiste mensagens do diálogo no Qdrant."""
    print("[SVIM] save_context node entered")
    print(f"[SVIM] save_context state.cliente_id={state.get('cliente_id')!r} state.session_id={state.get('session_id')!r}")

    if memory is None:
        print("[SVIM] Qdrant memory not configured, skipping save_context")
        return state

    try:
        user_id = cliente_id or state.get("cliente_id") or "anon"
        sid = state.get("session_id") or os.getenv("SESSION_ID") or None

        new_messages: List[Dict[str, str]] = []
        for msg in state["messages"]:
            if msg.type in ("human", "ai"):
                new_messages.append({"role": msg.type, "content": msg.content})

        memory.store_messages(user_id=user_id, session_id=sid, messages=new_messages)
        print(f"[SVIM] Stored {len(new_messages)} messages for user_id={user_id} session_id={sid}")

    except Exception as e:
        print(f"[SVIM] Error saving context: {e}")

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

graph = builder.compile(checkpointer=MemorySaver())