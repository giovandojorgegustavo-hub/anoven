"""
Modelo InterviewMessage — un mensaje dentro de un intento de entrevista.

Cada InterviewAttempt tiene una lista ordenada de mensajes (user + assistant).
El primer mensaje SIEMPRE es del assistant (el saludo inicial pre-escrito).

Mantenemos esto SEPARADO de la futura tabla `messages` (Fase 3, chat con mentores)
porque la entrevista es estructuralmente distinta: tiene un ciclo de vida cerrado
(in_progress → completed → evaluated) y produce un score + profile.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InterviewMessage(Base):
    __tablename__ = "interview_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    interview_attempt_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("interview_attempts.id"),
        index=True,
        nullable=False,
    )

    # "user" | "assistant" — coincide con lo que espera Anthropic en `messages=`.
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<InterviewMessage id={self.id} attempt={self.interview_attempt_id} role={self.role}>"
