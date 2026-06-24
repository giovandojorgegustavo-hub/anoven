"""
BillingResolver — resuelve el owner (pagador) de un proyecto compartido.

En proyectos compartidos el owner paga los tokens de todos los miembros.
Este servicio cachea el resultado en memoria (LRU 256 entradas) porque el
owner nunca cambia en v1 — la invalidación manual existe para v2.

Invariante A1.3 STRICT: NUNCA importar fastapi.

Robert C. Martin — Clean Architecture, 2017:
  billing routing es una razón de cambio distinta de chat orchestration
  y de cost recording → tres servicios separados.

ADR-9: LRU cache manual (dict + FIFO eviction) para evitar la limitación
de @functools.lru_cache con métodos de instancia que no son hashable-safe.
"""

from __future__ import annotations

import os
from typing import Callable

from sqlalchemy.orm import Session


class BillingOwnerNotFoundError(Exception):
    """El proyecto no tiene owner registrado en project_members."""
    def __init__(self, project_id: int):
        self.project_id = project_id
        super().__init__(
            f"No se encontró owner para el proyecto {project_id}."
        )


_DEFAULT_CACHE_SIZE = 256


class BillingResolver:
    """
    Resuelve el owner user_id de un proyecto para routing de costos.

    Uso esperado: instancia singleton por proceso, inyectada via
    FastAPI dependency (get_billing_resolver).

    El parámetro db_factory es un callable que devuelve una Session
    SQLAlchemy fresca (compatible con el contextmanager de FastAPI).
    """

    def __init__(
        self,
        db_factory: Callable[[], Session],
        cache_size: int | None = None,
    ):
        self._db_factory = db_factory
        _size = cache_size
        if _size is None:
            try:
                _size = int(os.environ.get("BILLING_RESOLVER_CACHE_SIZE", _DEFAULT_CACHE_SIZE))
            except (ValueError, TypeError):
                _size = _DEFAULT_CACHE_SIZE
        self._cache_size = max(1, _size)
        # LRU implementado como dict + lista de keys en orden de inserción.
        # dict preserva insertion order en Python 3.7+; FIFO eviction al llegar al límite.
        self._cache: dict[int, int] = {}

    def resolve_billing_owner_id(self, project_id: int) -> int:
        """
        Devuelve el user_id del owner del proyecto.

        Cache hit → O(1), sin DB.
        Cache miss → consulta project_members WHERE role='owner'.
        Raises BillingOwnerNotFoundError si no hay owner registrado.
        """
        if project_id in self._cache:
            return self._cache[project_id]

        # Cache miss: consultar DB
        from app.repositories.project_member_repo import ProjectMemberRepository
        db = self._db_factory()
        try:
            repo = ProjectMemberRepository(db)
            owner = repo.get_owner(project_id)
        finally:
            # Si db_factory devuelve un session que no se auto-cierra, cerrarlo.
            # Si es un contextmanager, el caller lo gestiona — este finally
            # es defensivo para el caso de session directa.
            try:
                db.close()
            except Exception:
                pass

        if owner is None:
            raise BillingOwnerNotFoundError(project_id)

        owner_user_id: int = owner.user_id

        # Guardar en cache con FIFO eviction
        if len(self._cache) >= self._cache_size:
            # Eliminar el más antiguo (primer key del dict)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[project_id] = owner_user_id
        return owner_user_id

    def invalidate(self, project_id: int) -> None:
        """
        Invalida la entrada de cache para un proyecto.

        Pre-construido para v2 (owner transfer). En v1 nunca se llama
        porque el owner no cambia.
        """
        self._cache.pop(project_id, None)

    def cache_size(self) -> int:
        """Cantidad de entradas en cache (para diagnóstico)."""
        return len(self._cache)
