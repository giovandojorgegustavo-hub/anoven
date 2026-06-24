"""
Migración Fase 6 + 7:
  - ALTER TABLE users ADD COLUMN research_opt_in BOOLEAN DEFAULT FALSE
  - Crea tablas cost_events + attachments (vía SQLAlchemy create_all)
  - Crea directorio /home/anoven/anoven-app/storage/uploads/ si no existe

Ejecutar UNA vez:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_6_7.py
"""

import os
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import engine, Base
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule, cost_event, attachment,
)


def main() -> int:
    Base.metadata.create_all(bind=engine)
    print("✓ Tablas cost_events + attachments creadas (idempotente).")

    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS research_opt_in "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.commit()
    print("✓ Columna users.research_opt_in lista.")

    storage = Path(os.environ.get(
        "ANOVEN_STORAGE_ROOT", "/home/anoven/anoven-app/storage/uploads"
    ))
    storage.mkdir(parents=True, exist_ok=True)
    print(f"✓ Directorio de uploads listo en {storage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
