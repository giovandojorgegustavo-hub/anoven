"""
Migración Fase B: copia users + sus mentores custom del sistema viejo
(/opt/anoven-chat) al nuevo anoven-app (Postgres).

Para cada user:
  - Copio email, name, password_hash (bcrypt compatible), role
  - Marco onboarding_state='passed' con onboarding_attempts=0 (skip entrevista)
  - Auto-asigno los 14 mentores default del catálogo (como user nuevo normal)
  - Si tiene mentores custom en /opt/anoven-shared/user-mentors/{id}/{slug}/CLAUDE.md:
      → los importo como Mentor visibility='private', status='active',
        created_by_user_id=nuevo_id
      → los asigno con source='created_by_self'

No mergeo con users del nuevo sistema si email coincide — los marca como skip.
Salida final: cuántos importados, cuántos saltados.

Ejecutar UNA vez en el server:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_users_from_legacy.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule, cost_event, attachment, mentor_request,
)
from app.models.mentor import Mentor, UserMentor
from app.models.user import User
from app.services.project_service import ProjectService


OLD_DB = "/opt/anoven-chat/data/anoven.db"
USER_MENTORS_DIR = Path("/opt/anoven-shared/user-mentors")


def main() -> int:
    if not Path(OLD_DB).exists():
        print(f"ERROR: viejo DB no encontrado en {OLD_DB}", file=sys.stderr)
        return 1

    old_conn = sqlite3.connect(OLD_DB)
    old_conn.row_factory = sqlite3.Row
    db = SessionLocal()

    try:
        project_service = ProjectService(db)

        # ===== 1) Migrar users =====
        old_users = old_conn.execute(
            "SELECT id, name, email, password_hash, role FROM users ORDER BY id"
        ).fetchall()

        old_to_new_id: dict[int, int] = {}
        imported = 0
        skipped_existing = 0

        for ou in old_users:
            existing = db.query(User).filter(User.email == ou["email"]).first()
            if existing is not None:
                old_to_new_id[ou["id"]] = existing.id
                skipped_existing += 1
                print(f"  skip (ya existe en nuevo): {ou['email']} (old={ou['id']} → new={existing.id})")
                continue

            new_user = User(
                email=ou["email"],
                nombre=ou["name"] or ou["email"].split("@")[0],
                password_hash=ou["password_hash"],
                auth_provider="local",
                role=ou["role"] or "user",
                onboarding_state="passed",
                onboarding_attempts=0,
                onboarding_score=None,
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            old_to_new_id[ou["id"]] = new_user.id

            # Default project + mentores
            default_project = project_service.ensure_default_for_user(new_user.id)
            new_user.active_project_id = default_project.id
            db.commit()

            # Auto-asignar los 14 mentores default a este user
            from app.services.mentor_service import MentorService
            MentorService(db).assign_defaults_to_user(new_user.id)

            print(f"  + {ou['email']} (old_id={ou['id']} → new_id={new_user.id})")
            imported += 1

        # ===== 2) Migrar mentores custom desde filesystem =====
        custom_imported = 0
        for old_user_id, new_user_id in old_to_new_id.items():
            user_dir = USER_MENTORS_DIR / str(old_user_id)
            if not user_dir.exists():
                continue

            for slug_dir in sorted(user_dir.iterdir()):
                if not slug_dir.is_dir():
                    continue
                claude_md = slug_dir / "CLAUDE.md"
                if not claude_md.exists():
                    continue

                # Slug único globalmente
                new_slug = f"migrated-{slug_dir.name}-u{new_user_id}"
                if db.query(Mentor).filter(Mentor.slug == new_slug).first():
                    continue

                system_prompt = claude_md.read_text()
                nombre = slug_dir.name.replace("-", " ").title()

                m = Mentor(
                    slug=new_slug,
                    nombre=nombre,
                    canon="(heredado del sistema viejo)",
                    filosofia=f"Mentor custom heredado: {slug_dir.name}",
                    system_prompt=system_prompt,
                    created_by_user_id=new_user_id,
                    visibility="private",
                    status="active",
                )
                db.add(m)
                db.commit()
                db.refresh(m)

                # Asignar al user con source='created_by_self'
                um = UserMentor(
                    user_id=new_user_id,
                    mentor_id=m.id,
                    source="created_by_self",
                    active=True,
                )
                db.add(um)
                db.commit()
                custom_imported += 1
                print(f"    custom: {nombre} (slug={new_slug}) → user_id={new_user_id}")

        print()
        print(f"=== Resumen ===")
        print(f"  Users importados: {imported}")
        print(f"  Users saltados (ya existían): {skipped_existing}")
        print(f"  Mentores custom importados: {custom_imported}")
        return 0
    finally:
        db.close()
        old_conn.close()


if __name__ == "__main__":
    sys.exit(main())
