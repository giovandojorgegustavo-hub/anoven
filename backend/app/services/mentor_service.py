"""
MentorService — lógica de negocio sobre mentores.
"""

from sqlalchemy.orm import Session

from app.models.mentor import Mentor, UserMentor
from app.repositories.mentor_repo import MentorRepository, UserMentorRepository


# Los 4 mentores que TODO user nuevo recibe por default — son la base universal.
# Cualquier user, sin importar perfil ni gustos, arranca con estos.
CORE_FOUR_SLUGS = [
    "anoven-admin",         # Administración / estrategia
    "anoven-marketing",     # Marketing
    "anoven-design",        # Diseño
    "anoven-secondbrain",   # PKM / sistemas de pensamiento
]

# Tope de mentores matched (extra a los core four) que se asignan por gustos.
MAX_MATCHED_MENTORS = 2


class MentorService:
    def __init__(self, db: Session):
        self.db = db
        self.mentor_repo = MentorRepository(db)
        self.user_mentor_repo = UserMentorRepository(db)

    def assign_defaults_to_user(self, user_id: int) -> list[UserMentor]:
        """
        Asigna los 4 mentores CORE al user. Se llama al registrarse.

        Antes asignaba TODOS los globales (16). Cambio FASE 7: solo los 4
        fijos universales (admin / marketing / design / secondbrain). Los
        otros 2 (max) se asignan post-entrevista vía MentorMatcher según
        gustos del user.
        """
        assignments = []
        for slug in CORE_FOUR_SLUGS:
            mentor = self.mentor_repo.get_by_slug(slug)
            if mentor is None:
                # Si falta uno del core, lo logueamos pero seguimos.
                # No queremos romper el registro por un mentor faltante.
                continue
            if mentor.status != "active" or mentor.visibility != "global":
                continue
            um = self.user_mentor_repo.assign(
                user_id=user_id,
                mentor_id=mentor.id,
                source="default",
            )
            assignments.append(um)
        return assignments

    def list_user_mentors_with_data(self, user_id: int) -> list[dict]:
        """Devuelve mentores del user con info combinada (mentor + asignacion).

        Reglas de visibilidad:
          - Mentores ajenos (source != created_by_self): solo si status=active.
          - Mentores propios (created_by_self): visibles tambien en pending_review
            para que el creador pueda usarlos antes de la curation del admin.
            Mentores draft/archived siguen ocultos.
        """
        ums = self.user_mentor_repo.list_for_user(user_id)
        result = []
        for um in ums:
            mentor = self.mentor_repo.get_by_id(um.mentor_id)
            if mentor is None:
                continue
            is_own_creation = um.source == "created_by_self"
            if is_own_creation:
                visible = mentor.status in ("active", "pending_review")
            else:
                visible = mentor.status == "active"
            if visible:
                result.append({
                    "mentor": mentor,
                    "source": um.source,
                    "match_reason": um.match_reason,
                    "assigned_at": um.assigned_at,
                })
        return result

    def list_global_catalog(self) -> list[dict]:
        """
        Catálogo público para el MentorMatcher. Devuelve solo los metadatos
        (id, slug, nombre, canon, filosofia) — NO el system_prompt, que es
        enorme y el matcher decide con los metadatos.
        """
        mentors = self.mentor_repo.list_globals_active()
        return [
            {
                "id": m.id,
                "slug": m.slug,
                "nombre": m.nombre,
                "canon": m.canon,
                "filosofia": m.filosofia,
            }
            for m in mentors
        ]

    def find_similar(self, canon: str, filosofia: str) -> list[Mentor]:
        """Para 5.4 dedup: busca mentores del catálogo similares al draft."""
        return self.mentor_repo.search_similar(canon, filosofia)

    def create_custom_mentor(
        self,
        user_id: int,
        slug: str,
        nombre: str,
        canon: str,
        filosofia: str,
        system_prompt: str,
    ) -> Mentor:
        """
        Crea un mentor custom del user via Promptifex.

        Estado inicial: visibility='private', status='pending_review',
        created_by_user_id=user_id. Auto-asignado al user en user_mentors
        con source='created_by_self'.

        El admin (Jorge) puede aprobarlo a global en 5.5 (curation queue).

        Si el slug ya existe (improbable porque incluye user_id), lo
        desambiguamos sufijando.
        """
        # Hacemos slug único globalmente (puede colisionar con globals)
        candidate_slug = slug
        i = 2
        while self.mentor_repo.get_by_slug(candidate_slug) is not None:
            candidate_slug = f"{slug}-u{user_id}-{i}"
            i += 1
            if i > 20:
                # Defensa última: usar timestamp
                import time
                candidate_slug = f"{slug}-{int(time.time())}"
                break

        mentor = self.mentor_repo.create(
            slug=candidate_slug,
            nombre=nombre,
            canon=canon,
            filosofia=filosofia,
            system_prompt=system_prompt,
            created_by_user_id=user_id,
            visibility="private",
            status="pending_review",
        )

        # Auto-asignar al user
        self.user_mentor_repo.assign(
            user_id=user_id,
            mentor_id=mentor.id,
            source="created_by_self",
        )
        return mentor

    def replace_with_matched(
        self,
        user_id: int,
        matches: list[dict],
    ) -> list[UserMentor]:
        """
        FASE 7: reemplaza solo las asignaciones source='matched' del user
        con las del MentorMatcher, manteniendo intactos:
          - source='default' (los 4 CORE_FOUR_SLUGS)
          - source='created_by_self' (mentores custom del user via Promptifex)

        `matches` es list de dicts: [{slug, reason}, ...] (puede traer 5+)

        1. Garantiza que los 4 CORE estén asignados (asigna los que falten).
        2. Quita asignaciones previas con source='matched'.
        3. Asigna hasta MAX_MATCHED_MENTORS (2) nuevos matches con source='matched'.
        4. NO asigna como matched los slugs que ya están en CORE_FOUR_SLUGS
           (evita duplicación).

        Devuelve TODAS las asignaciones activas del user post-cambio
        (default + matched + created_by_self), no solo las matched nuevas.
        """
        # 1. Asegurar CORE four — si falta alguno, lo agregamos
        existing_slugs = {
            self.mentor_repo.get_by_id(um.mentor_id).slug
            for um in self.user_mentor_repo.list_for_user(user_id)
            if self.mentor_repo.get_by_id(um.mentor_id) is not None
        }
        for core_slug in CORE_FOUR_SLUGS:
            if core_slug in existing_slugs:
                continue
            mentor = self.mentor_repo.get_by_slug(core_slug)
            if mentor and mentor.status == "active" and mentor.visibility == "global":
                self.user_mentor_repo.assign(
                    user_id=user_id,
                    mentor_id=mentor.id,
                    source="default",
                )

        # 2. Quitar SOLO los source='matched' previos (no toca default/created_by_self)
        self.user_mentor_repo.deactivate_by_source(user_id, source="matched")

        # 3. Asignar hasta MAX_MATCHED_MENTORS nuevos matches
        seen_ids: set[int] = set()
        new_matched_count = 0
        for match in matches:
            if new_matched_count >= MAX_MATCHED_MENTORS:
                break
            slug = match.get("slug")
            reason = match.get("reason", "")
            if not slug:
                continue
            # Skip si ya está como core four (evita doble asignación)
            if slug in CORE_FOUR_SLUGS:
                continue
            mentor = self.mentor_repo.get_by_slug(slug)
            if mentor is None or mentor.id in seen_ids:
                continue
            if mentor.status != "active":
                continue
            self.user_mentor_repo.assign(
                user_id=user_id,
                mentor_id=mentor.id,
                source="matched",
                match_reason=reason,
            )
            seen_ids.add(mentor.id)
            new_matched_count += 1

        # 4. Devolvemos TODO lo activo del user (no solo los matched nuevos)
        return self.user_mentor_repo.list_for_user(user_id)
