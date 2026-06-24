"""
Punto de entrada de la app Anoven.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import engine, Base

# Importamos los modelos para que SQLAlchemy los registre
from app.models import user, mentor, interview_attempt, interview_message, conversation, message, project, rule, cost_event, attachment, mentor_request  # noqa: F401
from app.models import support_ticket, ticket_attachment  # noqa: F401
from app.models import project_member, project_invitation, project_mentor  # noqa: F401

# Importamos los routers
from app.routes import auth, users, mentors, interviews, conversations, projects, rules, admin, attachments
from app.routes import support_tickets as support_tickets_router
from app.routes import admin_tickets as admin_tickets_router
from app.routes import project_members as project_members_router
from app.routes import project_invitations as project_invitations_router
from app.routes import project_mentors as project_mentors_router


app = FastAPI(
    title=settings.app_name,
    description="Plataforma de mentores AI personalizados",
    version="0.1.0",
)

# SessionMiddleware — necesario para el flujo OAuth de Authlib.
# Authlib guarda el `state` y el PKCE verifier en la sesión durante el
# round-trip browser → Google → callback. Usa una cookie firmada con jwt_secret.
app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Crea las tablas si no existen."""
    Base.metadata.create_all(bind=engine)


# === Routers ===
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(mentors.router)
app.include_router(interviews.router)
app.include_router(conversations.router)
app.include_router(projects.router)
app.include_router(rules.router)
app.include_router(admin.router)
app.include_router(attachments.router)
app.include_router(support_tickets_router.router, prefix="/api/tickets", tags=["tickets"])
app.include_router(admin_tickets_router.router, prefix="/api/admin/tickets", tags=["admin-tickets"])
app.include_router(project_members_router.router, tags=["project-members"])
app.include_router(project_invitations_router.router, tags=["project-invitations"])
app.include_router(project_mentors_router.router, tags=["project-mentors"])

# === Storage estático para uploads ===
_STORAGE_ROOT = Path(os.environ.get(
    "ANOVEN_STORAGE_ROOT",
    "/home/anoven/anoven-app/storage/uploads",
))
_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(_STORAGE_ROOT)), name="storage")


# === Endpoints sueltos ===
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": "0.1.0",
    }


@app.get("/")
def root():
    return {"message": "Anoven API. Ver /docs para la documentación."}
