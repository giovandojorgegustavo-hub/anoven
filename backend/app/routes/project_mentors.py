"""
Endpoints de gestión de mentores asignados al proyecto.

Montado en: /api/projects/{project_id}/mentors

Invariante A1.1 Clean/Hex: solo traducción HTTP → servicios.
Invariante A1.3: cero imports de fastapi en los servicios.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.project_mentor import ProjectMentorCreate, ProjectMentorRead
from app.services.project_mentor_service import (
    ProjectMentorService,
    MentorAlreadyAssignedError,
    MentorNotAssignedError,
    MentorNotFoundError,
)
from app.services.project_member_service import NotMemberError, NotOwnerError


router = APIRouter(prefix="/api/projects", tags=["project-mentors"])


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


# ── List mentors ──────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/mentors",
    response_model=list[ProjectMentorRead],
)
def list_mentors(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lista los mentores asignados al proyecto.
    Requiere ser member (o owner).
    """
    svc = ProjectMentorService(db)
    try:
        mentors = svc.list_mentors(project_id=project_id, requesting_user_id=current_user.id)
    except NotMemberError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eres miembro de este proyecto.",
        )

    result = []
    for pm in mentors:
        result.append(ProjectMentorRead(
            id=pm.id,
            project_id=pm.project_id,
            mentor_id=pm.mentor_id,
            mentor_slug=pm.mentor.slug,
            mentor_nombre=pm.mentor.nombre,
            added_by_user_email=pm.added_by.email,
            added_at=pm.added_at,
        ))
    return result


# ── Add mentor ────────────────────────────────────────────────────────────────

@router.post(
    "/{project_id}/mentors",
    response_model=ProjectMentorRead,
    status_code=status.HTTP_201_CREATED,
)
def add_mentor(
    project_id: int,
    payload: ProjectMentorCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Asigna un mentor al proyecto.
    Solo el owner puede asignar mentores.
    """
    _assert_owner(db, project_id, current_user.id)

    svc = ProjectMentorService(db)
    try:
        pm = svc.add_mentor(
            project_id=project_id,
            mentor_id=payload.mentor_id,
            owner_user_id=current_user.id,
        )
    except MentorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El mentor no existe o no está disponible.",
        )
    except MentorAlreadyAssignedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese mentor ya está asignado a este proyecto.",
        )

    # Cargar relaciones para la respuesta
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select as sa_select
    from app.models.project_mentor import ProjectMentor
    pm_loaded = db.execute(
        sa_select(ProjectMentor)
        .options(
            selectinload(ProjectMentor.mentor),
            selectinload(ProjectMentor.added_by),
        )
        .where(ProjectMentor.id == pm.id)
    ).scalars().first()

    return ProjectMentorRead(
        id=pm_loaded.id,
        project_id=pm_loaded.project_id,
        mentor_id=pm_loaded.mentor_id,
        mentor_slug=pm_loaded.mentor.slug,
        mentor_nombre=pm_loaded.mentor.nombre,
        added_by_user_email=pm_loaded.added_by.email,
        added_at=pm_loaded.added_at,
    )


# ── Remove mentor ─────────────────────────────────────────────────────────────

@router.delete(
    "/{project_id}/mentors/{mentor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_mentor(
    project_id: int,
    mentor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Desasigna un mentor del proyecto.
    Solo el owner puede hacerlo.
    """
    _assert_owner(db, project_id, current_user.id)

    svc = ProjectMentorService(db)
    try:
        svc.remove_mentor(
            project_id=project_id,
            mentor_id=mentor_id,
            owner_user_id=current_user.id,
        )
    except MentorNotAssignedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ese mentor no está asignado a este proyecto.",
        )

    return None
