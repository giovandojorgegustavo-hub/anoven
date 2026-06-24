"""
Modelo Conversation — una charla entre un user y un mentor.

Un user puede tener N conversations con un mismo mentor (cada una con su
contexto propio). El `title` se autogenera en Sesión 3.4 después del primer
turn del user. En 3.1 queda NULL.

Separado de InterviewAttempt porque las entrevistas tienen ciclo de vida
(in_progress → completed → evaluated) y producen score + profile. Las
conversaciones son abiertas y continuas — sin score, sin cierre forzado.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    mentor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mentors.id"),
        index=True,
        nullable=False,
    )

    # Use case al que pertenece la conversación. Si es NULL, la conversación
    # se considera del default use_case del default project del user.
    use_case_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("use_cases.id"),
        index=True,
        nullable=True,
    )

    # Título corto generado por LLM tras el primer turn del user (Sesión 3.4).
    # En 3.1 queda NULL — el frontend muestra "Conversación #{id}" si está vacío.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Se actualiza con cada mensaje nuevo — para ordenar en la sidebar.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Última vez que el user "vió" la conversación (abrió el chat). Si
    # last_seen_at < updated_at → hay mensajes no leídos → bold en sidebar.
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Star / focus para filtrar conversaciones importantes en la sidebar.
    is_focused: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation id={self.id} user={self.user_id} "
            f"mentor={self.mentor_id} title={self.title!r}>"
        )
