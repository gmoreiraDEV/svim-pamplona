import json
from datetime import datetime
from typing import Any, Dict, Optional

from psycopg import Connection


def upsert_session(
    conn: Connection,
    user_identifier: str,
    session_id: str,
    status: str = "open",
) -> None:
    """
    Cria ou atualiza uma sessão, mantendo last_used_at/updated_at.
    """
    if not user_identifier or not session_id:
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO svim_sessions (user_identifier, session_id, status, last_used_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (session_id)
            DO UPDATE SET
              status = EXCLUDED.status,
              last_used_at = NOW(),
              updated_at = NOW();
            """,
            (user_identifier, session_id, status),
        )


def log_interaction(
    conn: Connection,
    user_id: Optional[str],
    session_id: Optional[str],
    intent: Optional[str],
    request_json: Dict[str, Any],
    response_json: Dict[str, Any],
) -> None:
    """
    Registra uma interação em interaction_logs.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO interaction_logs (user_id, session_id, intent, request_json, response_json, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s);
            """,
            (
                user_id,
                session_id,
                intent,
                json.dumps(request_json, ensure_ascii=False),
                json.dumps(response_json, ensure_ascii=False),
                datetime.utcnow(),
            ),
        )
