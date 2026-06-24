"""
Repository para InterviewMessage.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.interview_message import InterviewMessage


class InterviewMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_attempt(self, attempt_id: int) -> list[InterviewMessage]:
        """Mensajes de un intento, en orden cronológico."""
        stmt = (
            select(InterviewMessage)
            .where(InterviewMessage.interview_attempt_id == attempt_id)
            .order_by(InterviewMessage.created_at, InterviewMessage.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(self, attempt_id: int, role: str, content: str) -> InterviewMessage:
        msg = InterviewMessage(
            interview_attempt_id=attempt_id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg
