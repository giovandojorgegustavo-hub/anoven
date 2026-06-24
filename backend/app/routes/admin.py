"""
Endpoints de admin (role='admin' requerido).

Cubre:
  - Curation queue de mentores pending_review (5.5)
  - Overview: KPIs + breakdown de costos (Fase 7 admin panel)
  - Listado de users con métricas básicas
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.cost_event import CostEvent
from app.models.mentor import Mentor
from app.models.mentor_request import MentorRequest
from app.models.message import Message
from app.models.user import User
from app.repositories.mentor_repo import MentorRepository
from app.schemas.mentor import CurationResult, MentorCurationStatus, MentorResponse


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo admins pueden ver esta página.",
        )


@router.get("/overview")
def admin_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    KPIs + breakdowns para el dashboard admin. Una sola query bag para no
    armar N round-trips desde el frontend.
    """
    _require_admin(current_user)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    total_users = db.execute(select(func.count(User.id))).scalar_one()
    total_convs = db.execute(select(func.count(Conversation.id))).scalar_one()
    total_msgs = db.execute(select(func.count(Message.id))).scalar_one()
    recent_msgs_7d = db.execute(
        select(func.count(Message.id)).where(Message.created_at >= seven_days_ago)
    ).scalar_one()

    total_usd = (
        db.execute(select(func.coalesce(func.sum(CostEvent.usd_cost), 0))).scalar_one()
    )
    usd_7d = (
        db.execute(
            select(func.coalesce(func.sum(CostEvent.usd_cost), 0)).where(
                CostEvent.created_at >= seven_days_ago
            )
        ).scalar_one()
    )

    pending_mentors = db.execute(
        select(func.count(Mentor.id)).where(Mentor.status == "pending_review")
    ).scalar_one()

    # Top users por costo
    top_users_q = (
        select(
            User.id,
            User.email,
            User.nombre,
            func.coalesce(func.sum(CostEvent.usd_cost), 0).label("usd"),
            func.count(CostEvent.id).label("turns"),
        )
        .join(CostEvent, CostEvent.user_id == User.id, isouter=True)
        .group_by(User.id, User.email, User.nombre)
        .order_by(func.coalesce(func.sum(CostEvent.usd_cost), 0).desc())
        .limit(10)
    )
    top_users = [
        {
            "id": row.id,
            "email": row.email,
            "nombre": row.nombre,
            "usd": float(row.usd),
            "turns": int(row.turns),
        }
        for row in db.execute(top_users_q).all()
    ]

    # Top mentors por costo
    top_mentors_q = (
        select(
            Mentor.id,
            Mentor.slug,
            Mentor.nombre,
            func.coalesce(func.sum(CostEvent.usd_cost), 0).label("usd"),
            func.count(CostEvent.id).label("turns"),
        )
        .join(CostEvent, CostEvent.mentor_id == Mentor.id, isouter=False)
        .group_by(Mentor.id, Mentor.slug, Mentor.nombre)
        .order_by(func.coalesce(func.sum(CostEvent.usd_cost), 0).desc())
        .limit(10)
    )
    top_mentors = [
        {
            "id": row.id,
            "slug": row.slug,
            "nombre": row.nombre,
            "usd": float(row.usd),
            "turns": int(row.turns),
        }
        for row in db.execute(top_mentors_q).all()
    ]

    # Spend por día (últimos 14 días).
    # Usamos text() para el date_trunc así Postgres trata el 'day' como
    # literal SQL, no como bind param distinto entre SELECT y GROUP BY.
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    by_day_rows = db.execute(
        text(
            "SELECT date_trunc('day', created_at) AS day, "
            "COALESCE(SUM(usd_cost), 0) AS usd, "
            "COUNT(id) AS turns "
            "FROM cost_events "
            "WHERE created_at >= :since "
            "GROUP BY 1 "
            "ORDER BY 1 ASC"
        ),
        {"since": fourteen_days_ago},
    ).all()
    by_day = [
        {
            "day": row.day.isoformat() if row.day else None,
            "usd": float(row.usd),
            "turns": int(row.turns),
        }
        for row in by_day_rows
    ]

    return {
        "kpis": {
            "users": int(total_users),
            "conversations": int(total_convs),
            "messages_total": int(total_msgs),
            "messages_7d": int(recent_msgs_7d),
            "usd_total": float(total_usd),
            "usd_7d": float(usd_7d),
            "pending_mentors": int(pending_mentors),
        },
        "top_users": top_users,
        "top_mentors": top_mentors,
        "by_day": by_day,
    }


