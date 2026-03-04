-- Scoring Engine v3 schema additions

ALTER TABLE agents ADD COLUMN IF NOT EXISTS trust_confidence FLOAT DEFAULT 0.0;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS trust_tier VARCHAR(20) DEFAULT 'UNKNOWN';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS last_scored_at TIMESTAMPTZ;

-- Add is_negative to attestations if not exists
ALTER TABLE attestations ADD COLUMN IF NOT EXISTS is_negative BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS score_audit (
    id SERIAL PRIMARY KEY,
    agent_id UUID REFERENCES agents(id),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    final_score INT,
    confidence FLOAT,
    tier VARCHAR(20),
    provenance_raw FLOAT,
    track_record_raw FLOAT,
    presence_raw FLOAT,
    endorsements_raw FLOAT,
    decay_factor FLOAT,
    data_snapshot JSONB
);

CREATE INDEX IF NOT EXISTS idx_score_audit_agent ON score_audit(agent_id);
CREATE INDEX IF NOT EXISTS idx_score_audit_computed ON score_audit(computed_at DESC);
