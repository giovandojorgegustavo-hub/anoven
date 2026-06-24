-- Rollback: per-mentor-model-assignment-v1
-- Date: 2026-06-08
-- Reverses: 20260608_per_mentor_model.sql

BEGIN;

DROP TABLE IF EXISTS model_resolution_audit;

ALTER TABLE users DROP COLUMN IF EXISTS model_override;

ALTER TABLE mentors DROP COLUMN IF EXISTS model;

COMMIT;
