# Banco de Dados – SVIM Pamplona

Este documento resume o schema usado pelo agente Maria para sessões e logs, além de como aplicar migrations e configurar conexão.

## Conexão
- `DATABASE_URL`: usada pela aplicação (agent) para gravar sessões e interações.
- `DATABASE_URL_MAKE`: usada pelo Makefile para rodar migrations (pode ser igual à `DATABASE_URL`).

Formatos aceitos (psql): `postgresql://user:pass@host:port/dbname`

## Migrations
- Local das migrations: `sql/`
- Comandos:
  - Aplicar todas (ordem numérica): `make db-migrate`
  - Aplicar uma específica: `make db-migrate-one MIGRATION=sql/XX_nome.sql`
- O Make carrega `.env` automaticamente (precisa ter `DATABASE_URL_MAKE`).

## Tabelas

### svim_sessions
- `id` (UUID, PK): identificador interno.
- `client_id` (TEXT): identificador de cliente (nome histórico).
- `user_identifier` (TEXT): identificador do usuário (ex: `CLIENT_ID` do fluxo); adicionada em migration posterior para alinhar com o código.
- `session_id` (TEXT, UNIQUE): ID externo da sessão (ex: `SESSION_ID` do orquestrador).
- `status` (TEXT): `open` ou `closed`.
- `created_at` (TIMESTAMPTZ): criação.
- `updated_at` (TIMESTAMPTZ): última atualização de metadados.
- `last_used_at` (TIMESTAMPTZ): última interação na sessão.
- Índices: `idx_svim_sessions_client_id`, `idx_svim_sessions_user_identifier`, `idx_svim_sessions_last_used`.
- Comentário: "Sessões de conversa; cada linha identifica uma sessão única para um usuário."

### interaction_logs
- `id` (BIGSERIAL, PK): identificador do log.
- `client_id` (TEXT): identificador de cliente (nome histórico).
- `user_id` (TEXT): identificador do usuário (ex: `CLIENT_ID` do fluxo); adicionada em migration posterior para alinhar com o código.
- `session_id` (TEXT): identificador da sessão (ex: `SESSION_ID`).
- `intent` (TEXT): nome da intent inferida (pode ser null).
- `request_json` (JSONB): payload recebido pelo agente.
- `response_json` (JSONB): resposta do agente.
- `created_at` (TIMESTAMPTZ): criação do log.
- Índice: `idx_interaction_logs_client_session`, `idx_interaction_logs_user_session`.
- Comentário: "Log de interações do agente; armazena request/response por usuário e sessão."

## Observações de compatibilidade
- As primeiras migrations usavam `client_id`. A migration `sql/02_alter_add_user_columns.sql` adiciona `user_identifier`/`user_id` sem remover as colunas antigas, para compatibilidade.
- O código atual usa `user_identifier` (sessões) e `user_id` (logs); mantenha `CLIENT_ID`/`SESSION_ID` no fluxo para chavear a memória/logs.
