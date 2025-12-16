import os
import json
import asyncio
import traceback
from typing import Any, Dict
from kestra import Kestra
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from app.agent.graph import graph
from app.utils.db import get_connection
from app.utils.session_logger import log_interaction, upsert_session

load_dotenv()


async def run_once() -> Dict[str, Any]:
    message = os.environ.get("MESSAGE")

    if not message:
        raise ValueError("SVIM_MESSAGE não foi definido nas variáveis de ambiente")

    client_id = os.getenv("CLIENT_ID")
    session_id = os.getenv("SESSION_ID")

    try:
        state = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=message)],
                "cliente_id": client_id,
                "session_id": session_id,
            },
            config={
                "configurable": {
                    "thread_id": session_id or client_id or "anon",
                    "checkpoint_ns": "svim",  # separa namespace de checkpoints
                }
            },
        )

        messages = state.get("messages", [])
        ai_msg = next((m for m in reversed(messages) if getattr(m, "type", "") == "ai"), None)

        result = {
            "reply": ai_msg.content if ai_msg else None,
            "messages": [{"type": m.type, "content": m.content} for m in messages],
            "history": state.get("history"),
            "cliente_id": state.get("cliente_id"),
            "session_id": session_id,
        }

        if os.getenv("DATABASE_URL"):
            try:
                with get_connection() as conn:
                    upsert_session(conn, user_identifier=client_id or "unknown", session_id=session_id or "unknown")
                    log_interaction(
                        conn,
                        user_id=client_id,
                        session_id=session_id,
                        intent=None, 
                        request_json={"message": message, "cliente_id": client_id, "session_id": session_id},
                        response_json=result,
                    )
            except Exception as db_exc:
                print(f"[SVIM] DB log error: {db_exc}")

        return result
    finally:
        pass
    

def main():
  try:
    result = asyncio.run(run_once())
    Kestra.outputs(result)
    print(json.dumps(result, ensure_ascii=False))

  except Exception as e:
    print("PYTHON_CRASH:", e)
    traceback.print_exc()
    raise

if __name__ == "__main__":
  main()
