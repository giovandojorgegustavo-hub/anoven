"""
SkillLoader -- ensamblador del bloque de skills para el system_prompt.

Responsabilidades:
  - Leer skills habilitadas del mentor desde el repositorio.
  - Aplicar cap de tamano total (40,000 chars) y por skill (8,000 chars).
  - Formatear el bloque markdown con separadores.
  - Cache en memoria con TTL de 60 segundos por mentor_id.
  - Invalidar cache cuando admin edita un skill.

Unico punto de verdad para construir skills_block. Nadie mas llama SQL
directamente para skills.

Cache es modulo-nivel (dict compartido entre instancias) para que
invalidate() y clear_cache() funcionen cross-request sin requerir
un singleton de FastAPI explícito.
"""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.mentor import Mentor
    from app.repositories.mentor_skill_repository import MentorSkillRepository

logger = logging.getLogger(__name__)

# Limites del bloque de skills
MAX_TOTAL_CHARS = 40_000
MAX_PER_SKILL_CHARS = 8_000
CACHE_TTL_SECONDS = 60.0

# Sufijo cuando se trunca contenido de un skill individual
TRUNCATE_SUFFIX = "... [truncado]"

# Cache compartido a nivel de modulo: mentor_id -> (expires_at: float, block: str)
# Al ser modulo-nivel, todas las instancias de SkillLoader comparten el mismo dict.
# Esto habilita que clear_cache() y invalidate() tengan efecto real entre requests.
_MODULE_CACHE: dict[int, tuple[float, str]] = {}


class SkillLoader:
    """
    Ensambla el bloque de skills para inyectar en el system_prompt.

    Uso:
        loader = SkillLoader(repo=MentorSkillRepository(db))
        block = loader.build_block_for_mentor(mentor)
        # block es '' si no hay skills habilitadas
    """

    def __init__(self, repo: "MentorSkillRepository"):
        self._repo = repo
        # _cache apunta al dict modulo-nivel para que invalidaciones sean
        # visibles en el mismo proceso uvicorn independientemente de que
        # instancia llame a invalidate() o clear_cache().
        self._cache = _MODULE_CACHE

    def build_block_for_mentor(self, mentor: "Mentor") -> str:
        """
        Devuelve el bloque de skills listo para inyectar en el system_prompt.
        Vacio ('') si el mentor no tiene skills habilitadas.

        Formato:
            ## Skills disponibles

            ### {title}
            {content}

            ---

            ### {title}
            {content}

            ---
        """
        now = time.monotonic()
        cached = self._cache.get(mentor.id)
        if cached and cached[0] > now:
            return cached[1]

        skills = self._repo.list_enabled_for_mentor(mentor.id)
        block = self._format_block(skills, mentor.slug)

        self._cache[mentor.id] = (now + CACHE_TTL_SECONDS, block)
        return block

    def invalidate(self, mentor_id: int) -> None:
        """Invalida el cache para un mentor. Llamar tras cualquier write de skills."""
        self._cache.pop(mentor_id, None)
        logger.debug("skill_loader_cache_invalidated", extra={"mentor_id": mentor_id})

    def clear_cache(self) -> None:
        """
        Limpia todo el cache de skills (todos los mentores).
        Usar tras mass ingest o cuando se necesite que todos los mentores
        recarguen sus skills desde la BD en el proximo request.
        """
        self._cache.clear()
        logger.info("skill_loader_cache_cleared")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _format_block(self, skills: list, mentor_slug: str) -> str:
        if not skills:
            return ""

        lines: list[str] = ["## Skills disponibles", ""]
        total_chars = len("## Skills disponibles\n\n")
        included = 0
        dropped = 0

        for skill in skills:
            content = skill.content or ""

            # Truncar skill individual si supera el maximo por skill
            if len(content) > MAX_PER_SKILL_CHARS:
                content = content[:MAX_PER_SKILL_CHARS - len(TRUNCATE_SUFFIX)] + TRUNCATE_SUFFIX

            # Calcular cuanto agregan este skill al total
            skill_section = f"### {skill.title}\n{content}\n\n---\n\n"
            skill_chars = len(skill_section)

            if total_chars + skill_chars > MAX_TOTAL_CHARS:
                # No entra -- parar aqui (no incluir skills parciales)
                dropped += 1
                continue

            lines.append(f"### {skill.title}")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")
            total_chars += skill_chars
            included += 1

        logger.info(
            "skills_block_built",
            extra={
                "mentor": mentor_slug,
                "skill_count": included,
                "total_chars": total_chars,
                "dropped": dropped,
            },
        )

        if included == 0:
            return ""

        return "\n".join(lines).rstrip() + "\n"
