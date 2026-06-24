"""
Migration FASE 6.1 — Versionado de mentores.

Agrega 5 columnas nuevas a `mentors`:
  - version: int default 1 — versión actual del mentor
  - prev_version_id: FK self (nullable) — cadena de versiones históricas
  - curated_at: timestamp (nullable) — cuándo se curó esta versión
  - curator: text (nullable) — quién curó ("initial_seed" | "promptifex_sdd" | "manual_admin")
  - eval_suite_topic_key: text (nullable) — link a engram eval-suite/vX

Backfill: todos los mentores existentes → version=1, curator='initial_seed', eval_suite_topic_key=null
EXCEPCIÓN: anoven-promptifex YA pasó por PMTX v1.2 — marcamos curator='promptifex_sdd' + topic key conocido.
"""

import sys
import os
import psycopg


def main() -> int:
    DB_URL = os.environ.get("DATABASE_URL", "").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    if not DB_URL:
        print("ERROR: DATABASE_URL no set", file=sys.stderr)
        return 1

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # 1) Agregar columnas si no existen (idempotente)
            print("== Agregando columnas...")
            cur.execute("""
                ALTER TABLE mentors
                ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS prev_version_id INTEGER REFERENCES mentors(id),
                ADD COLUMN IF NOT EXISTS curated_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS curator VARCHAR(40),
                ADD COLUMN IF NOT EXISTS eval_suite_topic_key VARCHAR(200);
            """)

            print("== Index en (slug, version) para futuras consultas...")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_mentors_slug_version
                ON mentors(slug, version DESC);
            """)

            # 2) Backfill — todos los mentores actuales son v1 'initial_seed'
            print("== Backfill: mentores existentes a v1 initial_seed...")
            cur.execute("""
                UPDATE mentors
                SET curator = 'initial_seed', version = 1
                WHERE curator IS NULL;
            """)
            print(f"  {cur.rowcount} mentores marcados como initial_seed")

            # 3) Excepción: anoven-promptifex SÍ pasó por PMTX cycle v1.2
            print("== Excepción: anoven-promptifex tiene curator='promptifex_sdd'")
            cur.execute("""
                UPDATE mentors
                SET curator = 'promptifex_sdd',
                    curated_at = '2026-05-23 07:17:12'::timestamp,
                    eval_suite_topic_key = 'anoven-promptifex/eval-suite/v1.2'
                WHERE slug = 'anoven-promptifex';
            """)
            print(f"  {cur.rowcount} updated")

            conn.commit()

            # 4) Reportar estado
            print()
            print("=== Estado final ===")
            cur.execute("""
                SELECT slug, version, curator, curated_at, eval_suite_topic_key
                FROM mentors
                WHERE visibility IN ('global', 'special')
                ORDER BY curated_at DESC NULLS LAST, slug
            """)
            print(f"  {'slug':<32} v  curator              curated_at            eval_suite")
            for slug, version, curator, curated, eval_key in cur.fetchall():
                cur_at = str(curated)[:19] if curated else "—"
                eval_disp = (eval_key or "—")[:40]
                print(f"  {slug:<32} {version}  {(curator or '—'):<19} {cur_at:<20} {eval_disp}")

    print()
    print("✅ Migration FASE 6.1 completada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
