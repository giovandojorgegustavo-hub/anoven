"""
Migración 5.1b: backfill de saludo inicial para conversations existentes
que están vacías (0 messages).

Razón: cambiamos `start_or_resume` para que TODOS los mentores inserten su
saludo al crear conversación. Las que ya existían sin mensajes (ej: conv #1
con Neuropsicología) no tienen ese saludo. Las llenamos.

Conversaciones con mensajes existentes NO se tocan — su flow histórico
queda como está.

Ejecutar UNA vez:
    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 migrate_5_1b.py
"""

import sys

from app.database import SessionLocal
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule,
)
from app.models.conversation import Conversation
from app.repositories.mentor_repo import MentorRepository
from app.repositories.message_repo import MessageRepository
from app.services.conversation_service import _build_initial_greeting


def main() -> int:
    db = SessionLocal()
    try:
        msg_repo = MessageRepository(db)
        mentor_repo = MentorRepository(db)
        convs = db.query(Conversation).all()

        backfilled = 0
        skipped_with_msgs = 0
        skipped_no_mentor = 0
        for c in convs:
            existing_msgs = msg_repo.list_for_conversation(c.id)
            if existing_msgs:
                skipped_with_msgs += 1
                continue
            mentor = mentor_repo.get_by_id(c.mentor_id)
            if mentor is None:
                skipped_no_mentor += 1
                continue
            greeting = _build_initial_greeting(mentor)
            if not greeting:
                continue
            msg_repo.create(conv_id=c.id, role="assistant", content=greeting)
            print(f"  conv #{c.id} ({mentor.nombre}) → saludo inicial ({len(greeting)} chars)")
            backfilled += 1

        print()
        print(f"✓ Backfilled {backfilled}  |  skip with msgs: {skipped_with_msgs}  |  skip no mentor: {skipped_no_mentor}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
