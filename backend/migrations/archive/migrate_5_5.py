"""
Migración Sesión 5.5:
  1. Promueve a Jorge (user_id=1) a role='admin'.
  2. Importa los user-mentors viejos de /opt/anoven-shared/user-mentors/
     como mentores con status='pending_review' + visibility='private'.
     Quedan en la curation queue para que Jorge los apruebe/rechace.

Ejecutar UNA vez:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_5_5.py
"""

import os
import re
import sys
from pathlib import Path

from app.database import SessionLocal
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule,
)
from app.models.mentor import Mentor
from app.models.user import User


USER_MENTORS_DIR = Path("/opt/anoven-shared/user-mentors")


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "mentor")[:50]


def main() -> int:
    db = SessionLocal()
    try:
        # ===== 1) Jorge = admin =====
        jorge = db.query(User).filter(User.id == 1).first()
        if jorge is None:
            print("ERROR: user id=1 (Jorge) no existe", file=sys.stderr)
            return 1
        if jorge.role != "admin":
            jorge.role = "admin"
            db.commit()
            print(f"✓ {jorge.email} → role='admin'")
        else:
            print(f"  {jorge.email} ya era admin")

        # ===== 2) Importar user-mentors viejos =====
        if not USER_MENTORS_DIR.exists():
            print(f"ERROR: {USER_MENTORS_DIR} no existe", file=sys.stderr)
            return 1

        imported = 0
        skipped = 0
        for user_dir in sorted(USER_MENTORS_DIR.iterdir()):
            if not user_dir.is_dir() or not user_dir.name.isdigit():
                continue
            for slug_dir in sorted(user_dir.iterdir()):
                if not slug_dir.is_dir():
                    continue
                claude_md = slug_dir / "CLAUDE.md"
                if not claude_md.exists():
                    continue

                # Slug nuevo para el sistema (prefijado para no colisionar)
                old_slug = slug_dir.name
                new_slug = f"legacy-{old_slug}-u{user_dir.name}"

                if db.query(Mentor).filter(Mentor.slug == new_slug).first():
                    skipped += 1
                    print(f"  skip ya importado: {new_slug}")
                    continue

                system_prompt = claude_md.read_text()
                nombre = old_slug.replace("-", " ").title()
                m = Mentor(
                    slug=new_slug,
                    nombre=nombre,
                    canon="(canon a curar — heredado del sistema viejo)",
                    filosofia=f"Heredado del user-mentor '{old_slug}' del sistema legacy.",
                    system_prompt=system_prompt,
                    created_by_user_id=None,  # no remapeamos al user viejo
                    visibility="private",
                    status="pending_review",
                )
                db.add(m)
                imported += 1
                print(f"  + {new_slug} (de /{user_dir.name}/{old_slug}, {len(system_prompt)} chars)")

        db.commit()
        print(f"\n✓ Importados {imported}, skip {skipped}. Todos en pending_review.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
