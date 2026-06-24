"""
Modelo CostEvent — telemetría por turn de chat.

Cada respuesta del mentor genera un row con tokens consumidos + costo USD.
Usado para business intel (cuánto cuesta cada user, cada mentor, cada
conversation). No se le muestra al user; es interno.

billed_user_id (agregado en anoven-shared-projects):
  - NULL  → proyecto privado (un solo member); el costo lo paga el caller (user_id).
  - NOT NULL → proyecto compartido; el owner paga aunque otro member haya
               iniciado el chat. Esto permite el dashboard de costo por owner.

  user_id   = quién hizo el request (member o owner).
  billed_user_id = quién paga el costo (siempre el owner del proyecto).

  Para proyectos privados: ambos son el mismo user (billed_user_id = NULL por
  compatibilidad histórica, o podría ser igual a user_id).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CostEvent(Base):
    __tablename__ = "cost_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversations.id"), index=True, nullable=True
    )
    mentor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mentors.id"), index=True, nullable=True
    )

    # NULL = proyecto privado (legacy o single-member).
    # NOT NULL = owner del proyecto que paga el costo cuando es proyecto compartido.
    # Columna agregada en migración shared_projects_001_create.sql.
    billed_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    model: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usd_cost: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)

    # "chat" | "evaluator" | "matcher" | "title" | "promptifex"
    purpose: Mapped[str] = mapped_column(String(30), default="chat", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CostEvent id={self.id} user={self.user_id} usd={self.usd_cost} "
            f"purpose={self.purpose}>"
        )
