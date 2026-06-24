-- Migration 002: Add allowed_tools column to mentors table
-- Phase 2 of mentor-tools-system SDD cycle
-- Safe to run multiple times (ALTER TABLE IF NOT EXISTS equivalent via exception)
--
-- This migration adds an `allowed_tools` TEXT column to `mentors` storing a
-- JSON array of tool slugs, e.g. '["mem_search"]'.
-- Default '[]' means ALL existing mentors opt OUT of the agentic loop.
-- No behavioral change until a mentor's allowed_tools is explicitly updated.

ALTER TABLE mentors ADD COLUMN allowed_tools TEXT NOT NULL DEFAULT '[]';
