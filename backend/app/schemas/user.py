"""
Schemas Pydantic — definen la forma de los datos que viajan por HTTP.

Schemas vs Models:
  - Models (SQLAlchemy) = forma EN LA BD (columnas).
  - Schemas (Pydantic) = forma EN LA API (JSON).

Son cosas distintas a propósito: el password_hash NUNCA sale por la API,
pero SÍ vive en la BD. Schemas filtran qué se expone.
"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# === Lo que el cliente MANDA al registrarse ===
class UserCreate(BaseModel):
    email: EmailStr   # EmailStr valida formato automáticamente
    password: str = Field(min_length=8, max_length=72)  # bcrypt soporta máx 72 chars
    nombre: str = Field(min_length=1, max_length=100)


# === Lo que el cliente MANDA al loguearse ===
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# === Lo que el servidor DEVUELVE al describir un usuario ===
# IMPORTANTE: NO incluye password ni password_hash.
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    nombre: str
    role: str

    # Estado de onboarding — el frontend lo usa para decidir si te lleva
    # al dashboard o al /onboarding (gate de Fase 2).
    onboarding_state: str
    onboarding_score: int | None
    onboarding_attempts: int

    # Project activo (Fase 4.2) — el frontend lo usa para filtrar conversaciones.
    active_project_id: int | None = None

    # Research opt-in (Fase 7)
    research_opt_in: bool = False

    created_at: datetime

    model_config = {"from_attributes": True}  # permite construir desde un objeto User de SQLAlchemy


# === Token JWT que el servidor devuelve al loguearse o registrarse ===
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
