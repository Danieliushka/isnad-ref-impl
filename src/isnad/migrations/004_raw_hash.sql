-- Migration 004: Add raw_hash column to trust_checks for commit-reveal-intent verification
-- Ref: DAN-48, Hoyte 2024 commit-reveal attacks
ALTER TABLE trust_checks ADD COLUMN IF NOT EXISTS raw_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_trust_checks_raw_hash ON trust_checks(raw_hash);
