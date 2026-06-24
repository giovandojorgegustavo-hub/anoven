"""
Migración del design pass: agrega columnas a conversations para soportar
unread state + focus state.

Ejecutar UNA vez.
"""

import sys
from sqlalchemy import text
from app.database import engine


def main() -> int:
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE conversations "
            "ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP NULL"
        ))
        conn.execute(text(
            "ALTER TABLE conversations "
            "ADD COLUMN IF NOT EXISTS is_focused BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.commit()
    print("✓ Columnas last_seen_at + is_focused listas en conversations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
