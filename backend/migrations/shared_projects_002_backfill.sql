-- ==========================================================
-- Migration: shared_projects_002_backfill.sql
-- Change: anoven-shared-projects
-- Date: 2026-06-09
-- Purpose: Backfill messages.author_user_id and seed
--          project_members owner row per existing project.
-- Idempotent: UPDATE WHERE IS NULL + INSERT ON CONFLICT DO NOTHING (O4.3)
-- Run AFTER: shared_projects_001_create.sql
-- ==========================================================

BEGIN;

-- ============================================================
-- 6. Backfill messages.author_user_id for role='user' rows
--    Source: conversations.user_id (who owns the conversation)
-- ============================================================
UPDATE messages m
SET author_user_id = c.user_id
FROM conversations c
WHERE m.conversation_id = c.id
  AND m.role = 'user'
  AND m.author_user_id IS NULL;

-- ============================================================
-- 7. Seed project_members owner row per existing project
--    (uses project.user_id as both member and inviter)
-- ============================================================
INSERT INTO project_members (project_id, user_id, role, joined_at, invited_by_user_id)
SELECT p.id, p.user_id, 'owner', p.created_at, p.user_id
FROM projects p
ON CONFLICT (project_id, user_id) DO NOTHING;

COMMIT;
