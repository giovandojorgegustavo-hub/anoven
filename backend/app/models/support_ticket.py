"""
Modelo SupportTicket — tickets de soporte enviados por usuarios.

Flujo de dos pasos:
  1. POST /api/tickets          → crea el ticket, devuelve ticket_id
  2. POST /api/tickets/{id}/attachments → adjunta imágenes (mín 1, máx 3)

El ticket es el aggregate root del dominio de soporte. Las transiciones de
estado se hacen SOLO a través de `transition_to(new_status)` para garantizar
las invariantes del ciclo de vida.

State machine:
  open ──► in_progress ──► closed
  open ──────────────────► closed
  closed ────────────────► open
  closed ────────────────► in_progress
  in_progress ───────────► open
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.ticket_attachment import TicketAttachment


# Valores permitidos para ticket_type
ALLOWED_TYPES = ("bug", "mejora", "pregunta", "otro")

# Valores permitidos para status
ALLOWED_STATUSES = ("open", "in_progress", "closed")

# Valores permitidos para priority (v1 — not exposed in API yet, reserved)
ALLOWED_PRIORITIES = ("low", "normal", "high")

# Transiciones válidas: {estado_actual: {estados_destino_permitidos}}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open":        {"in_progress", "closed"},
    "in_progress": {"closed", "open"},
    "closed":      {"open", "in_progress"},
}


class InvalidStateTransition(Exception):
    """Se lanza cuando una transición de estado no está permitida."""
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Transición no permitida: {from_status} → {to_status}"
        )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    mentor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mentors.id", ondelete="SET NULL"), nullable=True
    )

    ticket_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")

    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # lazy="raise" forza a que todo acceso a attachments sea explícito con selectinload
    # Falla en runtime si el código intenta acceder sin cargar correctamente — louder > silent N+1
    attachments: Mapped[list["TicketAttachment"]] = relationship(
        "TicketAttachment",
        back_populates="ticket",
        lazy="raise",
        cascade="all, delete-orphan",
    )

    def transition_to(self, new_status: str) -> None:
        """
        Aplica una transición de estado validada.

        Effectos secundarios:
          - Si → closed: setea closed_at
          - Si ← closed (reopen): limpia closed_at
          - Si → in_progress o closed por primera vez: setea responded_at si no está seteado

        Raises:
          InvalidStateTransition: si la transición no está permitida
        """
        if new_status not in ALLOWED_STATUSES:
            raise InvalidStateTransition(self.status, new_status)

        current = self.status
        if new_status == current:
            raise InvalidStateTransition(current, new_status)

        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise InvalidStateTransition(current, new_status)

        self.status = new_status
        now = datetime.now(timezone.utc)

        if new_status == "closed":
            self.closed_at = now
            if self.responded_at is None:
                self.responded_at = now
        elif new_status in ("open", "in_progress") and current == "closed":
            # reopen — clear closed_at but keep responded_at + admin_response as history
            self.closed_at = None

    def __repr__(self) -> str:
        return (
            f"<SupportTicket id={self.id} user={self.user_id} "
            f"type={self.ticket_type!r} status={self.status!r}>"
        )
