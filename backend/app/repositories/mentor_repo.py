"""
Repository de Mentor y UserMentor — encapsula el acceso SQL.
"""

import re

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.mentor import Mentor, UserMentor


class MentorRepository:
    """Acceso a la tabla mentors."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, mentor_id: int) -> Mentor | None:
        return self.db.get(Mentor, mentor_id)

    def get_by_slug(self, slug: str) -> Mentor | None:
        stmt = select(Mentor).where(Mentor.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_globals_active(self) -> list[Mentor]:
        """Mentores marcados como 'global' y 'active' — los 5 default."""
        stmt = select(Mentor).where(
            Mentor.visibility == "global",
            Mentor.status == "active",
        )
        return list(self.db.execute(stmt).scalars())

    def list_all(self) -> list[Mentor]:
        """Todos los mentores (uso de admin)."""
        return list(self.db.execute(select(Mentor)).scalars())

    def list_by_status(self, status: str) -> list[Mentor]:
        stmt = select(Mentor).where(Mentor.status == status)
        return list(self.db.execute(stmt).scalars())

    def search_similar(self, canon: str, filosofia: str, limit: int = 5) -> list[Mentor]:
        """
        Búsqueda básica de similitud por keyword overlap en canon + filosofia
        contra mentores active+global. Para 5.4 (dedup) — versión simple sin
        embeddings.
        """
        # Tokens distintivos del input
        text = f"{canon} {filosofia}".lower()
        tokens = re.findall(r"\w+", text)
        meaningful = [t for t in tokens if len(t) >= 4]
        if not meaningful:
            return []

        # Score cada mentor activo+global por overlap de tokens
        stmt = select(Mentor).where(
            Mentor.status == "active",
            Mentor.visibility == "global",
        )
        mentors = list(self.db.execute(stmt).scalars())
        scored = []
        for m in mentors:
            haystack = (m.canon + " " + m.filosofia).lower()
            score = sum(1 for t in meaningful if t in haystack)
            if score >= 2:  # umbral mínimo
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def update_status_visibility(
        self,
        mentor: Mentor,
        status: str | None = None,
        visibility: str | None = None,
    ) -> Mentor:
        if status is not None:
            mentor.status = status
        if visibility is not None:
            mentor.visibility = visibility
        self.db.commit()
        self.db.refresh(mentor)
        return mentor

    def create(self, **kwargs) -> Mentor:
        """Crea un mentor nuevo."""
        mentor = Mentor(**kwargs)
        self.db.add(mentor)
        self.db.commit()
        self.db.refresh(mentor)
        return mentor


class UserMentorRepository:
    """Acceso a la tabla user_mentors (asignaciones)."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: int) -> list[UserMentor]:
        """Devuelve TODAS las asignaciones activas de un user."""
        stmt = select(UserMentor).where(
            UserMentor.user_id == user_id,
            UserMentor.active == True,
        )
        return list(self.db.execute(stmt).scalars())

    def is_assigned(self, user_id: int, mentor_id: int) -> bool:
        stmt = select(UserMentor).where(
            UserMentor.user_id == user_id,
            UserMentor.mentor_id == mentor_id,
            UserMentor.active == True,
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def assign(
        self,
        user_id: int,
        mentor_id: int,
        source: str = "default",
        match_reason: str | None = None,
    ) -> UserMentor:
        """Asigna un mentor a un user. `match_reason` se usa cuando source='matched'."""
        # Si ya existe, no duplicar (pero sí actualizar la reason si vino una nueva)
        if self.is_assigned(user_id, mentor_id):
            existing = self.db.execute(
                select(UserMentor).where(
                    UserMentor.user_id == user_id,
                    UserMentor.mentor_id == mentor_id,
                )
            ).scalar_one()
            if match_reason and existing.match_reason != match_reason:
                existing.match_reason = match_reason
                self.db.commit()
            return existing

        um = UserMentor(
            user_id=user_id,
            mentor_id=mentor_id,
            source=source,
            match_reason=match_reason,
        )
        self.db.add(um)
        self.db.commit()
        self.db.refresh(um)
        return um

    def deactivate_all_for_user(self, user_id: int) -> int:
        """
        Marca como inactivas TODAS las asignaciones del user.
        Devuelve cuántas se desactivaron. NO borra registros — queda historia.
        """
        stmt = select(UserMentor).where(
            UserMentor.user_id == user_id,
            UserMentor.active == True,
        )
        ums = list(self.db.execute(stmt).scalars())
        for um in ums:
            um.active = False
        if ums:
            self.db.commit()
        return len(ums)

    def deactivate_by_source(self, user_id: int, source: str) -> int:
        """
        FASE 7: marca como inactivas las asignaciones del user de un source
        específico (ej: 'matched' para reemplazo post-entrevista, sin tocar
        'default' ni 'created_by_self').
        """
        stmt = select(UserMentor).where(
            UserMentor.user_id == user_id,
            UserMentor.source == source,
            UserMentor.active == True,
        )
        ums = list(self.db.execute(stmt).scalars())
        for um in ums:
            um.active = False
        if ums:
            self.db.commit()
        return len(ums)
