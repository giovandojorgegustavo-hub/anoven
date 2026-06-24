"""
Endpoints de gestión de members del proyecto.

Montado en: /api/projects/{project_id}/members

Invariante A1.1 Clean/Hex:
  Este módulo SOLO traduce HTTP → servicios. Cero lógica de negocio aquí.
  Toda la validación de reglas vive en project_member_service.py.

Invariante A1.3:
  Los servicios a los que llamamos NO importan fastapi. Solo las
  excepciones de dominio se mapean a HTTPException aquí.

Nota sobre require_project_member/owner:
  Las factories de deps.py requieren project_id al momento de definir la
  ruta (no en runtime). Para rutas con {project_id} en el path usamos
  verificación inline directa — mismo comportamiento, sin magia.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.project_member import ProjectMemberRead
from app.schemas.project_invitation import InvitationCreate, InvitationRead
from app.services.project_member_service import (
    ProjectMemberService,
    AlreadyMemberError,
    CannotKickSelfError,
    InvitationAlreadyPendingError,
    MaxMembersReachedError,
    NotMemberError,
    OwnerCannotLeaveError,
    ProjectNotShareableError,
    TargetNotMemberError,
    UserNotFoundError,
)


router = APIRouter(prefix="/api/projects", tags=["project-members"])


def _assert_member(db: Session, project_id: int, user_id: int):
    """Inline guard: 403 si el user no es member del proyecto."""
    from app.repositories.project_member_repo import ProjectMemberRepository
    pm = ProjectMemberRepository(db).get_by_project_user(project_id, user_id)
    if pm is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eres miembro de este proyecto.",
        )
    return pm


def _assert_owner(db: Session, project_id: int, user_id: int):
    """Inline guard: 403 si el user no es owner del proyecto."""
    from app.repositories.project_member_repo import ProjectMemberRepository
    pm = ProjectMemberRepository(db).get_by_project_user(project_id, user_id)
    if pm is None or pm.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el owner del proyecto puede hacer esto.",
        )
    return pm


# ── List members ──────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/members",
    response_model=list[ProjectMemberRead],
)
def list_members(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lista todos los members del proyecto.
    Requiere ser member (o owner).
    """
    svc = ProjectMemberService(db)
    try:
        members = svc.list_members(project_id=project_id, requesting_user_id=current_user.id)
    except NotMemberError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eres miembro de este proyecto.",
        )

    result = []
    for m in members:
        result.append(ProjectMemberRead(
            id=m.id,
            project_id=m.project_id,
            user_id=m.user_id,
            user_email=m.user.email,
            user_nombre=m.user.full_name or m.user.email,
            role=m.role,
            joined_at=m.joined_at,
            invited_by_user_id=m.invited_by_user_id,
        ))
    return result


# ── Invite member ─────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/members/invite",
    response_model=InvitationRead,
    status_code=status.HTTP_201_CREATED,
)
def invite_member(
    project_id: int,
    payload: InvitationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Invita a un usuario al proyecto por email.
    Solo el owner puede invitar.
    """
    _assert_owner(db, project_id, current_user.id)

    svc = ProjectMemberService(db)
    try:
        inv = svc.invite_user(
            project_id=project_id,
            invited_user_email=payload.invited_user_email,
            invited_by_user_id=current_user.id,
            days_to_expire=payload.days_to_expire,
        )
    except ProjectNotShareableError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El proyecto General no se puede compartir.",
        )
    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El email no está registrado en Anoven.",
        )
    except AlreadyMemberError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese usuario ya es miembro del proyecto.",
        )
    except InvitationAlreadyPendingError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya hay una invitación pendiente para ese usuario.",
        )
    except MaxMembersReachedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El proyecto ya tiene el máximo de 20 miembros.",
        )

    # Cargar relaciones con selectinload para evitar lazy="raise"
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select as sa_select
    from app.models.project_invitation import ProjectInvitation
    inv_loaded = db.execute(
        sa_select(ProjectInvitation)
        .options(
            selectinload(ProjectInvitation.project),
            selectinload(ProjectInvitation.invited_user),
        )
        .where(ProjectInvitation.id == inv.id)
    ).scalars().first()

    return InvitationRead(
        id=inv_loaded.id,
        project_id=inv_loaded.project_id,
        project_name=inv_loaded.project.name,
        invited_user_email=inv_loaded.invited_user.email,
        invited_by_user_email=current_user.email,
        status=inv_loaded.status,
        expires_at=inv_loaded.expires_at,
        created_at=inv_loaded.created_at,
        responded_at=inv_loaded.responded_at,
    )


# ── Kick member ───────────────────────────────────────────────────────────────

@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def kick_member(
    project_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Elimina a un member del proyecto.
    Solo el owner puede hacerlo. El owner no puede eliminarse a sí mismo.
    """
    _assert_owner(db, project_id, current_user.id)

    svc = ProjectMemberService(db)
    try:
        svc.kick_member(
            project_id=project_id,
            target_user_id=user_id,
            owner_user_id=current_user.id,
        )
    except TargetNotMemberError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ese usuario no es miembro del proyecto.",
        )
    except CannotKickSelfError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminarte a ti mismo. Usa /leave o borra el proyecto.",
        )

    return None


# ── Leave project ─────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    El user sale del proyecto como member.
    El owner no puede salir por esta ruta.
    """
    _assert_member(db, project_id, current_user.id)

    svc = ProjectMemberService(db)
    try:
        svc.leave_project(project_id=project_id, current_user_id=current_user.id)
    except OwnerCannotLeaveError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El owner no puede salir. Borra el proyecto o transfiere el ownership (no disponible en v1).",
        )

    return None
