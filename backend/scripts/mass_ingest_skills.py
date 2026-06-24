#!/usr/bin/env python3
"""
Mass ingest script — skills-platform-with-telemetry (Batch 1)

Reads all SKILL.md files from local ~/.claude/skills/ (excluding _shared/, sdd-*, pmtx-*)
and UPSERTs them into the remote mentor_skills PostgreSQL table for all active mentors
except anoven-creador.

Usage:
    python3 mass_ingest_skills.py \
        --source-dir ~/.claude/skills \
        --db-url "postgresql://anoven_app:PASSWORD@localhost:5432/anoven_app_dev" \
        --exclude-mentor anoven-creador \
        --output-sql backend/SQL/migrations/003_mass_ingest_skills_TIMESTAMP.sql \
        [--dry-run]

Environment:
    DATABASE_URL  Postgres connection string (overrides --db-url if set)
    ADMIN_API_TOKEN  Bearer token for cache invalidate endpoint (optional)
"""

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional deps — fail early with helpful message
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    sys.exit("Missing PyYAML — install with: pip install pyyaml")

try:
    import psycopg
except ImportError:
    sys.exit("Missing psycopg — install with: pip install 'psycopg[binary]'")

# ---------------------------------------------------------------------------
# Constants (from app/services/skill_loader.py — kept in sync)
# ---------------------------------------------------------------------------
MAX_PER_SKILL_CHARS = 8_000
TRUNCATE_SUFFIX = "\n\n... [truncado]"

# Slug must match /^[a-z0-9-]+$/ and be <= 80 chars
SLUG_RE = re.compile(r"^[a-z0-9-]+$")
SLUG_MAX_LEN = 80


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert arbitrary text to a valid slug: lowercase, hyphens, no special chars."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:SLUG_MAX_LEN] if text else "unknown-skill"


def humanize(slug: str) -> str:
    """Turn a slug into a readable title: 'my-skill' -> 'My Skill'."""
    return " ".join(word.capitalize() for word in slug.split("-"))


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter delimited by ---. Returns (frontmatter_dict, body).
    If no frontmatter, returns ({}, full_text).
    """
    if not text.startswith("---"):
        return {}, text

    # Find the closing ---
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return {}, text

    fm_text = text[3:end_idx].strip()
    body = text[end_idx + 4:].lstrip("\n")

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}

    if not isinstance(fm, dict):
        fm = {}

    return fm, body


def normalize_skill(dir_name: str, skill_path: Path) -> dict | None:
    """
    Parse and normalize a SKILL.md file.
    Returns a dict with keys: slug, title, triggers (JSON str), content, dir_name.
    Returns None if the file cannot be parsed or yields an empty content.
    """
    try:
        raw = skill_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"  WARN: cannot read {skill_path}: {e}", file=sys.stderr)
        return None

    fm, body = parse_frontmatter(raw)

    # Slug fallback chain: frontmatter.slug -> slugify(name) -> dir_basename
    slug = (
        fm.get("slug")
        or (slugify(fm["name"]) if fm.get("name") else None)
        or dir_name
    )
    slug = slugify(str(slug))  # ensure valid format
    if len(slug) > SLUG_MAX_LEN:
        print(f"  WARN: slug '{slug}' truncated from '{dir_name}'", file=sys.stderr)
        slug = slug[:SLUG_MAX_LEN].rstrip("-")

    # Title fallback chain: display_name -> name -> humanize(slug)
    title = (
        fm.get("display_name")
        or fm.get("name")
        or humanize(slug)
    )
    title = str(title)[:160]  # VARCHAR(160) cap

    # Triggers: activation_phrases -> triggers field -> []
    raw_triggers = fm.get("activation_phrases") or fm.get("triggers") or []
    if isinstance(raw_triggers, str):
        raw_triggers = [raw_triggers]
    elif not isinstance(raw_triggers, list):
        raw_triggers = []
    triggers_json = json.dumps([str(t) for t in raw_triggers], ensure_ascii=False)

    # Content: full body, capped at 8000 chars
    content = body.strip()
    if not content:
        # Fall back to full file if body is empty (no frontmatter separation)
        content = raw.strip()
    if len(content) > MAX_PER_SKILL_CHARS:
        content = content[: MAX_PER_SKILL_CHARS - len(TRUNCATE_SUFFIX)] + TRUNCATE_SUFFIX

    if not content:
        print(f"  WARN: empty content for '{dir_name}', skipping", file=sys.stderr)
        return None

    return {
        "slug": slug,
        "title": title,
        "triggers": triggers_json,
        "content": content,
        "dir_name": dir_name,
    }


def collect_skills(source_dir: Path, exclude_prefixes: list[str]) -> list[dict]:
    """Walk source_dir, parse each subdirectory's SKILL.md, return normalized list."""
    skills = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        dir_name = child.name
        if any(dir_name.startswith(p) for p in exclude_prefixes):
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.exists():
            print(f"  INFO: no SKILL.md in {dir_name}, skipping", file=sys.stderr)
            continue
        skill = normalize_skill(dir_name, skill_file)
        if skill is not None:
            skills.append(skill)
    return skills


