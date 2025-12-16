import os
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
from uuid import uuid4

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

def create_qdrant_client(config: Optional[Dict[str, Any]] = None) -> QdrantClient:
    """
    Cria um cliente Qdrant usando URL e API Key do config ou do ambiente.

    Prioridade:
    1) config["qdrant_url"] / config["qdrant_api_key"]
    2) variáveis de ambiente QDRANT_URL / QDRANT_API_KEY
    """
    config = config or {}

    url = config.get("qdrant_url") or os.getenv("QDRANT_URL")
    api_key = config.get("qdrant_api_key") or os.getenv("QDRANT_API_KEY")

    if not url:
        raise ValueError("Qdrant URL não definida (use config['qdrant_url'] ou QDRANT_URL).")

    client = QdrantClient(
        url=url,
        api_key=api_key,
    )

    return client


def ensure_qdrant_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int = 1536,
    distance: Distance = Distance.COSINE,
) -> None:
    collections = client.get_collections()
    existing = {c.name for c in collections.collections}

    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
        )

    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="user_id",
            field_schema={"type": "keyword"},
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            return
        print(f"Qdrant index error: {e}")


class QdrantMemory:
    """Armazena e recupera contexto de conversa no Qdrant."""

    def __init__(
        self,
        collection_name: str = "svim_conversations",
        embedding_model: str = "text-embedding-3-small",
        vector_size: int = 1536,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.client = create_qdrant_client(config)
        ensure_qdrant_collection(self.client, collection_name, vector_size=vector_size)
        self._openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _embed(self, texts: List[str]) -> List[List[float]]:
        resp = self._openai.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [item.embedding for item in resp.data]

    def get_user_context(self, user_id: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Busca os K itens de memória mais relevantes de um usuário."""
        query_vector = self._embed([query or ""])[0]

        query_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )

        # Compatibilidade com diferentes versões do cliente Qdrant
        if hasattr(self.client, "search"):
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=k,
                with_payload=True,
                query_filter=query_filter,
            )
        elif hasattr(self.client, "search_points"):
            results = self.client.search_points(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=k,
                with_payload=True,
                query_filter=query_filter,
            ).points
        else:
            raise AttributeError("QdrantClient não possui métodos search/search_points")

        payloads = [r.payload for r in results if r.payload]
        return [
            {"role": p.get("role", "user"), "content": p.get("content", "")}
            for p in payloads
        ]

    def store_messages(self, user_id: str, messages: List[Dict[str, str]], session_id: str | None = None) -> None:
        """Persiste mensagens (role/content) no Qdrant."""
        if not messages:
            return

        vectors = self._embed([f"{m.get('role')}: {m.get('content','')}" for m in messages])
        now = datetime.now(UTC).isoformat()

        points = []
        for msg, vector in zip(messages, vectors):
            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                        "created_at": now,
                    },
                )
            )
        print(f"Storing {len(points)} messages for user {user_id} in Qdrant.")
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )
