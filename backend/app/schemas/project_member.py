"""
Schemas Pydantic para el dominio project_members.

Copy en tuteo limeño culto. Audit gate:
  rg "vos|vení|tenés|querés|ponés|hacés|sos\b" → 0 hits esperados.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Member read ───────────────────────────────────────────────────────────────

class ProjectMemberRead(BaseModel):
    """Vista de un member del proyecto."""
    id: int
    project_id: int
    user_id: int
    user_email: str
    user_nombre: str
    role: str  # "owner" | "member"
    joined_at: datetime
    invited_by_user_id: Optional[int]

    model_config = {"from_attributes": True}


class MemberListRead(BaseModel):
    """Lista de members del proyecto."""
    members: list[ProjectMemberRead]
    total: int
