import os
import uuid
from datetime import datetime, UTC

import pytest

from app.utils.db import get_connection
from app.utils.session_logger import log_interaction, upsert_session
from app.utils.qdrant import QdrantMemory


pytestmark = pytest.mark.integration


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"Missing env var: {name}")
    return value


def _require_any_env(*names: str) -> str:
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    pytest.skip(f"Missing env vars: {', '.join(names)}")
    return ""


def test_db_session_and_log_roundtrip():
    db_url = _require_any_env("DATABASE_URL", "DATABASE_URL_MAKE")
    # Se vier de DATABASE_URL_MAKE, propaga para DATABASE_URL para o client
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = db_url

    user_id = f"test-user-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    print(f"[DB] Using user_id={user_id} session_id={session_id}")

    with get_connection() as conn:
        upsert_session(conn, user_identifier=user_id, session_id=session_id, status="open")
        log_interaction(
            conn,
            user_id=user_id,
            session_id=session_id,
            intent="test_intent",
            request_json={"ts": datetime.now(datetime.UTC).isoformat(), "msg": "hello"},
            response_json={"reply": "hi"},
        )

        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM svim_sessions WHERE session_id = %s", (session_id,)
            )
            row = cur.fetchone()
            assert row is not None, "session not found in DB"
            assert row[0] == "open"
            print(f"[DB] session status={row[0]}")

            cur.execute(
                "SELECT intent, request_json->>'msg', response_json->>'reply' "
                "FROM interaction_logs WHERE session_id = %s ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            row = cur.fetchone()
            assert row is not None, "log not found in DB"
            assert row[0] == "test_intent"
            assert row[1] == "hello"
            assert row[2] == "hi"
            print(f"[DB] log intent={row[0]} request_msg={row[1]} response_reply={row[2]}")


def test_qdrant_memory_roundtrip():
    _require_env("QDRANT_URL")
    # API key may be optional depending on deployment

    user_id = f"test-user-{uuid.uuid4()}"
    print(f"[QDRANT] Using user_id={user_id}")
    mem = QdrantMemory()

    messages = [
        {"role": "human", "content": "Oi, quero cortar"},
        {"role": "ai", "content": "Claro, qual horário prefere?"},
    ]
    mem.store_messages(user_id=user_id, messages=messages)
    print("[QDRANT] Stored messages")

    ctx = mem.get_user_context(user_id=user_id, query="corte", k=2)
    print(f"[QDRANT] Retrieved context: {ctx}")
    roles = [m["role"] for m in ctx]
    contents = [m["content"] for m in ctx]

    assert "human" in roles, "human message not retrieved"
    assert any("cortar" in c.lower() for c in contents), "stored content not retrieved"
