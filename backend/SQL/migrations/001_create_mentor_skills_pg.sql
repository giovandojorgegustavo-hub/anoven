-- Migration 001: Create mentor_skills table (PostgreSQL)
-- Phase 1 -- Skills Markdown Injection
-- Idempotent: uses IF NOT EXISTS

CREATE TABLE IF NOT EXISTS mentor_skills (
    id SERIAL PRIMARY KEY,
    mentor_id INTEGER NOT NULL REFERENCES mentors(id) ON DELETE CASCADE,
    slug VARCHAR(80) NOT NULL,
    title VARCHAR(160) NOT NULL,
    content TEXT NOT NULL,
    triggers TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (mentor_id, slug)
);

CREATE INDEX IF NOT EXISTS ix_mentor_skills_mentor_id
    ON mentor_skills(mentor_id);

CREATE INDEX IF NOT EXISTS ix_mentor_skills_enabled
    ON mentor_skills(mentor_id, enabled);
