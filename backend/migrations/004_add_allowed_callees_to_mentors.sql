-- Migration 004: Add allowed_callees and max_callees_per_turn to mentors table
-- Cycle: call-mentor-multi-agent
-- Date: 2026-06-08
-- Constitution: O4.3 (idempotent DDL — ADD COLUMN IF NOT EXISTS)
-- Rollback: ALTER TABLE mentors DROP COLUMN IF EXISTS allowed_callees;
--           ALTER TABLE mentors DROP COLUMN IF EXISTS max_callees_per_turn;

ALTER TABLE mentors
  ADD COLUMN IF NOT EXISTS allowed_callees JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE mentors
  ADD COLUMN IF NOT EXISTS max_callees_per_turn INTEGER NULL;
