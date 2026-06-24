-- ==========================================================
-- Rollback: shared_projects_rollback.sql
-- Change: anoven-shared-projects
-- Date: 2026-06-09
-- Purpose: Full schema rollback for anoven-shared-projects
--          migration. Safe to run if migration was partial.
-- WARNING: This drops all shared-project data. Use ONLY
--          after confirmed failure. Restore pg_dump backup
--          at /tmp/anoven_schema_backup_pre_shared_projects_*
--          if data integrity is in question.
-- O4.5 compliance: rollback SQL documented here.
-- ==========================================================

BEGIN;

-- Remove added columns first (before dropping tables they reference)
ALTER TABLE cost_events DROP COLUMN IF EXISTS billed_user_id;
ALTER TABLE messages    DROP COLUMN IF EXISTS author_user_id;

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS project_mentors    CASCADE;
DROP TABLE IF EXISTS project_invitations CASCADE;
DROP TABLE IF EXISTS project_members    CASCADE;

COMMIT;

-- After running this file:
-- 1. Restore .bak files for any modified app/*.py (none in Batch 1)
-- 2. Verify schema: \d messages (no author_user_id), \d cost_events (no billed_user_id)
-- 3. Confirm tables gone: \d project_members, \d project_invitations, \d project_mentors
