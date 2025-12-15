# AI Agent - SVIM Pamplona

## Folder structure

- `app/agent`: orquestra o agente Maria (grafo, ferramentas e entrypoint).
  - `graph.py`: define o grafo LangGraph e o prompt da Maria.
  - `tools.py`: ferramentas HTTP para listar/criar agendamentos e serviços.
  - `main.py`: entrypoint (`python -m app.agent.main`) que invoca o grafo.
- `app/utils/http_client.py`: cliente HTTP autenticado com validações básicas.
- `tests`: testes das tools com pytest.
- `workflows/_flows/svim/maria.yml`: fluxo do Kestra que roda o agente via Docker.
- `docs`: diagramas e intents.
- `requirements.in/requirements.txt`: dependências (gerado via `pip-compile`).
- `Dockerfile`: imagem usada pelo Kestra (Python 3.13 slim).
- `Makefile`: atalhos de build, testes e imagem.

## Database

- Não há persistência local neste projeto. O agente consome APIs externas definidas em `app/utils/http_client.py` (URLs e tokens via variáveis de ambiente).

## Docs

- [Diagramas e definições de projeto](./docs/diagrams_definitions.md)
- [Intents](./docs/intents.md)

## Pré-requisitos

- Python 3.13+
- pip
- Docker (para build da imagem usada no Kestra)

## Variáveis de ambiente

Use `.env` (copie de `.env.example` com `make env`) ou exporte antes de rodar:

- `OPENAI_API_KEY`: chave da OpenAI.
- `MODEL`: nome do modelo (ex: `gpt-4.1`).
- `URL_BASE`, `X_API_TOKEN`, `ESTABELECIMENTO_ID`: dados da API do salão.
- `MESSAGE`: mensagem do cliente que inicia a conversa.
- `SVIM`, `CLIENT_ID`, `CLIENT_NOME`, `CLIENT_WHATSAPP`: dados de contexto do cliente.
- Memória/Qdrant (opcional para histórico): `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` (default `svim_conversations`), `EMBEDDINGS_MODEL` (default `text-embedding-3-small`), `QDRANT_VECTOR_SIZE` (1536 para o modelo small, 3072 para o large).
- `HTTP_TIMEOUT` (opcional), `DATABASE_URL` (não usado localmente).

## Instalação

```bash
pip install -r requirements.txt
```

## Executar o agente localmente

```bash
# certifique-se de ter as variáveis exportadas ou em um .env
python3 -m app.agent.main
```

O retorno é um JSON com `reply` (mensagem da IA) e o histórico de `messages`.

## Testes

- Rodar testes das tools: `make test_tool` ou `python3 -m pytest -q tests/test_tools.py`
- Modo verboso: `make test_tool_verbose`

## Docker / Kestra

- Build da imagem: `make build-image` (ou `IMAGE_TAG=v0.0.X make build-image`)
- Push: `make push-image` ou `make build-push-image`
- O fluxo `workflows/_flows/svim/maria.yml` usa a imagem Docker e injeta as variáveis de ambiente para o Kestra.

## Outras tarefas

- Gerar `requirements.txt` a partir de `requirements.in`: `make compile-deps`
