-- PARTIAL migration: per-mentor-model-assignment-v1
-- Date: 2026-06-08 (revised after DB inspection)
-- Skips mentors.model (already exists from prior session) and adds only what's missing.

BEGIN;

-- Add CHECK constraint to existing mentors.model column (if not already constrained)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'mentors_model_whitelist_check'
  ) THEN
    ALTER TABLE mentors
      ADD CONSTRAINT mentors_model_whitelist_check
      CHECK (
        model IS NULL OR model IN (
          'claude-haiku-4-5-20251001',
          'claude-haiku-4-5',
          'claude-sonnet-4-6',
          'claude-opus-4-7',
          'claude-opus-4-8'
        )
      );
  END IF;
END $$;

-- Add users.model_override (does NOT exist yet)
ALTER TABLE users
  ADD COLUMN model_override VARCHAR(60) NULL
  CHECK (
    model_override IS NULL OR model_override IN (
      'claude-haiku-4-5-20251001',
      'claude-haiku-4-5',
      'claude-sonnet-4-6',
      'claude-opus-4-7',
      'claude-opus-4-8'
    )
  );

-- Create model_resolution_audit (does NOT exist yet)
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
