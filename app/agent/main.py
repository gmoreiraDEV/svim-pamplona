import os
import json
import asyncio
import traceback
from typing import Any, Dict
from kestra import Kestra
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from app.agent.graph import graph

load_dotenv()


async def run_once() -> Dict[str, Any]:
    message = os.environ.get("MESSAGE")

    if not message:
        raise ValueError("SVIM_MESSAGE não foi definido nas variáveis de ambiente")

    try:
        state = await graph.ainvoke({
            "messages": [HumanMessage(content=message)],
            "cliente_id": os.getenv("CLIENT_ID"),
        })

        messages = state.get("messages", [])
        ai_msg = next((m for m in reversed(messages) if getattr(m, "type", "") == "ai"), None)

        return {
            "reply": ai_msg.content if ai_msg else None,
            "messages": [{"type": m.type, "content": m.content} for m in messages],
        }
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
