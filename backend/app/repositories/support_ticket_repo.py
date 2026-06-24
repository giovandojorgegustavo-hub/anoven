"""
Repository SupportTicket — traducción SQLAlchemy → dominio.

NUNCA lógica de negocio aquí. NUNCA imports de fastapi.
Solo traducción de queries a objetos de dominio.

Todos los métodos que devuelven SupportTicket usan selectinload(attachments)
para evitar N+1 (lazy="raise" en el modelo fuerza el cargado explícito).
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session, selectinload

from app.models.support_ticket import SupportTicket
from app.models.ticket_attachment import TicketAttachment


class SupportTicketRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Queries individuales ──────────────────────────────────────────────────

    def get_by_id(self, ticket_id: int) -> SupportTicket | None:
        """Carga el ticket con sus attachments (selectinload para evitar N+1)."""
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .options(selectinload(SupportTicket.attachments))
        )
        return self.db.execute(stmt).scalars().first()

    def get_for_user(self, user_id: int, ticket_id: int) -> SupportTicket | None:
        """Ticket del user específico — devuelve None si no es del user."""
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .where(SupportTicket.user_id == user_id)
            .options(selectinload(SupportTicket.attachments))
        )
        return self.db.execute(stmt).scalars().first()

    # ── Listas ────────────────────────────────────────────────────────────────

    def list_for_user(
        self,
        user_id: int,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """Todos los tickets del user, ordenados por created_at DESC."""
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .options(selectinload(SupportTicket.attachments))
            .order_by(desc(SupportTicket.created_at))
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(SupportTicket.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def list_all(
        self,
        status: str | None = None,
        ticket_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """Lista admin: todos los tickets con filtros opcionales, ordenados por created_at DESC."""
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.attachments))
            .order_by(desc(SupportTicket.created_at))
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(SupportTicket.status == status)
        if ticket_type is not None:
            stmt = stmt.where(SupportTicket.ticket_type == ticket_type)
        return list(self.db.execute(stmt).scalars().all())

    # ── Conteos ───────────────────────────────────────────────────────────────

    def count_unread_for_admin(self) -> int:
        """Tickets con status open — para el badge del admin."""
        stmt = (
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status == "open")
        )
        return self.db.execute(stmt).scalar_one()

    def count_recent_for_user(self, user_id: int, hours: int = 1) -> int:
        """Tickets creados por el user en las últimas N horas — para rate limit."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .where(SupportTicket.created_at >= cutoff)
        )
        return self.db.execute(stmt).scalar_one()

    # ── Escrituras ────────────────────────────────────────────────────────────

    def create(self, **fields) -> SupportTicket:
        """Inserta un nuevo ticket. Devuelve el objeto persistido con id asignado."""
        ticket = SupportTicket(**fields)
        self.db.add(ticket)
        self.db.flush()  # genera el id sin commit
        return ticket

    def update_status(
        self,
        ticket: SupportTicket,
        new_status: str,
        admin_user_id: int,
        admin_response: str | None = None,
    ) -> SupportTicket:
        """
        Aplica la transición de estado y persiste.
        La lógica de transición vive en ticket.transition_to() (domain method).
        """
        if admin_response is not None:
            ticket.admin_response = admin_response
            ticket.admin_user_id = admin_user_id
            if ticket.responded_at is None:
                ticket.responded_at = datetime.now(timezone.utc)

        ticket.transition_to(new_status)  # raises InvalidStateTransition si no permitida
        self.db.flush()
        return ticket

    def save(self, ticket: SupportTicket) -> SupportTicket:
        """Persiste cambios en un ticket ya en sesión (flush sin commit)."""
        self.db.flush()
        return ticket
