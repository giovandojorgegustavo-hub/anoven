"""
Dependencies de FastAPI.

`get_current_user` es la "puerta de seguridad" — FastAPI la corre
ANTES de cualquier endpoint que la incluya. Si no hay JWT válido,
rechaza con 401.

Uso:
    @router.get("/me")
    def quien_soy(user: User = Depends(get_current_user)):
        return user

Sesión anoven-shared-projects:
    require_project_member  — verifica que el user sea member del proyecto
    require_project_owner   — verifica que el user sea owner del proyecto
    get_billing_resolver    — singleton dep para BillingResolver
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.core.security import decode_access_token


# HTTPBearer lee el header `Authorization: Bearer <token>` directamente,
# sin formularios raros de OAuth2 password flow.
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Devuelve el User logueado o lanza 401."""

    token = credentials.credentials  # el string del JWT

    # Validar el JWT
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Buscar el user en la BD
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no existe",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Solo deja pasar si el user tiene role='admin'."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acción requiere permisos de admin",
        )
    return current_user


# ── Shared-projects deps ──────────────────────────────────────────────────────

def require_project_member(project_id: int):
    """
    Dependency factory: devuelve un callable compatible con Depends()
    que valida que el user autenticado sea member (o owner) del proyecto.

    Uso:
        @router.get("/{project_id}/members")
        def list_members(
            project_id: int,
            member: ProjectMember = Depends(require_project_member(project_id)),
        ): ...

    Raises 403 si el user no es member.
    Retorna el ProjectMember row (útil para conocer el role en el handler).
    """
    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        from app.repositories.project_member_repo import ProjectMemberRepository
        pm = ProjectMemberRepository(db).get_by_project_user(project_id, current_user.id)
        if pm is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No eres miembro de este proyecto.",
            )
        return pm
    return _dep


def require_project_owner(project_id: int):
    """
    Dependency factory: igual que require_project_member pero exige role='owner'.

    Raises 403 si el user no es owner (incluso si es member).
    """
    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        from app.repositories.project_member_repo import ProjectMemberRepository
        pm = ProjectMemberRepository(db).get_by_project_user(project_id, current_user.id)
        if pm is None or pm.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el owner del proyecto puede hacer esto.",
            )
        return pm
    return _dep


# ── BillingResolver singleton dep ─────────────────────────────────────────────

_billing_resolver_instance = None


def get_billing_resolver():
    """
    FastAPI dep que devuelve la instancia singleton de BillingResolver.

    Singleton por proceso — safe porque BillingResolver tiene su propio
    LRU cache interno y gestiona su propia session factory.

    Reemplaza el pattern inline (SessionLocal instanciado en conversation_service)
    que existía en Batch 3. A partir de Batch 4 todos los callers inyectan esto.
    """
    global _billing_resolver_instance
    if _billing_resolver_instance is None:
        from app.services.billing_resolver import BillingResolver
        from app.database import SessionLocal
        _billing_resolver_instance = BillingResolver(db_factory=SessionLocal)
    return _billing_resolver_instance
