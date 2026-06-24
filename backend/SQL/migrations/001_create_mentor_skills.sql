-- Migration 001: Create mentor_skills table
-- Phase 1 — Skills Markdown Injection
-- Idempotent: uses IF NOT EXISTS

CREATE TABLE IF NOT EXISTS mentor_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mentor_id INTEGER NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
    slug VARCHAR(80) NOT NULL,
    title VARCHAR(160) NOT NULL,
    content TEXT NOT NULL,
    triggers TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (mentor_id, slug)
);

CREATE INDEX IF NOT EXISTS ix_mentor_skills_mentor_id
    ON mentor_skills(mentor_id);

CREATE INDEX IF NOT EXISTS ix_mentor_skills_enabled
    ON mentor_skills(mentor_id, enabled);
