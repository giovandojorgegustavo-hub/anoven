"""
Endpoints CRUD de rules.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.rule import RuleCreate, RuleResponse, RuleToggleActive
from app.services.rule_service import (
    InvalidScope,
    RuleNotFound,
    RuleService,
)


router = APIRouter(prefix="/rules", tags=["rules"])


def _to_response(rule) -> RuleResponse:
    return RuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        project_id=rule.project_id,
        use_case_id=rule.use_case_id,
        content=rule.content,
        active=rule.active,
        scope=rule.scope,
        created_at=rule.created_at,
    )


@router.get("", response_model=list[RuleResponse])
def list_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Todas las reglas del user, global primero."""
    service = RuleService(db)
    return [_to_response(r) for r in service.list_for_user(current_user.id)]


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: RuleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RuleService(db)
    try:
        rule = service.create_for_user(
            user_id=current_user.id,
            content=payload.content,
            project_id=payload.project_id,
            use_case_id=payload.use_case_id,
        )
    except InvalidScope as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _to_response(rule)


@router.patch("/{rule_id}", response_model=RuleResponse)
def toggle_active(
    rule_id: int,
    payload: RuleToggleActive,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RuleService(db)
    try:
        rule = service.toggle_active(rule_id, current_user.id, payload.active)
    except RuleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _to_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RuleService(db)
    try:
        service.delete_for_user(rule_id, current_user.id)
    except RuleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return None
