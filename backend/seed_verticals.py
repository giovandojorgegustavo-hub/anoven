"""
Seed del catálogo REAL de Anoven — importa los 14 verticales oficiales.

Lee `/opt/anoven-shared/verticals.json` y, para cada vertical que NO es
backstage (Promptifex y Creador quedan fuera), levanta el `CLAUDE.md`
correspondiente y lo persiste en la tabla `mentors` como:
  - slug          = vertical.slug                 (ej: "anoven-admin")
  - nombre        = vertical.label                (ej: "Administración")
  - canon         = autores extraídos de la description (después del "—")
  - filosofia     = topic extraído de la description (antes del "—")
  - system_prompt = contenido íntegro del CLAUDE.md
  - visibility    = "global"
  - status        = "active"
  - created_by_user_id = NULL  (sistema)

Antes de insertar los nuevos, ARCHIVA los 5 dummy previos
(estrategia / marketing / finanzas / productividad / bienestar)
seteando `status='archived'`. NO los borramos por trazabilidad.

Ejecutar UNA vez desde el server:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 seed_verticals.py
"""

import json
import os
import sys

from app.database import SessionLocal, engine, Base
from app.models.mentor import Mentor

# Para que SQLAlchemy registre las tablas antes de tocar nada.
from app.models import user, interview_attempt, interview_message  # noqa: F401


VERTICALS_JSON = "/opt/anoven-shared/verticals.json"

# Quedan fuera del catálogo público — son backstage del owner.
BACKSTAGE_SLUGS = {"anoven-promptifex", "anoven-creador"}

# Slugs de los 5 dummy creados en sesiones anteriores. Los archivamos.
DUMMY_SLUGS = {"estrategia", "marketing", "finanzas", "productividad", "bienestar"}


def parse_canon_and_filosofia(description: str) -> tuple[str, str]:
    """
    Las descriptions tienen formato 'Topic — Autores'.
    Parseamos y devolvemos (canon, filosofia).

    canon     = lista de autores después del "—"
    filosofia = topic antes del "—"

    Si no hay "—", usamos description entera como filosofia y canon vacío.
    """
    if "—" in description:
        topic, authors = description.split("—", 1)
        return authors.strip(), topic.strip()
    return "", description.strip()


def find_claude_md(cwd: str) -> str | None:
    """Busca el CLAUDE.md de un vertical en sus ubicaciones habituales."""
    candidates = [
        os.path.join(cwd, ".claude", "CLAUDE.md"),
        os.path.join(cwd, "CLAUDE.md"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def main() -> int:
    if not os.path.exists(VERTICALS_JSON):
        print(f"ERROR: no encuentro {VERTICALS_JSON}", file=sys.stderr)
        return 1

    with open(VERTICALS_JSON) as f:
        verticals = json.load(f)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1) Archivar los 5 dummy.
        archived = 0
        for dummy_slug in DUMMY_SLUGS:
            m = db.query(Mentor).filter(Mentor.slug == dummy_slug).first()
            if m is None or m.status == "archived":
                continue
            m.status = "archived"
            archived += 1
            print(f"  archivado: {dummy_slug}")
        if archived:
            db.commit()
            print(f"Archivados {archived} mentores dummy.\n")

        # 2) Importar verticales oficiales.
        imported = 0
        skipped = 0
        already_present = 0

        for v in verticals:
            slug = v["slug"]
            label = v["label"]
            cwd = v["cwd"]
            description = v.get("description", "")

            if slug in BACKSTAGE_SLUGS:
                print(f"  skip (backstage): {slug}")
                skipped += 1
                continue

            claude_md_path = find_claude_md(cwd)
            if claude_md_path is None:
                print(f"  skip (sin CLAUDE.md): {slug}", file=sys.stderr)
                skipped += 1
                continue

            existing = db.query(Mentor).filter(Mentor.slug == slug).first()
            if existing is not None:
                print(f"  ya existe: {slug}")
                already_present += 1
                continue

            with open(claude_md_path) as f:
                system_prompt = f.read()

            canon, filosofia = parse_canon_and_filosofia(description)

            mentor = Mentor(
                slug=slug,
                nombre=label,
                canon=canon[:500] if canon else "(canon en CLAUDE.md)",
                filosofia=filosofia[:500] if filosofia else label,
                system_prompt=system_prompt,
                created_by_user_id=None,
                visibility="global",
                status="active",
            )
            db.add(mentor)
            print(f"  + importado: {slug} ({len(system_prompt)} chars)")
            imported += 1

        db.commit()

        print()
        print(f"Resumen: importados={imported}  skipped={skipped}  ya-existían={already_present}  dummy-archivados={archived}")

        # Estado final.
        total_active = db.query(Mentor).filter(
            Mentor.visibility == "global",
            Mentor.status == "active",
        ).count()
        total_archived = db.query(Mentor).filter(Mentor.status == "archived").count()
        print(f"Total en catálogo público (global+active): {total_active}")
        print(f"Total archivados: {total_archived}")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