@router.get("/users")
def admin_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Listado de users con métricas: role, onboarding, conversaciones, costo."""
    _require_admin(current_user)

    rows = db.execute(
        select(
            User.id,
            User.email,
            User.nombre,
            User.role,
            User.onboarding_state,
            User.onboarding_attempts,
            User.research_opt_in,
            User.created_at,
            func.coalesce(func.sum(CostEvent.usd_cost), 0).label("usd"),
            func.count(Conversation.id.distinct()).label("conv_count"),
        )
        .join(CostEvent, CostEvent.user_id == User.id, isouter=True)
        .join(Conversation, Conversation.user_id == User.id, isouter=True)
        .group_by(User.id, User.email, User.nombre, User.role, User.onboarding_state, User.onboarding_attempts, User.research_opt_in, User.created_at)
        .order_by(User.id)
    ).all()

    return [
        {
            "id": r.id,
            "email": r.email,
            "nombre": r.nombre,
            "role": r.role,
            "onboarding_state": r.onboarding_state,
            "onboarding_attempts": r.onboarding_attempts,
            "research_opt_in": r.research_opt_in,
            "conv_count": int(r.conv_count or 0),
            "usd_spent": float(r.usd or 0),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/mentors/pending", response_model=list[MentorResponse])
def list_pending_mentors(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mentores con status='pending_review' a la espera de curación."""
    _require_admin(current_user)
    repo = MentorRepository(db)
    return [MentorResponse.model_validate(m) for m in repo.list_by_status("pending_review")]


