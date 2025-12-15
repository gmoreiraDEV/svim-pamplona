import os
from contextlib import contextmanager
from typing import Iterator

import psycopg


def _get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        raise ValueError("DATABASE_URL não definido")
    return db_url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """
    Context manager para obter conexão com autocommit.
    Uso:
        with get_connection() as conn:
            ...
    """
    conn = psycopg.connect(_get_db_url(), autocommit=True)
    try:
        yield conn
    finally:
        conn.close()
