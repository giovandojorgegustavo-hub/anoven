"""
Schemas Pydantic para Mentor.
"""

from datetime import datetime
from pydantic import BaseModel, Field


# === Lo que el cliente VE de un mentor ===
class MentorResponse(BaseModel):
    id: int
    slug: str
    nombre: str
    canon: str
    filosofia: str
    visibility: str
    status: str
    created_at: datetime
    # FASE 6 — versionado + curación (opcional para retrocompatibilidad)
    version: int = 1
    curator: str | None = None
    curated_at: datetime | None = None
    eval_suite_topic_key: str | None = None
    # call-mentor-multi-agent (2026-06-08) — cross-mentor invocation config
    allowed_callees: list[str] = []         # which mentors this mentor can call
    max_callees_per_turn: int | None = None  # None = system default (2)

    model_config = {"from_attributes": True}


# === Vista admin: mentor con info de curación + tamaño ===
class MentorCurationStatus(BaseModel):
    """Para el panel admin /admin/mentors/curation."""
    id: int
    slug: str
    nombre: str
    version: int
    curator: str | None  # "initial_seed" | "promptifex_sdd" | "manual_admin"
    curated_at: datetime | None
    eval_suite_topic_key: str | None
    system_prompt_bytes: int  # tamaño actual del prompt en bytes
    visibility: str
    status: str


# === Resultado de una pasada de curación ===
class CurationResult(BaseModel):
    """Lo que devuelve POST /admin/mentors/{id}/curate."""
    mentor_id: int
    slug: str
    old_version: int
    new_version: int
    old_bytes: int
    new_bytes: int
    compression_ratio: float  # new_bytes / old_bytes
    change_summary: str
    eval_count: int
    eval_suite_topic_key: str


# === Lo que el cliente VE de "MIS mentores" (con info de asignación) ===
class MyMentorResponse(BaseModel):
    """Un mentor + cómo me fue asignado."""
    mentor: MentorResponse
    source: str          # "default" | "matched" | "created_by_self" | "assigned_by_admin"
    match_reason: str | None = None  # solo cuando source='matched'
    assigned_at: datetime


# === Catálogo (self-add) — mentores que el user PUEDE agregarse ===
class MentorCatalogItem(BaseModel):
    """Item del catálogo de mentores que el user puede agregarse.
    Solo expone los campos visibles en la UI de selección (sin system_prompt,
    sin curator metadata)."""
    id: int
    slug: str
    nombre: str
    canon: str
    filosofia: str

    model_config = {"from_attributes": True}


# === Add mentor (self) — payload para POST /users/me/mentors ===
class UserMentorAddRequest(BaseModel):
    mentor_id: int


# === UserMentor response — lo que devuelve POST /users/me/mentors ===
class UserMentorResponse(BaseModel):
    id: int
    user_id: int
    mentor_id: int
    source: str
    active: bool
    match_reason: str | None = None
    assigned_at: datetime

    model_config = {"from_attributes": True}


# === Crear mentor (admin o user vía Creador-Promptifex en sesión futura) ===
class MentorCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_-]+$")
    nombre: str = Field(min_length=1, max_length=100)
    canon: str = Field(min_length=1, max_length=500)
    filosofia: str = Field(min_length=1, max_length=500)
    system_prompt: str = Field(min_length=10)
    visibility: str = Field(default="private", pattern=r"^(private|shareable|global)$")

# === Actualizar mentor (admin) — todos los campos son opcionales ===
class MentorUpdate(BaseModel):
    """Payload para PATCH /admin/mentors/{{id}}. Todos los campos son opcionales."""
    nombre: str | None = None
    canon: str | None = None
    filosofia: str | None = None
    system_prompt: str | None = None
    visibility: str | None = None
    status: str | None = None
    # call-mentor-multi-agent (2026-06-08) — cross-mentor invocation config
    allowed_callees: list[str] | None = None
    max_callees_per_turn: int | None = None  # None = use system default (no override)