def resolve_target_mentors(conn, exclude_slugs: set[str]) -> list[dict]:
    """Query active mentors from DB, exclude the given slugs."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, slug FROM mentors WHERE status='active' ORDER BY slug"
        )
        rows = cur.fetchall()
    return [{"id": r[0], "slug": r[1]} for r in rows if r[1] not in exclude_slugs]


def build_upsert_sql(
    mentors: list[dict],
    skills: list[dict],
    run_ts: str,
) -> str:
    """Generate the full SQL artifact content (BEGIN ... COMMIT)."""
    lines = [
        "--",
        f"-- Mass ingest skills — generated {run_ts}",
        f"-- Source: ~/.claude/skills/ | Skills: {len(skills)} | Mentors: {len(mentors)}",
        f"-- Excluded: anoven-creador",
        f"-- Expected rows: ~{len(mentors) * len(skills)} (UPSERT)",
        "--",
        "",
        "BEGIN;",
        "",
    ]

    for mentor in mentors:
        lines.append(f"-- Mentor: {mentor['slug']} (id={mentor['id']})")
        for skill in skills:
            # Escape single quotes in SQL string literals
            def esc(s: str) -> str:
                return s.replace("'", "''")

            lines.append(
                f"INSERT INTO mentor_skills "
                f"(mentor_id, slug, title, content, triggers, enabled, position, created_at, updated_at) "
                f"VALUES ("
                f"{mentor['id']}, "
                f"'{esc(skill['slug'])}', "
                f"'{esc(skill['title'])}', "
                f"'{esc(skill['content'])}', "
                f"'{esc(skill['triggers'])}', "
                f"true, "
                f"0, "
                f"NOW(), "
                f"NOW()"
                f") "
                f"ON CONFLICT (mentor_id, slug) DO UPDATE SET "
                f"content = EXCLUDED.content, "
                f"title = EXCLUDED.title, "
                f"triggers = EXCLUDED.triggers, "
                f"updated_at = NOW();"
            )
        lines.append("")

    lines += ["COMMIT;", ""]
    return "\n".join(lines)


def execute_sql(conn, sql_content: str) -> dict:
    """Execute the SQL inside a single transaction. Returns summary dict."""
    summary = {"rows_affected": 0, "errors": []}
    with conn.cursor() as cur:
        try:
            cur.execute(sql_content)
            conn.commit()
            summary["rows_affected"] = cur.rowcount
        except Exception as e:
            conn.rollback()
            summary["errors"].append(str(e))
            raise
    return summary


def invalidate_cache(url: str, token: str | None) -> None:
    """POST to the cache invalidate endpoint."""
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            method="POST",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                print(f"  Cache invalidated via {url}")
            else:
                print(f"  WARN: cache invalidate returned {resp.status}", file=sys.stderr)
    except Exception as e:
        print(f"  WARN: cache invalidate failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mass ingest SKILL.md files into mentor_skills PostgreSQL table."
    )
    parser.add_argument(
        "--source-dir",
        default=str(Path.home() / ".claude" / "skills"),
        help="Directory containing skill subdirs (default: ~/.claude/skills)",
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection URL (overridden by DATABASE_URL env var)",
    )
    parser.add_argument(
        "--exclude-mentor",
        action="append",
        default=["anoven-creador"],
        metavar="SLUG",
        help="Mentor slug(s) to exclude (default: anoven-creador)",
    )
    parser.add_argument(
        "--exclude-dir-prefix",
        action="append",
        default=["_shared", "sdd-", "pmtx-"],
        metavar="PREFIX",
        help="Skill dir prefixes to skip (default: _shared sdd- pmtx-)",
    )
    parser.add_argument(
        "--output-sql",
        default="",
        help="Path for generated SQL artifact. Auto-named with timestamp if empty.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and generate SQL, but do NOT execute against the DB.",
    )
    parser.add_argument(
        "--cache-invalidate-url",
        default="",
        help="URL for POST /api/admin/skills/cache/invalidate after ingest.",
    )
    args = parser.parse_args()

    db_url = args.db_url
    if not db_url:
        sys.exit("ERROR: DATABASE_URL env var or --db-url required")

    source_dir = Path(args.source_dir).expanduser()
    if not source_dir.is_dir():
        sys.exit(f"ERROR: source dir not found: {source_dir}")

    # ------------------------------------------------------------------
    # Stage 0 — Preflight: verify DB connectivity and schema
    # ------------------------------------------------------------------
    print(f"\n=== Stage 0 — Preflight ===")
    print(f"Source dir : {source_dir}")
    print(f"DB URL     : {db_url[:40]}...")
    print(f"Dry run    : {args.dry_run}")

    if not args.dry_run:
        try:
            conn = psycopg.connect(db_url)
        except Exception as e:
            sys.exit(f"ERROR: cannot connect to database: {e}")

        # Verify schema has expected columns
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='mentor_skills' AND table_schema='public'"
            )
            cols = {r[0] for r in cur.fetchall()}
        expected = {"id", "mentor_id", "slug", "title", "content", "triggers", "enabled", "position"}
        missing = expected - cols
        if missing:
            conn.close()
            sys.exit(f"ERROR: mentor_skills schema mismatch — missing columns: {missing}")
        print(f"Schema OK  : mentor_skills has expected columns")

        # Resolve target mentors
        exclude_slugs = set(args.exclude_mentor)
        mentors = resolve_target_mentors(conn, exclude_slugs)
        print(f"Mentors    : {len(mentors)} active (excluding: {', '.join(sorted(exclude_slugs))})")
        for m in mentors:
            print(f"             {m['slug']} (id={m['id']})")
    else:
        conn = None
        mentors = [{"id": 0, "slug": "(dry-run-placeholder)"}]
        print("Dry-run mode: skipping DB connection and mentor resolution")

    # ------------------------------------------------------------------
    # Stage 1 — Discovery
    # ------------------------------------------------------------------
    print(f"\n=== Stage 1 — Discovery ===")
    skills = collect_skills(source_dir, args.exclude_dir_prefix)
    print(f"Skills found: {len(skills)}")
    for s in skills:
        print(f"  {s['slug']} ({s['dir_name']})")

    if not skills:
        sys.exit("ERROR: no skills found — check --source-dir and --exclude-dir-prefix")

    # ------------------------------------------------------------------
    # Stage 2 — Parse & Normalize (already done by collect_skills)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 2 — Parse & Normalize ===")
    print(f"Normalized {len(skills)} skills OK")

    # ------------------------------------------------------------------
    # Stage 3 — SQL Generation
    # ------------------------------------------------------------------
    print(f"\n=== Stage 3 — SQL Generation ===")
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    output_sql = args.output_sql
    if not output_sql:
        # Auto-name relative to where script is called from (backend repo context expected)
        output_sql = f"003_mass_ingest_skills_{run_ts}.sql"

    # Resolve relative paths from CWD
    output_path = Path(output_sql).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the actual mentors list for SQL (use real mentors or placeholders)
    sql_mentors = mentors if not args.dry_run else [{"id": 999, "slug": "DRY-RUN-MENTOR"}]
    sql_content = build_upsert_sql(sql_mentors, skills, run_ts)

    output_path.write_text(sql_content, encoding="utf-8")
    expected_rows = len(sql_mentors) * len(skills)
    print(f"SQL written : {output_path}")
    print(f"Expected rows: {expected_rows} UPSERTs ({len(skills)} skills × {len(sql_mentors)} mentors)")

    # ------------------------------------------------------------------
    # Stage 4 — Execute (skip if --dry-run)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 4 — Execute ===")
    if args.dry_run:
        print("Dry-run: execution skipped")
        print(f"\n=== DRY-RUN COMPLETE ===")
        print(f"Would ingest: {len(skills)} skills × {len(sql_mentors)} mentors = {expected_rows} rows")
        return

    # Regenerate SQL with real mentors (in dry-run we may have used placeholders)
    sql_content = build_upsert_sql(mentors, skills, run_ts)
    output_path.write_text(sql_content, encoding="utf-8")
    print(f"SQL artifact updated with real mentor IDs: {output_path}")

    print(f"Executing {len(mentors) * len(skills)} UPSERTs in single transaction...")
    try:
        with conn.cursor() as cur:
            cur.execute(sql_content)
            conn.commit()
        print(f"Transaction committed OK")
    except Exception as e:
        print(f"ERROR: transaction failed and rolled back: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # ------------------------------------------------------------------
    # Stage 5 — Cache invalidation (optional)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 5 — Cache Invalidation ===")
    if args.cache_invalidate_url:
        token = os.environ.get("ADMIN_API_TOKEN", "")
        invalidate_cache(args.cache_invalidate_url, token or None)
    else:
        print("Skipped (no --cache-invalidate-url provided)")
        print("To invalidate manually: POST https://anoven.ai/api/admin/skills/cache/invalidate")

    # ------------------------------------------------------------------
    # Stage 6 — Verification (informational)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 6 — Verification ===")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mentor_id, COUNT(*) FROM mentor_skills WHERE enabled=true "
            "GROUP BY mentor_id ORDER BY mentor_id"
        )
        rows = cur.fetchall()
    mentor_id_to_slug = {m["id"]: m["slug"] for m in mentors}
    print("Per-mentor enabled skill count:")
    for mentor_id, count in rows:
        slug = mentor_id_to_slug.get(mentor_id, f"id={mentor_id}")
        print(f"  {slug}: {count} enabled skills")

    conn.close()

    print(f"\n=== INGEST COMPLETE ===")
    print(f"Skills ingested : {len(skills)}")
    print(f"Mentors targeted: {len(mentors)}")
    print(f"SQL artifact    : {output_path}")
    print(f"Backup snapshot : /tmp/mentor_skills_backup_pre_skills-platform-with-telemetry_*.sql")


if __name__ == "__main__":
    main()
