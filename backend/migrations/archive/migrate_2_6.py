"""
Migración Sesión 2.6: agrega columna `match_reason` a `user_mentors` y
re-corre el MentorMatcher para users que ya tenían matches sin razón guardada.

Ejecutar UNA vez desde el server:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_2_6.py
"""

import json
import sys

from sqlalchemy import text

from app.database import SessionLocal, engine
from app.repositories.interview_repo import InterviewRepository
from app.services.mentor_matcher import match_mentors
from app.services.mentor_service import MentorService

# Registrar modelos para que SQLAlchemy los conozca.
from app.models import user, mentor, interview_attempt, interview_message  # noqa: F401
from app.models.interview_attempt import InterviewAttempt


def add_column_if_missing() -> None:
    """ALTER TABLE para agregar match_reason. Idempotente."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE user_mentors "
                "ADD COLUMN IF NOT EXISTS match_reason TEXT"
            )
        )
        conn.commit()
        print("Columna `match_reason` lista en user_mentors.")


def rematch_evaluated_users() -> None:
    """
    Para cada attempt 'evaluated' (ya pasó por Evaluador), volvemos a llamar
    al MentorMatcher con el profile_json guardado y refrescamos user_mentors
    con las razones esta vez.

    NO re-llama al Evaluador (caro). Solo el Matcher (~$0.01 por user).
    """
    db = SessionLocal()
    try:
        # Buscamos los attempts evaluados.
        attempts = db.query(InterviewAttempt).filter(
            InterviewAttempt.status == "evaluated"
        ).all()

        if not attempts:
            print("No hay attempts evaluados todavía. Nada que re-matchear.")
            return

        mentor_service = MentorService(db)
        catalog = mentor_service.list_global_catalog()

        for attempt in attempts:
            print(f"\n  user_id={attempt.user_id}  attempt={attempt.id}  score={attempt.score}")
            if not attempt.profile_json:
                print("    skip — sin profile_json")
                continue

            profile = json.loads(attempt.profile_json)
            matches = match_mentors(profile=profile, catalog=catalog)
            print(f"    matches devueltos: {len(matches)}")

            mentor_service.replace_with_matched(
                user_id=attempt.user_id,
                matches=matches,
            )
            for m in matches:
                print(f"      · {m['slug']:32} → {m['reason'][:70]}")
    finally:
        db.close()


def main() -> int:
    print("=== Paso 1: agregar columna match_reason ===")
    add_column_if_missing()
    print()
    print("=== Paso 2: re-matchear users evaluados ===")
    rematch_evaluated_users()
    return 0


if __name__ == "__main__":
    sys.exit(main())
