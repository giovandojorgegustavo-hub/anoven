"""
Endpoints de invitaciones del proyecto.

Montado en: /api/projects/invitations

Invariante A1.1 Clean/Hex: solo traducción HTTP → servicios.
Invariante A1.3: cero imports de fastapi en los servicios.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.project_invitation import InvitationRead, InvitationCountRead
from app.services.project_member_service import (
    ProjectMemberService,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    InvitationNotYoursError,
    MaxMembersReachedError,
)


router = APIRouter(prefix="/api/projects/invitations", tags=["project-invitations"])


def _build_invitation_read(inv, db: Session) -> InvitationRead:
    """Construye InvitationRead cargando relaciones con selectinload."""
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select as sa_select
    from app.models.project_invitation import ProjectInvitation
    loaded = db.execute(
        sa_select(ProjectInvitation)
        .options(
            selectinload(ProjectInvitation.project),
            selectinload(ProjectInvitation.invited_user),
            selectinload(ProjectInvitation.invited_by),
        )
        .where(ProjectInvitation.id == inv.id)
    ).scalars().first()
    return InvitationRead(
        id=loaded.id,
        project_id=loaded.project_id,
        project_name=loaded.project.name,
        invited_user_email=loaded.invited_user.email,
        invited_by_user_email=loaded.invited_by.email,
        status=loaded.status,
        expires_at=loaded.expires_at,
        created_at=loaded.created_at,
        responded_at=loaded.responded_at,
    )


# ── Pending invitations ───────────────────────────────────────────────────────

@router.get(
    "/pending",
    response_model=list[InvitationRead],
)
def list_pending(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lista las invitaciones pendientes del user (filtradas por expires_at > NOW()).
    Endpoint read-only — sin side effects (ADR-7, Issue 3 resolved).
    Cache-Control: no-store para polling de badge.
    """
    from fastapi.responses import JSONResponse
    svc = ProjectMemberService(db)
    invitations = svc.list_my_invitations(current_user.id)
    result = [_build_invitation_read(inv, db) for inv in invitations]
    return result


# ── Unread count ──────────────────────────────────────────────────────────────

@router.get(
    "/unread-count",
    response_model=InvitationCountRead,
)
def unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cantidad de invitaciones pendientes no vencidas — para el badge del header.
    Diseñado para polling cada 30s (ADR-6).
    """
    svc = ProjectMemberService(db)
    count = svc.count_my_pending_invitations(current_user.id)
    return InvitationCountRead(count=count)


# ── Accept invitation ─────────────────────────────────────────────────────────

@router.post(
    "/{invitation_id}/accept",
    status_code=status.HTTP_200_OK,
)
def accept_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Acepta una invitación al proyecto.
    Solo el invitado puede aceptar su propia invitación.
    """
    svc = ProjectMemberService(db)
    try:
        member = svc.accept_invitation(
            invitation_id=invitation_id,
            current_user_id=current_user.id,
        )
    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La invitación no existe.",
        )
    except InvitationNotYoursError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta invitación no te pertenece.",
        )
    except InvitationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="La invitación venció. Pide al owner que te invite de nuevo.",
        )
    except InvitationNotPendingError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"La invitación ya fue resuelta (estado: {e.status}).",
        )
    except MaxMembersReachedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El proyecto ya alcanzó el máximo de 20 miembros.",
        )

    return {"ok": True, "project_id": member.project_id, "role": member.role}


# ── Reject invitation ─────────────────────────────────────────────────────────

@router.post(
    "/{invitation_id}/reject",
    status_code=status.HTTP_200_OK,
)
def reject_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Rechaza una invitación al proyecto.
    Solo el invitado puede rechazar su propia invitación.
    """
    svc = ProjectMemberService(db)
    try:
        svc.reject_invitation(
            invitation_id=invitation_id,
            current_user_id=current_user.id,
        )
    except InvitationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La invitación no existe.",
        )
    except InvitationNotYoursError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta invitación no te pertenece.",
        )
    except InvitationExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="La invitación ya venció.",
        )
    except InvitationNotPendingError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"La invitación ya fue resuelta (estado: {e.status}).",
        )

    return {"ok": True}
