import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from typing_extensions import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

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

if os.getenv("QDRANT_URL"):
    try:
        memory = QdrantMemory(
            collection_name=qdrant_collection or "svim_conversations",
            embedding_model=embedding_model,
            vector_size=qdrant_vector_size,
        )
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
- Capturar o serviço
- Capturar o dia e horário desejado
- Capturar a preferência de profissionais do cliente
- Capturar o nome e WhatsApp do cliente
- Devolva um json com esses dados:
{{"servico": "str",
"horario": "datetime",
"profissional": "str",
"cliente": {{
  "nome": "str", 
  "whatsApp": "str",
  }}
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
"""

model = ChatOpenAI(model="gpt-4.1")

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
        # CLIENT_ID do ambiente é prioridade; depois o que vier no estado.
        user_id = cliente_id or state.get("cliente_id") or "anon"
        session_id = session_id or state.get("session_id")
        state["cliente_id"] = user_id
        state["session_id"] = session_id
        last_human = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
        query = last_human.content if last_human else ""

        context_messages = memory.get_user_context(
            user_id=user_id,
            query=query,
            k=5,
        )
        history_text = _format_messages(context_messages)
        state["history"] = history_text
        print(f"[SVIM] Loaded {len(context_messages)} context messages for user_id={user_id} session_id={session_id}")
    except Exception as e:
        print(f"[SVIM] Error loading context: {e}")

    return state


def inject_system(state: State) -> State:
    msgs = state["messages"]
    history = state.get("history") or ""
    user_id = cliente_id or state.get("cliente_id") or "anon"
    session_id = session_id or state.get("session_id")

    system_content = SYSTEM_PROMPT

    if history:
        system_content = f"{SYSTEM_PROMPT}\n\nContexto recente do cliente:\n{history}"

    if not msgs or msgs[0].type != "system":
        msgs = [SystemMessage(content=system_content)] + msgs
    else:
        msgs[0] = SystemMessage(content=system_content)

    return {"messages": msgs, "history": history, "cliente_id": user_id, "session_id": session_id}


def save_context(state: State) -> State:
    """Persiste mensagens do diálogo no Qdrant."""
    if memory is None:
        return state

    try:
        user_id = cliente_id or state.get("cliente_id") or "anon"
        new_messages: List[Dict[str, str]] = []
        for msg in state["messages"]:
            if msg.type in ("human", "ai"):
                new_messages.append({"role": msg.type, "content": msg.content})

        memory.store_messages(user_id=user_id, messages=new_messages)
        print(f"[SVIM] Stored {len(new_messages)} messages for user_id={user_id}")
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

graph = builder.compile()
