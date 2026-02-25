-- Migration 002: Agent registration fields
-- Adds agent_type, contact_email to agents table
-- Adds agent_api_keys table for per-agent API keys

ALTER TABLE agents ADD COLUMN IF NOT EXISTS agent_type TEXT DEFAULT 'autonomous';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS contact_email TEXT;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS api_key_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_agents_api_key ON agents(api_key_hash);
