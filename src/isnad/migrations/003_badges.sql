-- Migration 003: Badge system
-- Agents can earn badges (e.g. "isnad Verified") based on trust criteria

CREATE TABLE IF NOT EXISTS badges (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    badge_type TEXT NOT NULL DEFAULT 'verified',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'revoked')),
    granted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id, badge_type)
);

CREATE INDEX IF NOT EXISTS idx_badges_agent ON badges(agent_id);
CREATE INDEX IF NOT EXISTS idx_badges_status ON badges(status);
