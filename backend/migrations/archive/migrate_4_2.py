"""
Migración Sesión 4.2:
  1. ALTER TABLE users ADD COLUMN active_project_id INTEGER NULL
  2. ALTER TABLE conversations ADD COLUMN use_case_id INTEGER NULL
  3. Crea tablas projects + use_cases (SQLAlchemy create_all las agrega)
  4. Para CADA user existente: bootstrap project default 'General' + use_case
     'Charla libre' + setea user.active_project_id
  5. Asigna todas las conversations existentes al default use_case del
     default project de su user

Ejecutar UNA vez desde el server:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_4_2.py
"""

import sys

from sqlalchemy import text

from app.database import SessionLocal, engine, Base
from app.models import (  # noqa: F401 — registrar modelos antes del create_all
    user,
    mentor,
    interview_attempt,
    interview_message,
    conversation,
    message,
    project,
)
from app.models.conversation import Conversation
from app.models.user import User
from app.services.project_service import ProjectService


def alter_tables_if_missing() -> None:
    """Agrega columnas a users + conversations. Idempotente con IF NOT EXISTS."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS active_project_id INTEGER NULL"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE conversations "
                "ADD COLUMN IF NOT EXISTS use_case_id INTEGER NULL "
                "REFERENCES use_cases(id)"
            )
        )
        conn.commit()
    print("Columnas active_project_id + use_case_id listas.")


def create_new_tables() -> None:
    """Crea projects + use_cases."""
    Base.metadata.create_all(bind=engine)
    print("Tablas projects + use_cases listas.")


def bootstrap_existing_users() -> None:
    """Crea default project + use_case + active_project_id para cada user."""
    db = SessionLocal()
    try:
        service = ProjectService(db)
        users_all = db.query(User).all()
        for u in users_all:
            project = service.ensure_default_for_user(u.id)
            if u.active_project_id is None:
                u.active_project_id = project.id
                db.commit()
            print(
                f"  user_id={u.id} ({u.email}) → default project '{project.name}' (id={project.id})"
            )
    finally:
        db.close()


def assign_orphan_conversations() -> None:
    """
    Las conversaciones creadas antes de 4.2 tienen use_case_id=NULL.
    Las asignamos al default use_case del default project del owner.
    """
    db = SessionLocal()
    try:
        service = ProjectService(db)
        orphans = db.query(Conversation).filter(
            Conversation.use_case_id.is_(None)
        ).all()
        moved = 0
        for c in orphans:
            project = service.project_repo.get_default_for_user(c.user_id)
            if project is None:
                continue
            default_uc = service.use_case_repo.get_default_for_project(project.id)
            if default_uc is None:
                continue
            c.use_case_id = default_uc.id
            moved += 1
        db.commit()
        print(f"  {moved} conversaciones huérfanas asignadas a default use_case.")
    finally:
        db.close()


def main() -> int:
    print("=== Paso 1: alter tables ===")
    create_new_tables()
    alter_tables_if_missing()
    print()
    print("=== Paso 2: bootstrap users existentes ===")
    bootstrap_existing_users()
    print()
    print("=== Paso 3: asignar conversaciones huérfanas ===")
    assign_orphan_conversations()
    print()
    print("✓ Migración 4.2 completada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
