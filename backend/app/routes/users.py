"""
Endpoints de usuarios.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.cost_event import CostEvent
from app.models.mentor import Mentor, UserMentor
from app.models.mentor_request import MentorRequest
from app.models.user import User
from app.schemas.mentor import UserMentorAddRequest, UserMentorResponse
from app.schemas.user import UserResponse
from app.services.project_service import ProjectNotFound, ProjectService


router = APIRouter(prefix="/users", tags=["users"])


class ActiveProjectUpdate(BaseModel):
    project_id: int


class ResearchOptInUpdate(BaseModel):
    research_opt_in: bool


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Devuelve el usuario actualmente logueado.
    Endpoint PROTEGIDO — requiere Authorization: Bearer <token>."""
    return current_user


@router.patch("/me/active-project", response_model=UserResponse)
def switch_active_project(
    payload: ActiveProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cambia el project activo del user. Valida que el project sea suyo.
    El frontend llama esto cuando el user clickea otro project en el switcher.
    """
    service = ProjectService(db)
    try:
        project = service.get_for_user(payload.project_id, current_user.id)
    except ProjectNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    current_user.active_project_id = project.id
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/stats")
def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Usage stats del user logueado — para mostrar en Settings."""
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    total_convs = db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == current_user.id)
    ).scalar_one()

    total_usd = db.execute(
        select(func.coalesce(func.sum(CostEvent.usd_cost), 0)).where(
            CostEvent.user_id == current_user.id
        )
    ).scalar_one()
    usd_30d = db.execute(
        select(func.coalesce(func.sum(CostEvent.usd_cost), 0))
        .where(CostEvent.user_id == current_user.id)
        .where(CostEvent.created_at >= thirty_days_ago)
    ).scalar_one()
    turns_total = db.execute(
        select(func.count(CostEvent.id)).where(CostEvent.user_id == current_user.id)
    ).scalar_one()
    turns_30d = db.execute(
        select(func.count(CostEvent.id))
        .where(CostEvent.user_id == current_user.id)
        .where(CostEvent.created_at >= thirty_days_ago)
    ).scalar_one()

    return {
        "conversations": int(total_convs),
        "turns_total": int(turns_total),
        "turns_30d": int(turns_30d),
        "usd_total": float(total_usd),
        "usd_30d": float(usd_30d),
    }


@router.patch("/me/research-opt-in", response_model=UserResponse)
def update_research_opt_in(
    payload: ResearchOptInUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Toggle de research opt-in. Si True, Anoven puede usar las conversaciones
    del user (anonimizadas) para mejorar producto y marketing.
    """
    current_user.research_opt_in = payload.research_opt_in
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/pending-mentors")
def get_pending_mentors(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    FASE 7: lista los `MentorRequest` con status='pending' del user.

    Son mentores que el Evaluador detectó como dolor del user pero NO existen
    en el catálogo todavía. El user puede crearlos hablando con el Creador.
    """
    requests = db.execute(
        select(MentorRequest)
        .where(MentorRequest.user_id == current_user.id)
        .where(MentorRequest.status == "pending")
        .order_by(MentorRequest.created_at.desc())
    ).scalars().all()

    return [
        {
            "id": r.id,
            "proposed_name": r.proposed_name,
            "proposed_canon": r.proposed_canon,
            "why": r.why,
            "source": r.source,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in requests
    ]


# ===========================================================================
# Self-add / remove mentor — el user gestiona sus propios mentores del catálogo
# ===========================================================================


@router.post(
    "/me/mentors",
    response_model=UserMentorResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_mentor_to_self(
    payload: UserMentorAddRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    El user agrega un mentor del catálogo a su workspace.

    Valida:
      - mentor existe (404)
      - mentor.status='active' (404 — no exponer drafts/archived)
      - mentor.visibility='global' (403 — no permite self-add de private/special)
      - user no lo tiene ya como UserMentor.active=True (409 duplicate)
      - si existe una asignación inactiva previa, la reactiva en lugar de duplicar

    Crea UserMentor con source='created_by_self' (convención del codebase —
    ver schemas/mentor.py).
    """
    mentor = db.get(Mentor, payload.mentor_id)
    if mentor is None or mentor.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mentor no encontrado o no disponible.",
        )

    if mentor.visibility != "global":
        # private / shareable / special no se autoasignan desde el catálogo.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este mentor no puede agregarse desde el catálogo.",
        )

    existing = db.execute(
        select(UserMentor)
        .where(UserMentor.user_id == current_user.id)
        .where(UserMentor.mentor_id == mentor.id)
    ).scalar_one_or_none()

    if existing is not None:
        if existing.active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya tenés este mentor asignado.",
            )
        # Reactivación: existía pero estaba soft-deleted. Lo reactivamos en su
        # source actual (no lo pisamos a 'created_by_self' si fue 'default').
        existing.active = True
        existing.assigned_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    um = UserMentor(
        user_id=current_user.id,
        mentor_id=mentor.id,
        source="created_by_self",
        active=True,
        assigned_at=datetime.utcnow(),
    )
    db.add(um)
    db.commit()
    db.refresh(um)
    return um


@router.delete(
    "/me/mentors/{mentor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_mentor_from_self(
    mentor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Soft-delete: el user "saca" un mentor de su workspace marcando la
    asignación como inactiva (active=False). NO se borra el registro —
    mantiene audit trail y permite reactivación vía POST /users/me/mentors.

    Aplica a CUALQUIER source (default, matched, created_by_self,
    assigned_by_admin). Esto es intencional: el user es dueño de su workspace.

    404 si no hay asignación activa para ese mentor.
    """
    um = db.execute(
        select(UserMentor)
        .where(UserMentor.user_id == current_user.id)
        .where(UserMentor.mentor_id == mentor_id)
        .where(UserMentor.active == True)
    ).scalar_one_or_none()

    if um is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenés este mentor asignado.",
        )

    um.active = False
    db.commit()
    # 204 No Content — FastAPI ignora el return body en 204.
    return None
