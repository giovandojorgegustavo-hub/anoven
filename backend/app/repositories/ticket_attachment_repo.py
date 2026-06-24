"""
Repository TicketAttachment — traducción SQLAlchemy → dominio.

NUNCA lógica de negocio aquí. NUNCA imports de fastapi.
"""

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.ticket_attachment import TicketAttachment


class TicketAttachmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, ticket_id: int, **fields) -> TicketAttachment:
        """Inserta un nuevo attachment para el ticket dado."""
        att = TicketAttachment(ticket_id=ticket_id, **fields)
        self.db.add(att)
        self.db.flush()
        return att

    def list_for_ticket(self, ticket_id: int) -> list[TicketAttachment]:
        """Lista todos los attachments de un ticket, ordenados por created_at ASC."""
        stmt = (
            select(TicketAttachment)
            .where(TicketAttachment.ticket_id == ticket_id)
            .order_by(TicketAttachment.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_for_ticket(self, ticket_id: int) -> int:
        """Cuenta los attachments de un ticket — para hacer cumplir el límite de 3."""
        stmt = (
            select(func.count())
            .select_from(TicketAttachment)
            .where(TicketAttachment.ticket_id == ticket_id)
        )
        return self.db.execute(stmt).scalar_one()

    def get_by_id(self, attachment_id: int) -> TicketAttachment | None:
        return self.db.get(TicketAttachment, attachment_id)

    def delete_for_ticket(self, ticket_id: int) -> None:
        """Elimina todos los attachments de un ticket (la DB CASCADE también lo hace, pero se expone para tests)."""
        stmt = select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id)
        for att in self.db.execute(stmt).scalars().all():
            self.db.delete(att)
        self.db.flush()
