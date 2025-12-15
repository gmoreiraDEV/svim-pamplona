CREATE TABLE IF NOT EXISTS interaction_logs (
  id           BIGSERIAL PRIMARY KEY,
  client_id      TEXT,
  session_id   TEXT,
  intent       TEXT,
  request_json JSONB,
  response_json JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interaction_logs_client_session ON interaction_logs (client_id, session_id);

COMMENT ON TABLE interaction_logs IS 'Log de interações do agente; armazena request/response por cliente e sessão.';
COMMENT ON COLUMN interaction_logs.id IS 'Chave primária sequencial do log.';
COMMENT ON COLUMN interaction_logs.client_id IS 'Identificador do cliente (mesmo valor de CLIENT_ID quando disponível).';
COMMENT ON COLUMN interaction_logs.session_id IS 'Identificador da sessão (SESSION_ID ou fallback para CLIENT_ID).';
COMMENT ON COLUMN interaction_logs.intent IS 'Nome da intent inferida (pode ficar null se não detectada).';
COMMENT ON COLUMN interaction_logs.request_json IS 'Payload recebido pelo agente (JSON bruto).';
COMMENT ON COLUMN interaction_logs.response_json IS 'Resposta do agente (JSON bruto).';
COMMENT ON COLUMN interaction_logs.created_at IS 'Timestamp de criação do log.';
