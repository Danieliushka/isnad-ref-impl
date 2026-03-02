-- Migration 005: Behavioral signals table for webhook integrations (PayLock, etc.)

CREATE TABLE IF NOT EXISTS behavioral_signals (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    source TEXT NOT NULL,            -- 'paylock', 'manual', etc.
    event_type TEXT NOT NULL,        -- 'escrow_created', 'escrow_released', 'escrow_disputed'
    contract_id TEXT,
    amount_sol DOUBLE PRECISION,
    metadata JSONB DEFAULT '{}',
    created_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_behavioral_signals_agent ON behavioral_signals(agent_id);
CREATE INDEX IF NOT EXISTS idx_behavioral_signals_source ON behavioral_signals(source);
CREATE INDEX IF NOT EXISTS idx_behavioral_signals_event ON behavioral_signals(event_type);
CREATE INDEX IF NOT EXISTS idx_behavioral_signals_created ON behavioral_signals(created_at);
