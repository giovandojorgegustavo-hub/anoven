"""
Schemas Pydantic para el dominio project_invitations.

Copy en tuteo limeño culto. Audit gate:
  rg "vos|vení|tenés|querés|ponés|hacés|sos\b" → 0 hits esperados.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, EmailStr


# ── Input ─────────────────────────────────────────────────────────────────────

class InvitationCreate(BaseModel):
    """
    Payload para invitar a un usuario al proyecto.
    Solo necesitás el email — el backend resuelve el user_id.
    """
    invited_user_email: EmailStr = Field(
        ...,
        description="Email del usuario a invitar (debe tener cuenta en Anoven)",
    )
    days_to_expire: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Días hasta que venza la invitación (1–30, default 7)",
    )


# ── Output ────────────────────────────────────────────────────────────────────

class InvitationRead(BaseModel):
    """Vista de una invitación (pendiente o resuelta)."""
    id: int
    project_id: int
    project_name: str
    invited_user_email: str
    invited_by_user_email: str
    status: str  # "pending" | "accepted" | "rejected" | "expired" | "revoked"
    expires_at: datetime
    created_at: datetime
    responded_at: Optional[datetime]

    model_config = {"from_attributes": True}


class InvitationCountRead(BaseModel):
    """Cantidad de invitaciones pendientes — para el badge del header."""
    count: int
