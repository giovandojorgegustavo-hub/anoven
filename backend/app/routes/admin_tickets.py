"""
Endpoints de administración de tickets.

Mounted prefix: /api/admin/tickets (ver main.py)
Auth: require_admin (role='admin' obligatorio)

A1.1 Clean/Hex — este módulo traduce HTTP → service → HTTP.
NUNCA lógica de negocio aquí.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.repositories.support_ticket_repo import SupportTicketRepository
from app.repositories.ticket_attachment_repo import TicketAttachmentRepository
from app.services.ticket_storage_adapter import TicketStorageAdapter
from app.services.support_ticket_service import (
    SupportTicketService,
    TicketNotFoundError,
    InvalidStatusTransitionError,
    MissingResponseForCloseError,
)
from app.schemas.support_ticket import (
    AttachmentRead,
    TicketReadAdmin,
    TicketRespondPayload,
    UnreadCountRead,
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-tickets"])

_STORAGE_ROOT = os.environ.get(
    "ANOVEN_STORAGE_ROOT",
    "/home/anoven/anoven-app/storage/uploads",
)


def _make_service(db: Session) -> SupportTicketService:
    return SupportTicketService(
        ticket_repo=SupportTicketRepository(db),
        attachment_repo=TicketAttachmentRepository(db),
        storage=TicketStorageAdapter(_STORAGE_ROOT),
    )


def _attachment_url(ticket_id: int, attachment_id: int) -> str:
    return f"/api/tickets/{ticket_id}/attachments/{attachment_id}/file"


def _ticket_to_admin_read(ticket) -> TicketReadAdmin:
    attachments = []
    for att in (ticket.attachments or []):
        attachments.append(AttachmentRead(
            id=att.id,
            original_name=att.original_name,
            mime_type=att.mime_type,
            size_bytes=att.size_bytes,
            file_url=_attachment_url(att.ticket_id, att.id),
        ))
    return TicketReadAdmin(
        id=ticket.id,
        user_id=ticket.user_id,
        ticket_type=ticket.ticket_type,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        admin_response=ticket.admin_response,
        admin_user_id=ticket.admin_user_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        responded_at=ticket.responded_at,
        closed_at=ticket.closed_at,
        conversation_id=ticket.conversation_id,
        mentor_id=ticket.mentor_id,
        attachments=attachments,
    )


# ── GET /api/admin/tickets/unread-count ───────────────────────────────────────
# IMPORTANTE: esta ruta va ANTES de /{ticket_id} para evitar que FastAPI
# interprete "unread-count" como un ticket_id entero.

@router.get("/unread-count", response_model=UnreadCountRead)
async def admin_unread_count(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Devuelve el conteo de tickets con status 'open'.
    Usado por el badge de polling en el panel admin (cada 30s).
    """
    service = _make_service(db)
    count = service.admin_unread_count()
    return UnreadCountRead(count=count)


# ── GET /api/admin/tickets ────────────────────────────────────────────────────

@router.get("", response_model=list[TicketReadAdmin])
async def admin_list_tickets(
    status_filter: str | None = Query(None, alias="status"),
    ticket_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lista todos los tickets con filtros opcionales. Solo admins."""
    service = _make_service(db)
    tickets = service.admin_list_tickets(
        status=status_filter,
        ticket_type=ticket_type,
    )
    return [_ticket_to_admin_read(t) for t in tickets]


# ── GET /api/admin/tickets/{ticket_id} ────────────────────────────────────────

@router.get("/{ticket_id}", response_model=TicketReadAdmin)
async def admin_get_ticket(
    ticket_id: int,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Devuelve el detalle de cualquier ticket. Solo admins."""
    service = _make_service(db)
    try:
        ticket = service.admin_get_ticket(ticket_id=ticket_id)
        return _ticket_to_admin_read(ticket)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket no encontrado.",
        )


# ── PATCH /api/admin/tickets/{ticket_id} ──────────────────────────────────────

@router.patch("/{ticket_id}", response_model=TicketReadAdmin)
async def admin_update_ticket(
    ticket_id: int,
    update_in: TicketRespondPayload,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    El admin responde y opcionalmente cambia el estado del ticket.
    new_status puede ser 'in_progress', 'closed' u omitirse.
    """
    service = _make_service(db)
    try:
        ticket = service.admin_update_ticket(
            ticket_id=ticket_id,
            update_in=update_in,
            admin_user_id=admin_user.id,
        )
        db.commit()
        db.refresh(ticket)
        return _ticket_to_admin_read(ticket)
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket no encontrado.",
        )
    except InvalidStatusTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Transición no permitida: {e.from_status} → {e.to_status}",
        )
    except MissingResponseForCloseError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
