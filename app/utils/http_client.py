import os
import logging
import requests
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger(__name__)


class HttpClientError(Exception):
    """Erro específico para chamadas HTTP do agente SVIM."""


class HttpClient:
    """HTTP client com configuração fixa e validações de segurança."""

    def __init__(self) -> None:
        base_url = os.getenv("URL_BASE", "").rstrip("/")
        if not base_url:
            raise ValueError("URL_BASE não definida para o cliente HTTP da SVIM")
        self.base_url = base_url

        self.headers = {
            "X-Api-Key": os.getenv("X_API_TOKEN", ""),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "estabelecimentoId": os.getenv("ESTABELECIMENTO_ID", ""),
        }

        self.timeout = float(os.getenv("HTTP_TIMEOUT", 10))

    def _full_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            if not path.startswith(self.base_url):
                raise HttpClientError("URL não permitida pelo cliente padrão")
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        url = self._full_url(path)
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:  # pragma: no cover - comportamento de rede
            logger.error("HTTP client error", exc_info=exc)
            raise HttpClientError(str(exc))
        except ValueError as exc:  # pragma: no cover - JSON inválido
            logger.error("Invalid JSON from HTTP client", exc_info=exc)
            raise HttpClientError("INVALID_JSON_RESPONSE")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params or {})

    def post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("POST", path, json=json or {})


_default_client: Optional[HttpClient] = None


def get_http_client() -> HttpClient:
    global _default_client
    if _default_client is None:
        _default_client = HttpClient()
    return _default_client


__all__ = ["HttpClient", "HttpClientError", "get_http_client"]
