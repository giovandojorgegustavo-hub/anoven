-- ==========================================================
-- Migration: shared_projects_001_create.sql
-- Change: anoven-shared-projects
-- Date: 2026-06-09
-- Purpose: Create project_members, project_invitations,
--          project_mentors; add author_user_id to messages,
--          billed_user_id to cost_events (DDL only — no data)
-- Idempotent: all CREATE TABLE/INDEX use IF NOT EXISTS;
--             all ALTER ADD COLUMN use IF NOT EXISTS (O4.3)
-- ==========================================================

BEGIN;

-- ============================================================
-- 1. project_members
-- ============================================================
CREATE TABLE IF NOT EXISTS project_members (
  id                  SERIAL PRIMARY KEY,
  project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role                VARCHAR(16) NOT NULL CHECK (role IN ('owner','member')),
  joined_at           TIMESTAMP NOT NULL DEFAULT NOW(),
  invited_by_user_id  INTEGER NOT NULL REFERENCES users(id),
  CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_project_members_user_id
  ON project_members(user_id);
CREATE INDEX IF NOT EXISTS ix_project_members_project_role
  ON project_members(project_id, role);

-- ============================================================
-- 2. project_invitations
-- ============================================================
CREATE TABLE IF NOT EXISTS project_invitations (
  id                  SERIAL PRIMARY KEY,
  project_id          INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  invited_user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invited_by_user_id  INTEGER NOT NULL REFERENCES users(id),
  status              VARCHAR(16) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','accepted','rejected','expired','revoked')),
  expires_at          TIMESTAMP NOT NULL,
  created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
  responded_at        TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_invitations_pending
  ON project_invitations(project_id, invited_user_id)
  WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_project_invitations_invited_user_status
  ON project_invitations(invited_user_id, status);

-- ============================================================
-- 3. project_mentors
-- ============================================================
CREATE TABLE IF NOT EXISTS project_mentors (
  id                 SERIAL PRIMARY KEY,
  project_id         INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  mentor_id          INTEGER NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
  added_by_user_id   INTEGER NOT NULL REFERENCES users(id),
  added_at           TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_project_mentors_project_mentor UNIQUE (project_id, mentor_id)
);
CREATE INDEX IF NOT EXISTS ix_project_mentors_project
  ON project_mentors(project_id);

-- ============================================================
-- 4. messages.author_user_id (NULL = assistant turn)
-- ============================================================
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_messages_author_created
  ON messages(author_user_id, created_at);

-- ============================================================
-- 5. cost_events.billed_user_id (owner when shared project)
-- ============================================================
ALTER TABLE cost_events
  ADD COLUMN IF NOT EXISTS billed_user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS ix_cost_events_billed_user
  ON cost_events(billed_user_id, created_at);

COMMIT;
