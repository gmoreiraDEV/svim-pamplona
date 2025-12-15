CREATE TABLE IF NOT EXISTS svim_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'open' 
        CHECK (status IN ('open', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_svim_sessions_client_id
    ON svim_sessions (client_id);

CREATE INDEX IF NOT EXISTS idx_svim_sessions_last_used
    ON svim_sessions (last_used_at);

COMMENT ON TABLE svim_sessions IS 'Sessões de conversa; cada linha identifica uma sessão única para um usuário.';
COMMENT ON COLUMN svim_sessions.id IS 'UUID interno da sessão.';
COMMENT ON COLUMN svim_sessions.client_id IS 'Identificador do usuário (ex: CLIENT_ID).';
COMMENT ON COLUMN svim_sessions.session_id IS 'ID externo da sessão (ex: SESSION_ID compartilhado pelo orquestrador).';
COMMENT ON COLUMN svim_sessions.status IS 'Estado da sessão: open ou closed.';
COMMENT ON COLUMN svim_sessions.created_at IS 'Timestamp de criação da sessão.';
COMMENT ON COLUMN svim_sessions.updated_at IS 'Timestamp da última atualização de metadados.';
COMMENT ON COLUMN svim_sessions.last_used_at IS 'Última interação registrada nesta sessão.';
