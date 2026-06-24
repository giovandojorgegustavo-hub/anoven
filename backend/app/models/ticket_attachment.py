"""
Modelo TicketAttachment — imágenes adjuntas a support tickets.

Almacenamiento: ${ANOVEN_STORAGE_ROOT}/uploads/tickets/{ticket_id}/{uuid}.{ext}
El file_path en BD es relativo al ANOVEN_STORAGE_ROOT.

MIME permitidos: image/png, image/jpeg, image/webp
Tamaño máximo: 5 MB (5,242,880 bytes)
Máximo por ticket: 3
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.support_ticket import SupportTicket


# MIME types aceptados (validación también vía magic bytes en el service)
ALLOWED_MIMES = frozenset(["image/png", "image/jpeg", "image/webp"])

MAX_ATTACHMENT_SIZE_BYTES = 5_242_880  # 5 MB
MAX_ATTACHMENTS_PER_TICKET = 3


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    ticket: Mapped["SupportTicket"] = relationship(
        "SupportTicket",
        back_populates="attachments",
    )

    def __repr__(self) -> str:
        return (
            f"<TicketAttachment id={self.id} ticket={self.ticket_id} "
            f"mime={self.mime_type!r} size={self.size_bytes}>"
        )
