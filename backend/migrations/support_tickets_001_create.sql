-- Migration: backend/migrations/support_tickets_001_create.sql
-- Change: anoven-support-tickets
-- Date: 2026-06-08
-- Pre-DDL backup (O4.4): /tmp/anoven_schema_backup_pre_support_tickets_20260608-204032.sql
--
-- Two-step attachment flow: POST /api/tickets → ticket_id → POST /api/tickets/{id}/attachments
-- Rate limit: 5 tickets/hour/user (v1)
-- No cron cleanup in v1 (out of scope)
--
-- ROLLBACK (O4.5):
--   BEGIN;
--   DROP TRIGGER IF EXISTS trg_support_tickets_updated_at ON support_tickets;
--   DROP FUNCTION IF EXISTS touch_support_tickets_updated_at();
--   DROP TABLE IF EXISTS ticket_attachments;
--   DROP TABLE IF EXISTS support_tickets;
--   COMMIT;

BEGIN;

-- Optional admin role grant for christianeddych (idempotent, O4.3)
-- christianeddych@gmail.com was NOT found as admin at time of migration
UPDATE users SET role = 'admin'
WHERE email = 'christianeddych@gmail.com'
  AND role != 'admin';

CREATE TABLE IF NOT EXISTS support_tickets (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER NULL REFERENCES conversations(id) ON DELETE SET NULL,
    mentor_id       INTEGER NULL REFERENCES mentors(id) ON DELETE SET NULL,
    ticket_type     VARCHAR(16) NOT NULL,
    title           VARCHAR(200) NOT NULL,
    description     TEXT NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'open',
    admin_response  TEXT NULL,
    admin_user_id   INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at    TIMESTAMPTZ NULL,
    closed_at       TIMESTAMPTZ NULL,
    CONSTRAINT support_tickets_type_chk
        CHECK (ticket_type IN ('bug','mejora','pregunta','otro')),
    CONSTRAINT support_tickets_status_chk
        CHECK (status IN ('open','in_progress','closed')),
    CONSTRAINT support_tickets_title_len_chk
        CHECK (char_length(title) BETWEEN 3 AND 200),
    CONSTRAINT support_tickets_description_len_chk
        CHECK (char_length(description) BETWEEN 10 AND 5000),
    CONSTRAINT support_tickets_closed_response_chk
        CHECK (status <> 'closed' OR admin_response IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id      ON support_tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status       ON support_tickets(status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_created_at   ON support_tickets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_conversation ON support_tickets(conversation_id) WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_support_tickets_mentor       ON support_tickets(mentor_id) WHERE mentor_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_support_tickets_admin_inbox  ON support_tickets(status, created_at DESC) WHERE status IN ('open','in_progress');

CREATE TABLE IF NOT EXISTS ticket_attachments (
    id             BIGSERIAL PRIMARY KEY,
    ticket_id      BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_path      TEXT NOT NULL,
    original_name  VARCHAR(255) NOT NULL,
    mime_type      VARCHAR(64) NOT NULL,
    size_bytes     INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ticket_attachments_mime_chk
        CHECK (mime_type IN ('image/png','image/jpeg','image/webp')),
    CONSTRAINT ticket_attachments_size_chk
        CHECK (size_bytes BETWEEN 1 AND 5242880)
);

CREATE INDEX IF NOT EXISTS idx_ticket_attachments_ticket_id ON ticket_attachments(ticket_id);

-- updated_at trigger
CREATE OR REPLACE FUNCTION touch_support_tickets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_support_tickets_updated_at ON support_tickets;
CREATE TRIGGER trg_support_tickets_updated_at
    BEFORE UPDATE ON support_tickets
    FOR EACH ROW
    EXECUTE FUNCTION touch_support_tickets_updated_at();

COMMIT;
