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

    # Índices para filtros rápidos
    for field in ("user_id", "session_id", "created_at"):
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema={"type": "keyword"},
            )
        except Exception as e:
            if "already exists" in str(e).lower():
                continue
            print(f"Qdrant index error ({field}): {e}")



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

    def _is_valid_id(self, value: Optional[str]) -> bool:
        return bool(value and value.strip() and value not in ("anon", "anon-session"))

    def get_recent_context(
        self,
        session_id: Optional[str],
        user_id: Optional[str],
        k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recupera as últimas K mensagens usando:
        - session_id (se presente)
        - senão user_id
        """
        must = []

        if self._is_valid_id(session_id):
            must.append(FieldCondition(key="session_id", match=MatchValue(value=session_id)))
        elif self._is_valid_id(user_id):
            must.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))
        else:
            return []

        query_filter = Filter(must=must)

        # Compatibilidade com versões diferentes do client
        if hasattr(self.client, "scroll"):
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                with_payload=True,
                limit=max(k * 5, 50),
            )
        elif hasattr(self.client, "scroll_points"):
            points = self.client.scroll_points(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                with_payload=True,
                limit=max(k * 5, 50),
            ).points
        else:
            raise AttributeError("QdrantClient não possui métodos scroll/scroll_points")

        payloads = [p.payload for p in points if getattr(p, "payload", None)]

        # Ordenar por created_at (ISO) e pegar os últimos k
        payloads.sort(key=lambda x: x.get("created_at", ""))
        payloads = payloads[-k:]

        return [{"role": p.get("role", "user"), "content": p.get("content", "")} for p in payloads]

    def get_hybrid_context(
        self,
        session_id: Optional[str],
        user_id: Optional[str],
        query: str,
        recent_k: int = 6,
        semantic_k: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Memória híbrida:
        - 1) Recência: últimas mensagens (prioriza session_id; fallback user_id)
        - 2) Semântica: mensagens mais relevantes para 'query' (preferencialmente por user_id)
        Retorna uma lista final sem duplicatas.
        """
        # 1) Recente (conversa)
        recent = self.get_recent_context(session_id=session_id, user_id=user_id, k=recent_k)

        # 2) Semântico (lembranças antigas úteis)
        semantic: List[Dict[str, Any]] = []
        if query and query.strip():
            # Aqui é importante: semântica por USER_ID (memória "do cliente", atravessa sessões)
            if self._is_valid_id(user_id):
                semantic = self.get_user_context(user_id=user_id, query=query, k=semantic_k)
            else:
                # se não tiver user_id válido, tenta semântica por session_id (melhor que nada)
                # (usa o mesmo método, mas com "user_id" = session_id não rola porque o filtro do get_user_context é por user_id)
                # então, nesse fallback, a gente simplesmente não faz semântico.
                semantic = []

        # Deduplicação (role+content)
        seen = set()
        merged: List[Dict[str, Any]] = []

        def _add(msg: Dict[str, Any]):
            content = msg.get("content")
            if isinstance(content, list):
                content = " ".join(str(item) for item in content)
            elif content is None:
                content = ""
            else:
                content = str(content)

            key = (msg.get("role", ""), content.strip())
            if not key[1]:
                return
            if key in seen:
                return
            seen.add(key)
            merged.append({"role": key[0], "content": key[1]})

        # Ordem: primeiro recência, depois semântica (sem repetir)
        for m in recent:
            _add(m)
        for m in semantic:
            _add(m)

        return merged

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
