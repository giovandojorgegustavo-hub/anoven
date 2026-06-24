'''Backfill títulos para conversaciones que ya existen sin título.'''
import sys
from app.database import SessionLocal
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.services.title_generator import generate_title
from app.models import user, mentor, interview_attempt, interview_message, conversation, message  # noqa

db = SessionLocal()
repo = ConversationRepository(db)
msg_repo = MessageRepository(db)

for conv in repo.list_for_user(1):
    if conv.title:
        print(f'  conv #{conv.id}: ya tiene título: {conv.title}')
        continue
    msgs = msg_repo.list_for_conversation(conv.id)
    if len(msgs) < 2:
        print(f'  conv #{conv.id}: sin mensajes suficientes, skip')
        continue
    user_m = next((m for m in msgs if m.role == 'user'), None)
    asst_m = next((m for m in msgs if m.role == 'assistant'), None)
    if not user_m or not asst_m:
        print(f'  conv #{conv.id}: sin turn completo, skip')
        continue
    title = generate_title(user_m.content, asst_m.content)
    repo.set_title(conv.id, title)
    print(f'  conv #{conv.id}: "{title}"')

db.close()
