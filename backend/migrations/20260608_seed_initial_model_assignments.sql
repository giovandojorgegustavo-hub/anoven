-- Seed: initial model assignments for per-mentor-model-assignment-v1
-- Date: 2026-06-08
-- Run AFTER 20260608_per_mentor_model.sql

BEGIN;

-- anoven-creador needs Opus for rich mentor composition (cognitively heavy task)
UPDATE mentors
   SET model = 'claude-opus-4-7'
 WHERE slug = 'anoven-creador';

-- Giovanni (owner) gets Opus across all mentor interactions
UPDATE users
   SET model_override = 'claude-opus-4-7'
 WHERE email = 'giovandojorgegustavo@gmail.com';

-- Verify expected rows
DO $$
DECLARE
  mentor_count INTEGER;
  user_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO mentor_count FROM mentors WHERE slug = 'anoven-creador' AND model = 'claude-opus-4-7';
  SELECT COUNT(*) INTO user_count  FROM users   WHERE email = 'giovandojorgegustavo@gmail.com' AND model_override = 'claude-opus-4-7';

  IF mentor_count = 0 THEN
    RAISE WARNING 'anoven-creador NOT updated (slug not found?). Check mentors table.';
  END IF;
  IF user_count = 0 THEN
    RAISE WARNING 'giovandojorgegustavo@gmail.com NOT updated (email not found?). Check users table.';
  END IF;
END $$;

COMMIT;
