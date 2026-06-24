"""
Migración Sesión 4.4: backfill de observations en engram al nuevo namespace
per-anoven-project.

Antes (4.3): project = "anoven-app-user-{user_id}"
Después (4.4): project = "anoven-app-user-{user_id}-{anoven_project_slug}"

El backfill recorre todas las conversations, calcula el engram_project que
LE TOCA según su use_case, computa el session_id determinístico, y UPDATEa
las observations de ese session_id al nuevo project.

Ejecutar UNA vez desde el server:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_4_4.py
"""

import sqlite3
import sys
from pathlib import Path

from app.database import SessionLocal
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project,
)
from app.models.conversation import Conversation
from app.services.engram_client import (
    project_for_user_and_project,
    session_id_for_conversation,
)
from app.services.project_service import ProjectService


ENGRAM_DB = Path.home() / ".engram" / "engram.db"


def main() -> int:
    if not ENGRAM_DB.exists():
        print(f"ERROR: no encuentro engram db en {ENGRAM_DB}", file=sys.stderr)
        return 1

    db = SessionLocal()
    eng = sqlite3.connect(str(ENGRAM_DB))

    try:
        service = ProjectService(db)
        convs = db.query(Conversation).all()
        print(f"Total conversations: {len(convs)}")

        updated_total = 0
        for c in convs:
            session_id = session_id_for_conversation(c.id)

            # Resolver el anoven-project slug de esta conv
            slug = None
            if c.use_case_id is not None:
                uc = service.use_case_repo.get_by_id(c.use_case_id)
                if uc is not None:
                    p = service.project_repo.get_by_id(uc.project_id)
                    if p is not None:
                        slug = p.slug

            if slug is None:
                default = service.project_repo.get_default_for_user(c.user_id)
                slug = default.slug if default else "general"

            new_project = project_for_user_and_project(c.user_id, slug)

            cursor = eng.execute(
                "UPDATE observations SET project = ? WHERE session_id = ? AND project != ?",
                (new_project, session_id, new_project),
            )
            count = cursor.rowcount
            if count > 0:
                # También actualizamos la sesión
                eng.execute(
                    "UPDATE sessions SET project = ? WHERE id = ?",
                    (new_project, session_id),
                )
                print(
                    f"  conv #{c.id} (user_id={c.user_id}) → {new_project} "
                    f"[{count} observations updated]"
                )
                updated_total += count

        eng.commit()
        print()
        print(f"✓ Backfill 4.4 completado. {updated_total} observations migradas.")
        return 0
    finally:
        eng.close()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
