-- Adiciona colunas compatíveis com o código atual, sem alterar migrações anteriores

-- sviim_sessions: adiciona user_identifier (mantém client_id existente)
ALTER TABLE svim_sessions
    ADD COLUMN IF NOT EXISTS user_identifier TEXT;

CREATE INDEX IF NOT EXISTS idx_svim_sessions_user_identifier
    ON svim_sessions (user_identifier);

COMMENT ON COLUMN svim_sessions.user_identifier IS 'Identificador do usuário (ex: CLIENT_ID).';

-- interaction_logs: adiciona user_id (mantém client_id existente)
ALTER TABLE interaction_logs
    ADD COLUMN IF NOT EXISTS user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_interaction_logs_user_session
    ON interaction_logs (user_id, session_id);

COMMENT ON COLUMN interaction_logs.user_id IS 'Identificador do usuário (mesmo valor de CLIENT_ID quando disponível).';
