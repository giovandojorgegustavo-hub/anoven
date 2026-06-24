"""
Endpoints de mentores.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.mentor import Mentor, UserMentor
from app.models.user import User
from app.repositories.mentor_repo import MentorRepository
from app.schemas.mentor import MentorCatalogItem, MyMentorResponse, MentorResponse
from app.services.mentor_service import MentorService
from app.core.deps import get_current_user


router = APIRouter(prefix="/mentors", tags=["mentors"])


@router.get("/creator", response_model=MentorResponse)
def get_creator(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Devuelve el mentor 'anoven-creador' (visibility='special') para que el
    frontend pueda iniciar chat con él desde el botón "+ Crear mentor".
    No requiere user_mentor assignment.
    """
    repo = MentorRepository(db)
    creador = repo.get_by_slug("anoven-creador")
    if creador is None or creador.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El Creador no está disponible.",
        )
    return MentorResponse.model_validate(creador)


@router.get("/catalog", response_model=list[MentorCatalogItem])
def get_catalog(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Devuelve los mentores que el user PUEDE agregarse a su workspace.

    Filtros:
      - status='active' (no draft, no archived)
      - visibility='global' (NO private, NO special — excluye Creador)
      - excluye los que el user ya tiene asignados activos (UserMentor.active=True)

    Pensado para una UI tipo "+ Agregar mentor" que muestra solo lo agregable.
    """
    # Subquery: mentor_ids del user con asignación activa.
    already_assigned_subq = (
        select(UserMentor.mentor_id)
        .where(UserMentor.user_id == current_user.id)
        .where(UserMentor.active == True)
    )

    stmt = (
        select(Mentor)
        .where(Mentor.status == "active")
        .where(Mentor.visibility == "global")
        .where(Mentor.id.notin_(already_assigned_subq))
        .order_by(Mentor.nombre.asc())
    )
    mentors = list(db.execute(stmt).scalars())
    return [MentorCatalogItem.model_validate(m) for m in mentors]


@router.get("/me", response_model=list[MyMentorResponse])
def my_mentors(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve los mentores asignados al user logueado."""
    service = MentorService(db)
    data = service.list_user_mentors_with_data(current_user.id)
    return [
        MyMentorResponse(
            mentor=MentorResponse.model_validate(item["mentor"]),
            source=item["source"],
            match_reason=item.get("match_reason"),
            assigned_at=item["assigned_at"],
        )
        for item in data
    ]
