"""
context_builders — estrategias de construcción de contexto (Strategy Pattern).

Exports:
  ContextBuilder          — Port (Protocol)
  IndividualContextBuilder — adapter para proyectos de un solo miembro
  SharedProjectContextBuilder — adapter con TF-IDF author summary
  get_context_builder     — factory que selecciona la estrategia correcta

Alistair Cockburn — Hexagonal Architecture, 2005:
  ContextBuilderFactory.for_project() elige el adapter sin que el caller
  (conversation_service) sepa cuál estrategia se está usando.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.context_builders.base import ContextBuilder
from app.services.context_builders.individual import IndividualContextBuilder
from app.services.context_builders.shared_project import SharedProjectContextBuilder


def get_context_builder(
    db: Session,
    conversation_id: int,
    project_id: int | None = None,
) -> ContextBuilder:
    """
    Factory: selecciona la estrategia de contexto según el proyecto.

    Lógica de selección:
      - Si project_id es None → IndividualContextBuilder (fallback seguro)
      - Si el proyecto tiene más de 1 miembro → SharedProjectContextBuilder
      - Caso contrario → IndividualContextBuilder

    La verificación de member count usa ProjectMemberRepository directamente
    para no crear dependencia circular con los servicios.
    """
    if project_id is None:
        return IndividualContextBuilder(db=db, conversation_id=conversation_id)

    try:
        from app.repositories.project_member_repo import ProjectMemberRepository
        count = ProjectMemberRepository(db).count_for_project(project_id)
        if count > 1:
            return SharedProjectContextBuilder(db=db)
    except Exception:
        # Fallback defensivo: si falla la consulta, usar comportamiento individual
        pass

    return IndividualContextBuilder(db=db, conversation_id=conversation_id)


__all__ = [
    "ContextBuilder",
    "IndividualContextBuilder",
    "SharedProjectContextBuilder",
    "get_context_builder",
]
