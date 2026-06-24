"""
Schemas Pydantic para vistas de proyectos compartidos.

ProjectShareView es la vista que recibe el frontend cuando pide la lista
de proyectos del user (owned + member-of). Incluye el rol del user en cada
proyecto y conteos de members y mentores para la UI.

Copy en tuteo limeño culto. Audit gate:
  rg "vos|vení|tenés|querés|ponés|hacés|sos\b" → 0 hits esperados.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ProjectShareView(BaseModel):
    """
    Vista consolidada de un proyecto para el user.

    - role: qué rol tiene el user en este proyecto.
    - members_count: total de members (incluye al owner).
    - mentors_count: mentores asignados al proyecto.
    """
    id: int
    slug: str
    name: str
    description: str | None
    role: Literal["owner", "member"]
    members_count: int
    mentors_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
