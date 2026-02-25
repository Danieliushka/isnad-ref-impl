-- Migration 001: Initial schema (PostgreSQL)
-- Timestamp fields use TEXT to store ISO-8601 strings (backwards compat with SQLite era)

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT,
    public_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    is_certified BOOLEAN DEFAULT FALSE,
    trust_score DOUBLE PRECISION DEFAULT 0.0,
    last_checked TEXT,
    -- New fields for platform scanning
    platforms JSONB DEFAULT '[]',
    capabilities JSONB DEFAULT '[]',
    offerings TEXT,
    avatar_url TEXT,
    last_scanned TEXT
);

CREATE TABLE IF NOT EXISTS attestations (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    witness_id TEXT NOT NULL,
    task TEXT NOT NULL,
    evidence_uri TEXT DEFAULT '',
    signature TEXT,
    witness_pubkey TEXT,
    timestamp TEXT NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS certifications (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    category_scores JSONB DEFAULT '{}',
    certified_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    badge_hash TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    owner_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rate_limit INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS trust_checks (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    score DOUBLE PRECISION,
    report JSONB DEFAULT '{}',
    requester_ip TEXT
);

CREATE TABLE IF NOT EXISTS platform_data (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    platform_name TEXT NOT NULL,
    platform_url TEXT,
    raw_data JSONB DEFAULT '{}',
    metrics JSONB DEFAULT '{}',
    last_fetched TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_attestations_subject ON attestations(subject_id);
CREATE INDEX IF NOT EXISTS idx_attestations_witness ON attestations(witness_id);
CREATE INDEX IF NOT EXISTS idx_attestations_task ON attestations(task);
CREATE INDEX IF NOT EXISTS idx_attestations_timestamp ON attestations(timestamp);
CREATE INDEX IF NOT EXISTS idx_certifications_agent ON certifications(agent_id);
CREATE INDEX IF NOT EXISTS idx_certifications_expires ON certifications(expires_at);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_trust_checks_agent ON trust_checks(agent_id);
CREATE INDEX IF NOT EXISTS idx_trust_checks_time ON trust_checks(requested_at);
CREATE INDEX IF NOT EXISTS idx_platform_data_agent ON platform_data(agent_id);
CREATE INDEX IF NOT EXISTS idx_platform_data_platform ON platform_data(platform_name);
