"""
Modelo InterviewAttempt — un intento de entrevista de onboarding.

Un user puede tener varios intentos (si falla, reintenta). Cada uno tiene
su propio score, feedback y profile extraído.

La diferencia con User.onboarding_state:
  - `User.onboarding_state` resume el estado GLOBAL del user (pending | in_progress | passed | failed_quality).
  - `InterviewAttempt` guarda CADA intento puntual con su track record.

Así si un user falla el primer intento y pasa el segundo, queda registro
auditable de ambos.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InterviewAttempt(Base):
    __tablename__ = "interview_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    # Estado del intento puntual:
    #   "in_progress" → el user está hablando con el Entrevistador
    #   "completed"   → el Entrevistador emitió [INTERVIEW_COMPLETE], esperando al Evaluador
    #   "evaluated"   → el Evaluador asignó score (pasó o no, eso vive en User.onboarding_state)
    #   "abandoned"   → timeout o cancelación
    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)

    # Resultado de la evaluación (NULL hasta que corre el Evaluador en Sesión 2.4).
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Feedback que le mostramos al user si falla (qué le faltó a la entrevista).
    evaluator_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Perfil JSON extraído por el Entrevistador. Lo usa MentorMatcher (Sesión 2.5).
    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<InterviewAttempt id={self.id} user={self.user_id} "
            f"status={self.status} score={self.score}>"
        )
