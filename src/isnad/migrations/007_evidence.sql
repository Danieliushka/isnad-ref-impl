-- Migration 007: Evidence submissions from external agents (Hash Agent / SkillFence)

CREATE TABLE IF NOT EXISTS evidence (
    id SERIAL PRIMARY KEY,
    evidence_id TEXT UNIQUE NOT NULL,
    agent_id TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL DEFAULT 'security_scan',
    payload JSONB NOT NULL DEFAULT '{}',
    signature TEXT NOT NULL,
    public_key TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_error TEXT,
    score_impact FLOAT DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_evidence_agent ON evidence(agent_id);
CREATE INDEX IF NOT EXISTS idx_evidence_audit ON evidence(audit_id);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_evidence_submitted ON evidence(submitted_at DESC);
