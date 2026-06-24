"""
Corre Promptifex SDD sobre UN mentor directo desde Python (sin pasar por HTTP).

Uso: python3 curate_one.py {slug}
Ej:  python3 curate_one.py anoven-design
"""

import json
import sys
import os
import urllib.request
from datetime import datetime

from app.database import SessionLocal
# Importar TODOS los models antes para que SQLAlchemy resuelva FKs cross-table
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule, cost_event, attachment, mentor_request,
)
from app.models.mentor import Mentor
from app.services.promptifex import recurate_mentor


def save_to_engram(project: str, topic_key: str, title: str, content: str) -> bool:
    """Best-effort save al engram local."""
    try:
        payload = {
            "project": project,
            "scope": "project",
            "type": "architecture",
            "title": title,
            "content": content,
            "topic_key": topic_key,
        }
        req = urllib.request.Request(
            "http://127.0.0.1:7437/save",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"  ⚠️ engram save falló: {e}")
        return False


def main(slug: str) -> int:
    db = SessionLocal()
    try:
        m = db.query(Mentor).filter(Mentor.slug == slug).first()
        if not m:
            print(f"  ❌ {slug} no existe en BD")
            return 1

        old_version = m.version
        old_system_prompt = m.system_prompt
        old_canon = m.canon
        old_filosofia = m.filosofia
        old_bytes = len(old_system_prompt or "")

        print(f"  Mentor:  {m.slug}")
        print(f"  Version: v{old_version}")
        print(f"  Curator: {m.curator}")
        print(f"  Bytes:   {old_bytes}")
        print(f"  Canon:   {old_canon[:80]}...")
        print()
        print(f"  Llamando a Promptifex SDD... (30-60s)")

        result = recurate_mentor(
            current_system_prompt=old_system_prompt,
            mentor_slug=m.slug,
            mentor_nombre=m.nombre,
            current_canon=old_canon or "",
            current_filosofia=old_filosofia or "",
        )

        new_version = old_version + 1
        new_system_prompt = result["new_system_prompt"]
        new_bytes = len(new_system_prompt)
        new_canon = result["new_canon"]
        new_filosofia = result["new_filosofia"]
        change_summary = result["change_summary"]
        evals = result["eval_suite"]["evals"]

        clean_slug = m.slug.replace("anoven-", "")
        eval_topic_key = f"anoven-{clean_slug}/eval-suite/v{new_version}"

        # Save eval suite a engram
        suite_content = json.dumps({
            "mentor_slug": m.slug,
            "version": new_version,
            "evals": evals,
            "change_summary": change_summary,
            "created_at": datetime.utcnow().isoformat(),
        }, ensure_ascii=False, indent=2)

        save_to_engram(
            project=f"anoven-{clean_slug}",
            topic_key=eval_topic_key,
            title=f"Eval suite v{new_version} — {m.slug}",
            content=suite_content,
        )

        # Update mentor en BD
        m.system_prompt = new_system_prompt
        m.canon = new_canon
        m.filosofia = new_filosofia
        m.version = new_version
        m.curator = "promptifex_sdd"
        m.curated_at = datetime.utcnow()
        m.eval_suite_topic_key = eval_topic_key
        db.commit()

        ratio = new_bytes / max(old_bytes, 1)
        print()
        print(f"  ✅ Curación completada")
        print(f"  Old version: v{old_version} → v{new_version}")
        print(f"  Old bytes:   {old_bytes} → {new_bytes} ({ratio*100:.0f}%)")
        print(f"  Evals:       {len(evals)}")
        print(f"  Topic key:   {eval_topic_key}")
        print()
        print(f"  Change summary:")
        for line in change_summary.split("\n")[:10]:
            print(f"    {line}")
        print()
        print(f"  New canon: {new_canon[:120]}")
        return 0

    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 curate_one.py {slug}")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
