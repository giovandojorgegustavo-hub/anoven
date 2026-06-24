"""
Endpoints de autenticación: local (email/password) + Google OAuth.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.google_oauth import oauth
from app.database import get_db
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse
from app.services.auth_service import (
    AuthService,
    EmailAlreadyExists,
    InvalidCredentials,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Registra un user nuevo y devuelve un JWT para usarlo inmediatamente."""
    service = AuthService(db)
    try:
        user, token = service.register(
            email=payload.email,
            password=payload.password,
            nombre=payload.nombre,
        )
    except EmailAlreadyExists as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


# ============================================================
# Google OAuth
# ============================================================
#
# Flujo:
#   1) Browser pega GET /auth/google/login
#      → backend responde 302 redirect a https://accounts.google.com/...
#   2) User autoriza en Google
#      → Google redirige a GET /auth/google/callback?code=XXX&state=YYY
#   3) Backend canjea `code` por `access_token` + `id_token` con Google
#      → extrae email, nombre, google_id
#      → crea o encuentra al user en la BD
#      → genera nuestro JWT
#      → redirige al frontend con el JWT en la URL
#   4) Frontend lee el JWT del URL y lo guarda (localStorage / cookie).
# ============================================================


@router.get("/google/login")
async def google_login(request: Request):
    """Inicia el flujo OAuth: redirige al consent screen de Google."""
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """
    Google nos manda acá después del consent.
    Cambiamos el `code` por el `id_token` y resolvemos el user.
    """
    try:
        token_data = await oauth.google.authorize_access_token(request)
    except Exception as e:
        # Authlib lanza error si el state no coincide o si Google rechazó el code
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth callback inválido: {e}",
        )

    userinfo = token_data.get("userinfo")
    if userinfo is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google no devolvió userinfo.",
        )

    google_id = userinfo["sub"]
    email = userinfo["email"]
    nombre = userinfo.get("name") or email.split("@")[0]

    service = AuthService(db)
    user, jwt_token = service.login_or_register_google(
        google_id=google_id,
        email=email,
        nombre=nombre,
    )

    # Redirigimos al frontend con el JWT en el query string.
    # NOTA seguridad: en producción esto se hace mejor con HttpOnly cookie.
    # Para MVP/dev en localhost va bien.
    frontend_redirect = f"{settings.frontend_url}/auth/callback?token={jwt_token}"
    return RedirectResponse(url=frontend_redirect)


# ============================================================


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Login con email + password. Devuelve un JWT."""
    service = AuthService(db)
    try:
        user, token = service.login(
            email=payload.email,
            password=payload.password,
        )
    except InvalidCredentials as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )
