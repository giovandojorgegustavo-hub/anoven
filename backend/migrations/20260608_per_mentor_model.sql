-- Migration: per-mentor-model-assignment-v1
-- Date: 2026-06-08
-- SDD: sdd/per-mentor-model-assignment-v1 (engram obs #1291-#1294)
-- Reversible: see 20260608_per_mentor_model_rollback.sql

BEGIN;

-- Whitelist of valid Claude model IDs (synced with app/services/model_resolver.py MODEL_WHITELIST)
-- Update both in lockstep when Anthropic releases new models.

ALTER TABLE mentors
  ADD COLUMN model TEXT NULL
  CHECK (
    model IS NULL OR model IN (
      'claude-haiku-4-5-20251001',
      'claude-haiku-4-5',
      'claude-sonnet-4-6',
      'claude-opus-4-7',
      'claude-opus-4-8'
    )
  );

ALTER TABLE users
  ADD COLUMN model_override TEXT NULL
  CHECK (
    model_override IS NULL OR model_override IN (
      'claude-haiku-4-5-20251001',
      'claude-haiku-4-5',
      'claude-sonnet-4-6',
      'claude-opus-4-7',
      'claude-opus-4-8'
    )
  );

CREATE TABLE model_resolution_audit (
  id BIGSERIAL PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  user_id INTEGER NOT NULL,
  mentor_id INTEGER NOT NULL,
  conversation_id INTEGER NULL,
  effective_model TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('user_override', 'mentor_default', 'system_default'))
);

CREATE INDEX idx_audit_user_mentor_ts ON model_resolution_audit(user_id, mentor_id, timestamp DESC);
CREATE INDEX idx_audit_ts ON model_resolution_audit(timestamp DESC);

COMMIT;
