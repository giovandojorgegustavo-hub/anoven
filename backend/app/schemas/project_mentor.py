"""
Schemas Pydantic para el dominio project_mentors.

Copy en tuteo limeño culto. Audit gate:
  rg "vos|vení|tenés|querés|ponés|hacés|sos\b" → 0 hits esperados.
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Input ─────────────────────────────────────────────────────────────────────

class ProjectMentorCreate(BaseModel):
    """Payload para asignar un mentor al proyecto."""
    mentor_id: int = Field(
        ...,
        description="ID del mentor a asignar al proyecto",
    )


# ── Output ────────────────────────────────────────────────────────────────────

class ProjectMentorRead(BaseModel):
    """Vista de un mentor asignado a un proyecto."""
    id: int
    project_id: int
    mentor_id: int
    mentor_slug: str
    mentor_nombre: str
    added_by_user_email: str
    added_at: datetime

    model_config = {"from_attributes": True}