@router.patch("/mentors/{mentor_id}/approve", response_model=MentorResponse)
def approve_mentor(
    mentor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aprueba el mentor: pasa a status='active', visibility='global'."""
    _require_admin(current_user)
    repo = MentorRepository(db)
    m = repo.get_by_id(mentor_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mentor no existe.")
    updated = repo.update_status_visibility(m, status="active", visibility="global")
    return MentorResponse.model_validate(updated)


@router.get("/mentor-requests")
def list_mentor_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Mentores que users PIDIERON crear (Evaluador detectó gaps) o que pidieron
    manualmente. Status='pending' = todavía no se creó ni se rechazó.
    Diferente de /mentors/pending — eso es para mentores YA CREADOS pero
    sin curar.
    """
    _require_admin(current_user)
    rows = db.execute(
        select(
            MentorRequest.id,
            MentorRequest.user_id,
            User.email,
            User.nombre.label("user_nombre"),
            MentorRequest.source,
            MentorRequest.proposed_name,
            MentorRequest.proposed_canon,
            MentorRequest.why,
            MentorRequest.status,
            MentorRequest.created_at,
        )
        .join(User, User.id == MentorRequest.user_id)
        .order_by(MentorRequest.created_at.desc())
    ).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_email": r.email,
            "user_nombre": r.user_nombre,
            "source": r.source,
            "proposed_name": r.proposed_name,
            "proposed_canon": r.proposed_canon,
            "why": r.why,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.patch("/mentor-requests/{request_id}/reject")
def reject_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    req = db.get(MentorRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request no existe.")
    req.status = "rejected"
    db.commit()
    return {"status": "rejected", "id": req.id}


@router.patch("/mentors/{mentor_id}/reject", response_model=MentorResponse)
def reject_mentor(
    mentor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rechaza el mentor: pasa a status='archived'."""
    _require_admin(current_user)
    repo = MentorRepository(db)
    m = repo.get_by_id(mentor_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mentor no existe.")
    updated = repo.update_status_visibility(m, status="archived")
    return MentorResponse.model_validate(updated)


# ============================================================
# FASE 6 — Panel de curación de mentores
# ============================================================

@router.get("/mentors/curation", response_model=list[MentorCurationStatus])
def list_curation_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lista todos los mentores globales con su estado de curación.

    Para el panel admin: ver quién pasó por Promptifex SDD vs cuáles están
    todavía en initial_seed.
    """
    _require_admin(current_user)
    mentors = db.execute(
        select(Mentor)
        .where(Mentor.visibility.in_(["global", "special"]))
        .order_by(Mentor.curated_at.desc().nullslast(), Mentor.slug)
    ).scalars().all()

    result = []
    for m in mentors:
        result.append(MentorCurationStatus(
            id=m.id,
            slug=m.slug,
            nombre=m.nombre,
            version=m.version,
            curator=m.curator,
            curated_at=m.curated_at,
            eval_suite_topic_key=m.eval_suite_topic_key,
            system_prompt_bytes=len(m.system_prompt or ""),
            visibility=m.visibility,
            status=m.status,
        ))
    return result


@router.post("/mentors/{mentor_id}/curate", response_model=CurationResult)
def curate_mentor(
    mentor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [DEPRECATED 2026-06-07] Single-shot curation — NO USAR.

    Razón: este endpoint hace una sola llamada LLM con tool_use. No produce
    eval suite trazable, no tiene anti-sycophancy independence, no tiene
    §17 Eval Protocol, no pasa por verify gate.

    Método único válido: PMTX cycle real con sub-agentes desde Claude Code.
    Ver `/opt/anoven-shared/PMTX-CYCLE-SOP.md` para el procedimiento.

    Este endpoint devuelve 410 Gone para impedir uso accidental.
    """
    _require_admin(current_user)
    raise HTTPException(
        status_code=410,
        detail=(
            "Single-shot curation está DEPRECATED desde 2026-06-07. "
            "Usá PMTX cycle real desde Claude Code. "
            "Ver /opt/anoven-shared/PMTX-CYCLE-SOP.md"
        ),
    )

    # ===== CÓDIGO ABAJO PRESERVADO POR HISTORIA — NO SE EJECUTA =====

    repo = MentorRepository(db)
    m = repo.get_by_id(mentor_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mentor no existe.")

    old_version = m.version
    old_system_prompt = m.system_prompt
    old_bytes = len(old_system_prompt or "")

    # Llamar a Promptifex (puede tardar 30-60 seg)
    from app.services.promptifex import recurate_mentor as _recurate
    try:
        result = _recurate(
            current_system_prompt=old_system_prompt,
            mentor_slug=m.slug,
            mentor_nombre=m.nombre,
            current_canon=m.canon or "",
            current_filosofia=m.filosofia or "",
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Promptifex falló: {e}",
        )

    new_version = old_version + 1
    new_system_prompt = result["new_system_prompt"]
    new_bytes = len(new_system_prompt)
    eval_suite_topic_key = f"anoven-{m.slug.replace('anoven-', '')}/eval-suite/v{new_version}"

    # Guardar eval suite en engram via HTTP API local
    try:
        import json as _json
        import urllib.request as _ur
        suite_content = _json.dumps({
            "mentor_slug": m.slug,
            "version": new_version,
            "evals": result["eval_suite"]["evals"],
            "change_summary": result["change_summary"],
            "created_at": datetime.utcnow().isoformat(),
        }, ensure_ascii=False, indent=2)

        save_payload = {
            "project": f"anoven-{m.slug.replace('anoven-', '')}",
            "scope": "project",
            "type": "architecture",
            "title": f"Eval suite v{new_version} — {m.slug}",
            "content": suite_content,
            "topic_key": eval_suite_topic_key,
        }
        req = _ur.Request(
            "http://127.0.0.1:7437/save",
            data=_json.dumps(save_payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=5)
    except Exception:
        # Si engram no responde, seguimos con la curación igual.
        eval_suite_topic_key = eval_suite_topic_key + " (engram unreachable)"

    # Bump version en BD
    m.system_prompt = new_system_prompt
    m.canon = result["new_canon"]
    m.filosofia = result["new_filosofia"]
    m.version = new_version
    m.curator = "promptifex_sdd"
    m.curated_at = datetime.utcnow()
    m.eval_suite_topic_key = eval_suite_topic_key
    db.commit()
    db.refresh(m)

    return CurationResult(
        mentor_id=m.id,
        slug=m.slug,
        old_version=old_version,
        new_version=new_version,
        old_bytes=old_bytes,
        new_bytes=new_bytes,
        compression_ratio=round(new_bytes / max(old_bytes, 1), 3),
        change_summary=result["change_summary"],
        eval_count=len(result["eval_suite"]["evals"]),
        eval_suite_topic_key=eval_suite_topic_key,
    )


# ============================================================
# FASE 1.5 -- Skills CRUD (mentor-tools-system)
# ============================================================

from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional


class SkillCreateRequest(_BaseModel):
    mentor_id: int
    slug: str
    title: str
    content: str
    triggers: _Optional[list[str]] = None
    position: _Optional[int] = None
    enabled: bool = True


class SkillUpdateRequest(_BaseModel):
    title: _Optional[str] = None
    content: _Optional[str] = None
    triggers: _Optional[list[str]] = None
    enabled: _Optional[bool] = None
    position: _Optional[int] = None


def _skill_to_dict(skill, mentor) -> dict:
    return {
        "id": skill.id,
        "mentor_id": skill.mentor_id,
        "mentor_nombre": mentor.nombre,
        "mentor_slug": mentor.slug,
        "slug": skill.slug,
        "title": skill.title,
        "content": skill.content,
        "triggers": skill.triggers,
        "enabled": skill.enabled,
        "position": skill.position,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


def _invalidate_skill_cache(mentor_id: int) -> None:
    """Invalida el cache de SkillLoader. TTL 60s garantiza consistencia eventual."""
    try:
        from app.services.skill_loader import SkillLoader  # noqa: F401
        # _cache es de instancia -- sin DI singleton no podemos acceder cross-request.
        # Para invalidacion inmediata: reiniciar el backend.
        pass
    except Exception:
        pass


@router.get("/skills")
def admin_list_skills(
    mentor_id: _Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lista todas las skills, opcionalmente filtradas por mentor_id."""
    _require_admin(current_user)
    from app.repositories.mentor_skill_repository import MentorSkillRepository

    repo = MentorSkillRepository(db)
    skills = repo.list_all_for_mentor(mentor_id) if mentor_id is not None else repo.list_all()

    mentor_ids = list({s.mentor_id for s in skills})
    mentors_by_id: dict[int, Any] = {}
    if mentor_ids:
        rows = db.execute(select(Mentor).where(Mentor.id.in_(mentor_ids))).scalars().all()
        mentors_by_id = {m.id: m for m in rows}

    return [
        _skill_to_dict(s, mentors_by_id[s.mentor_id])
        for s in skills
        if s.mentor_id in mentors_by_id
    ]


@router.get("/skills/{skill_id}")
def admin_get_skill(
    skill_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Detalle de una skill por ID."""
    _require_admin(current_user)
    from app.repositories.mentor_skill_repository import MentorSkillRepository

    repo = MentorSkillRepository(db)
    skill = repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")
    mentor = db.get(Mentor, skill.mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor asociado no existe.")
    return _skill_to_dict(skill, mentor)


@router.post("/skills", status_code=201)
def admin_create_skill(
    body: SkillCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Crea una skill nueva. slug debe ser unico dentro del mentor.
    position default = max_position + 1. enabled default = true.
    """
    _require_admin(current_user)
    from app.repositories.mentor_skill_repository import MentorSkillRepository
    from sqlalchemy.exc import IntegrityError

    mentor = db.get(Mentor, body.mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor no existe.")
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="El titulo no puede estar vacio.")
    if not body.content.strip():
        raise HTTPException(status_code=422, detail="El contenido no puede estar vacio.")
    if not body.slug.strip():
        raise HTTPException(status_code=422, detail="El slug no puede estar vacio.")

    repo = MentorSkillRepository(db)
    try:
        skill = repo.create(
            mentor_id=body.mentor_id,
            slug=body.slug.strip(),
            title=body.title.strip(),
            content=body.content,
            triggers=body.triggers,
            position=body.position,
            enabled=body.enabled,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"Ya existe una skill con slug '{body.slug}' para este mentor.",
        )
    return _skill_to_dict(skill, mentor)


@router.put("/skills/{skill_id}")
def admin_update_skill(
    skill_id: int,
    body: SkillUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Actualiza campos de una skill (full o partial -- todos los campos son opcionales)."""
    _require_admin(current_user)
    from app.repositories.mentor_skill_repository import MentorSkillRepository

    repo = MentorSkillRepository(db)
    skill = repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")

    update_fields = body.model_dump(exclude_none=True)
    if "title" in update_fields and not update_fields["title"].strip():
        raise HTTPException(status_code=422, detail="El titulo no puede estar vacio.")
    if "content" in update_fields and not update_fields["content"].strip():
        raise HTTPException(status_code=422, detail="El contenido no puede estar vacio.")

    mentor_id = skill.mentor_id
    updated = repo.update(skill_id, **update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")
    _invalidate_skill_cache(mentor_id)
    mentor = db.get(Mentor, mentor_id)
    return _skill_to_dict(updated, mentor)


@router.patch("/skills/{skill_id}")
def admin_patch_skill(
    skill_id: int,
    body: SkillUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Actualiza campos parciales de una skill (enabled toggle, position move, etc.)."""
    _require_admin(current_user)
    from app.repositories.mentor_skill_repository import MentorSkillRepository

    repo = MentorSkillRepository(db)
    skill = repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")

    update_fields = body.model_dump(exclude_none=True)
    mentor_id = skill.mentor_id
    updated = repo.update(skill_id, **update_fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")
    _invalidate_skill_cache(mentor_id)
    mentor = db.get(Mentor, mentor_id)
    return _skill_to_dict(updated, mentor)


@router.delete("/skills/{skill_id}", status_code=204)
def admin_delete_skill(
    skill_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Elimina una skill permanentemente (hard delete). Muestra confirmacion en UI."""
    _require_admin(current_user)
    from app.repositories.mentor_skill_repository import MentorSkillRepository

    repo = MentorSkillRepository(db)
    skill = repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")
    mentor_id = skill.mentor_id
    deleted = repo.delete(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill no encontrada.")
    _invalidate_skill_cache(mentor_id)
    return None


@router.get("/mentors-list")
def admin_mentors_list(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Lista simplificada de mentores (id, slug, nombre) para el selector
    del formulario de skills. Incluye activos y pending_review.
    """
    _require_admin(current_user)
    mentors = db.execute(
        select(Mentor.id, Mentor.slug, Mentor.nombre)
        .where(Mentor.status.in_(["active", "pending_review"]))
        .order_by(Mentor.nombre)
    ).all()
    return [{"id": m.id, "slug": m.slug, "nombre": m.nombre} for m in mentors]


# ============================================================
# SKILLS — Cache invalidation (skills-platform-with-telemetry)
# ============================================================

@router.post("/skills/cache/invalidate", status_code=204)
def invalidate_skills_cache(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Limpia el cache de SkillLoader para todos los mentores.
    Llamar tras mass ingest o edicion masiva de skills para forzar
    recarga desde BD en el proximo request de cada mentor.
    Returns 204 No Content.
    """
    _require_admin(current_user)
    from app.services.skill_loader import SkillLoader
    from app.repositories.mentor_skill_repository import MentorSkillRepository

    loader = SkillLoader(repo=MentorSkillRepository(db))
    loader.clear_cache()
    return None


# ============================================================
# MODEL ASSIGNMENT — sdd/per-mentor-model-assignment-v1
# Observability + admin management of the per-user/per-mentor model chain.
# ============================================================

from app.schemas.effective_model import EffectiveModelResponse
from app.services.model_resolver import ModelResolver, is_valid_model, MODEL_WHITELIST


@router.get("/effective-model", response_model=EffectiveModelResponse)
def get_effective_model(
    user_id: int,
    mentor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EffectiveModelResponse:
    """
    Observability endpoint: returns the effective Claude model for a
    (user_id, mentor_id) pair AND the full resolution chain (all 3 layers,
    including the layers that did NOT win).

    Why full chain: humans diagnosing "why did this user get Haiku?" need to
    see EVERY configured value, not just the winner. We got bitten 3 times
    today by multi-layer config (env vs settings.json vs FastAPI config)
    silently overriding each other. Full visibility = no silent failures.

    Canon: Humble & Farley (Continuous Delivery, 2010) — observability is
    non-negotiable. SycEval 2025 — show receipts, don't trust claims.

    Auth: admin-only.
    """
    _require_admin(current_user)

    from app.config import settings as _s
    resolver = ModelResolver(db_session=db, default_model=_s.default_model)
    return resolver.resolve_with_chain(user_id=user_id, mentor_id=mentor_id)


@router.get("/model-whitelist")
def get_model_whitelist(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Returns the list of valid Claude model IDs accepted by the resolver
    + DB CHECK constraints. Useful for admin UIs to populate dropdowns."""
    _require_admin(current_user)
    return {"models": sorted(MODEL_WHITELIST)}


@router.put("/mentor/{slug}/model", status_code=200)
def set_mentor_model(
    slug: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Set the per-mentor default model.

    Body: {"model": "claude-opus-4-7"} or {"model": null} to clear.

    NULL clears the per-mentor default → falls through to system default
    unless a user override exists.
    """
    _require_admin(current_user)

    model_value = payload.get("model")
    if model_value is not None and not is_valid_model(model_value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model_value}' not in whitelist. Valid: {sorted(MODEL_WHITELIST)}",
        )

    mentor = db.execute(
        select(Mentor).where(Mentor.slug == slug)
    ).scalar_one_or_none()
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mentor slug '{slug}' not found",
        )

    mentor.model = model_value
    db.commit()
    db.refresh(mentor)

    return {
        "slug": slug,
        "mentor_id": mentor.id,
        "model": mentor.model,
        "message": f"Mentor '{slug}' model set to {model_value!r}",
    }


@router.put("/user/{email}/model-override", status_code=200)
def set_user_model_override(
    email: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Set the per-user model override.

    Body: {"model_override": "claude-opus-4-7"} or {"model_override": null} to clear.

    A user override WINS over the mentor default, so this is the highest-priority
    per-user lever in the resolution chain.
    """
    _require_admin(current_user)

    model_value = payload.get("model_override")
    if model_value is not None and not is_valid_model(model_value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model '{model_value}' not in whitelist. Valid: {sorted(MODEL_WHITELIST)}",
        )

    target = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{email}' not found",
        )

    target.model_override = model_value
    db.commit()
    db.refresh(target)

    return {
        "email": email,
        "user_id": target.id,
        "model_override": target.model_override,
        "message": f"User '{email}' model_override set to {model_value!r}",
    }
