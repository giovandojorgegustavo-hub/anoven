"""
Migración Sesión 5.1: importa el vertical `anoven-creador` a la tabla mentors
con visibility='special' — así NO entra al pool del MentorMatcher pero está
disponible para start_or_resume desde el flow "Crear mentor".

Ejecutar UNA vez desde el server:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_5_1.py
"""

import json
import os
import sys

from app.database import SessionLocal, engine, Base
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule,
)
from app.models.mentor import Mentor


VERTICALS_JSON = "/opt/anoven-shared/verticals.json"
CREADOR_SLUG = "anoven-creador"


def main() -> int:
    if not os.path.exists(VERTICALS_JSON):
        print(f"ERROR: {VERTICALS_JSON} no existe", file=sys.stderr)
        return 1

    with open(VERTICALS_JSON) as f:
        verticals = json.load(f)

    creador = next((v for v in verticals if v["slug"] == CREADOR_SLUG), None)
    if creador is None:
        print(f"ERROR: vertical {CREADOR_SLUG} no encontrado", file=sys.stderr)
        return 1

    cwd = creador["cwd"]
    claude_md = os.path.join(cwd, ".claude", "CLAUDE.md")
    if not os.path.exists(claude_md):
        print(f"ERROR: {claude_md} no existe", file=sys.stderr)
        return 1

    with open(claude_md) as f:
        system_prompt = f.read()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(Mentor).filter(Mentor.slug == CREADOR_SLUG).first()
        if existing is not None:
            # Refresh contenido + asegurarse de visibility='special'
            existing.system_prompt = system_prompt
            existing.visibility = "special"
            existing.status = "active"
            db.commit()
            print(f"✓ Creador refresheado (id={existing.id}, visibility=special)")
            return 0

        description = creador.get("description", "")
        if "—" in description:
            topic, authors = description.split("—", 1)
            canon = authors.strip()
            filosofia = topic.strip()
        else:
            canon = "(ver CLAUDE.md)"
            filosofia = description.strip() or "El Creador"

        m = Mentor(
            slug=CREADOR_SLUG,
            nombre=creador["label"],
            canon=canon[:500],
            filosofia=filosofia[:500],
            system_prompt=system_prompt,
            created_by_user_id=None,
            visibility="special",
            status="active",
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        print(f"✓ Creador importado (id={m.id}, visibility=special, {len(system_prompt)} chars)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
