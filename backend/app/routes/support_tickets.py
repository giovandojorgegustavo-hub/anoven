"""
Endpoints de soporte para usuarios.

Mounted prefix: /api/tickets (ver main.py)
Auth: get_current_user (Bearer JWT)

A1.1 Clean/Hex — este módulo traduce HTTP → service → HTTP.
NUNCA lógica de negocio aquí.
"""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User
from app.repositories.support_ticket_repo import SupportTicketRepository
from app.repositories.ticket_attachment_repo import TicketAttachmentRepository
from app.repositories.user_repo import UserRepository
from app.services.ticket_storage_adapter import TicketStorageAdapter, AttachmentStorageError
from app.services.support_ticket_service import (
    SupportTicketService,
    TicketNotFoundError,
    TicketForbiddenError,
    RateLimitExceededError,
    AttachmentValidationError,
    AttachmentNotFoundError,
)
from app.schemas.support_ticket import AttachmentRead, TicketCreate, TicketRead


logger = logging.getLogger(__name__)

router = APIRouter(tags=["tickets"])

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


def _attachment_url(request_base: str, ticket_id: int, attachment_id: int) -> str:
    return f"/api/tickets/{ticket_id}/attachments/{attachment_id}/file"


def _ticket_to_read(ticket) -> TicketRead:
    attachments = []
    for att in (ticket.attachments or []):
        attachments.append(AttachmentRead(
            id=att.id,
            original_name=att.original_name,
            mime_type=att.mime_type,
            size_bytes=att.size_bytes,
            file_url=_attachment_url("", att.ticket_id, att.id),
        ))
    return TicketRead(
        id=ticket.id,
        ticket_type=ticket.ticket_type,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        admin_response=ticket.admin_response,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        responded_at=ticket.responded_at,
        closed_at=ticket.closed_at,
        conversation_id=ticket.conversation_id,
        mentor_id=ticket.mentor_id,
        attachments=attachments,
    )


# ── Flexible auth dependency (header OR query param) ─────────────────────────
# Used ONLY for the attachment-serving endpoint where <img src> cannot set
# Authorization headers. All other endpoints use the standard get_current_user.

_bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user_flexible(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme_optional),
    token_query: str | None = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """
    Acepta JWT desde Authorization: Bearer <token> O desde ?token=<jwt>.
    Útil para endpoints consumidos por <img src="...?token=jwt"> donde
    el browser no puede enviar headers de Authorization.

    Nunca retorna None — lanza 401 si no se puede autenticar.
    """
    raw_token: str | None = None

    # Prefer Authorization header if present
    if credentials is not None:
        raw_token = credentials.credentials
    elif token_query is not None:
        raw_token = token_query

    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_access_token(raw_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no existe.",
        )

    return user


# ── POST /api/tickets ─────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=TicketRead)
async def create_ticket(
    ticket_in: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Crea un ticket de soporte. El ticket se crea sin adjuntos — se adjuntan
    en un segundo paso via POST /api/tickets/{id}/attachments.
    """
    service = _make_service(db)
    try:
        ticket = service.create_ticket(
            user_id=current_user.id,
            ticket_in=ticket_in,
        )
        db.commit()
        db.refresh(ticket)
        return _ticket_to_read(ticket)
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )


# ── POST /api/tickets/{ticket_id}/attachments ─────────────────────────────────

@router.post("/{ticket_id}/attachments", status_code=status.HTTP_201_CREATED, response_model=AttachmentRead)
async def upload_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Adjunta una imagen (PNG, JPEG, WebP) a un ticket existente.
    El usuario debe ser el dueño del ticket.
    """
    file_data = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    original_filename = file.filename or "attachment"

    service = _make_service(db)
    try:
        att = service.add_attachment_to_ticket(
            user_id=current_user.id,
            ticket_id=ticket_id,
            file_data=file_data,
            original_filename=original_filename,
            mime_type=mime_type,
        )
        db.commit()
        db.refresh(att)
        return AttachmentRead(
            id=att.id,
            original_name=att.original_name,
            mime_type=att.mime_type,
            size_bytes=att.size_bytes,
            file_url=_attachment_url("", ticket_id, att.id),
        )
    except AttachmentValidationError as e:
        code = getattr(e, "code", "validation_error")
        if code == "file_too_large":
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=str(e),
            )
        if code == "unsupported_media_type":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket no encontrado.",
        )
    except TicketForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para adjuntar archivos a este ticket.",
        )
    except AttachmentStorageError as e:
        logger.exception(f"Storage error ticket={ticket_id} user={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno. Reintenta.",
        )


# ── GET /api/tickets/mine ─────────────────────────────────────────────────────

@router.get("/mine", response_model=list[TicketRead])
async def list_my_tickets(
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista los tickets del usuario autenticado, más reciente primero."""
    service = _make_service(db)
    tickets = service.list_user_tickets(
        user_id=current_user.id,
        status=status_filter,
    )
    return [_ticket_to_read(t) for t in tickets]


# ── GET /api/tickets/{ticket_id} ──────────────────────────────────────────────

@router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Devuelve el ticket del usuario.
    403 si el ticket existe pero pertenece a otro usuario (NO 404).
    """
    service = _make_service(db)
    try:
        ticket = service.get_user_ticket(user_id=current_user.id, ticket_id=ticket_id)
        return _ticket_to_read(ticket)
    except TicketForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver este ticket.",
        )
    except TicketNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket no encontrado.",
        )


# ── GET /api/tickets/{ticket_id}/attachments/{attachment_id}/file ─────────────

@router.get("/{ticket_id}/attachments/{attachment_id}/file")
async def serve_attachment(
    ticket_id: int,
    attachment_id: int,
    current_user: User = Depends(get_current_user_flexible),
    db: Session = Depends(get_db),
):
    """
    Sirve el archivo adjunto. Solo el dueño del ticket o un admin puede acceder.

    Acepta autenticación via Authorization header O ?token= query param.
    El segundo método permite que <img src="...?token=jwt"> funcione en el
    frontend sin necesidad de proxying adicional.

    X6.4: NO leakea información del filesystem en errores — solo 404 genérico.
    """
    is_admin = current_user.role == "admin"
    service = _make_service(db)
    try:
        data, mime_type, original_name = service.read_attachment(
            attachment_id=attachment_id,
            requester_user_id=current_user.id,
            is_admin=is_admin,
        )
    except AttachmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo no encontrado.",
        )
    except TicketForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver este archivo.",
        )
    except AttachmentStorageError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo no encontrado.",
        )

    # Usar FileResponse con ruta absoluta para eficiencia
    storage = TicketStorageAdapter(_STORAGE_ROOT)
    att_repo = TicketAttachmentRepository(db)
    att = att_repo.get_by_id(attachment_id)
    if att is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo no encontrado.",
        )
    abs_path = storage.get_absolute_path(att.file_path)
    if not abs_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo no encontrado.",
        )

    return FileResponse(
        path=str(abs_path),
        media_type=mime_type,
        filename=original_name,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="{original_name}"',
        },
    )
