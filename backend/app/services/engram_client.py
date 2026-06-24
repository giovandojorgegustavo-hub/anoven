"""
Cliente HTTP para engram (memoria persistente).

Engram corre en `localhost:7437` y expone un REST API. Documentamos acá
los endpoints que usamos. Si engram no responde dentro del timeout,
NINGUNA función levanta — devolvemos un valor neutro (None, lista vacía)
así el chat sigue funcionando sin memoria. **Degradación elegante** es la
regla: la memoria es un complemento, no un bloqueante.

Convención de namespacing de Anoven:

    project = "anoven-app-user-{user_id}"          (por user)
    type    = "conversation_turn" | "rule" | "user_note"
    scope   = "project"                            (default — privado al user)

Each user de anoven-app tiene su propio "project" en engram — eso garantiza
aislamiento entre users. No mezclamos memorias.
"""

import logging
import uuid
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


# ============================================================
# Helpers de namespacing
# ============================================================

def project_for_user(user_id: int) -> str:
    """Namespace legacy — solo por user. Lo dejamos para el smoke test y
    casos sin contexto de project. Para chat usar project_for_user_and_project."""
    return f"anoven-app-user-{user_id}"


def project_for_user_and_project(user_id: int, project_slug: str) -> str:
    """
    Namespace para el chat de un user dentro de un project específico de
    anoven-app. Cada anoven-project tiene su propio scope de memoria —
    sin contagio entre 'Bonabowl' y 'Mi café' del mismo user.

        anoven-app-user-1-bonabowl
        anoven-app-user-1-general
    """
    return f"anoven-app-user-{user_id}-{project_slug}"


def new_session_id() -> str:
    """Engram requiere un UUID externo para las sesiones."""
    return str(uuid.uuid4())


# Namespace UUID FIJO para derivar session_ids de conversation_id de forma
# determinística (uuid5). NUNCA cambiar — si cambia, perdemos el vínculo a
# las observations existentes en engram.
_CONV_SESSION_NS = uuid.UUID("3b1b1c40-9d3e-4f2c-bbed-8f9c0d2a1234")


def session_id_for_conversation(conv_id: int) -> str:
    """
    Devuelve un UUID determinístico para la conversation. Misma conv_id →
    mismo session_id siempre. Permite vincular todos los turns de una
    conversación a la misma sesión de engram sin guardar nada extra en BD.
    """
    return str(uuid.uuid5(_CONV_SESSION_NS, f"anoven-conv-{conv_id}"))


# ============================================================
# Cliente HTTP
# ============================================================

class EngramClient:
    """
    Wrapper fino sobre el HTTP API de engram.

    Todos los métodos son **fail-safe**: si engram está caído o responde
    error, loguean y devuelven valor neutro. El caller NO maneja excepciones.
    """

    def __init__(self) -> None:
        self.base_url = settings.engram_url.rstrip("/")
        self.timeout = settings.engram_timeout_seconds

    # --- Health -----------------------------------------------

    def health(self) -> bool:
        """True si engram responde sano."""
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=self.timeout)
            return r.status_code == 200 and r.json().get("status") == "ok"
        except Exception as e:
            logger.warning("engram health check failed: %s", e)
            return False

    # --- Sesiones ---------------------------------------------

    def create_session(self, session_id: str, project: str) -> bool:
        """Crea una sesión en engram. Idempotente: si ya existe devuelve True."""
        try:
            r = httpx.post(
                f"{self.base_url}/sessions",
                json={"id": session_id, "project": project},
                timeout=self.timeout,
            )
            if r.status_code == 201:
                return True
            # 409 (already exists) lo tomamos como éxito
            if r.status_code == 409:
                return True
            logger.warning(
                "engram create_session HTTP %s: %s",
                r.status_code, r.text[:200],
            )
            return False
        except Exception as e:
            logger.warning("engram create_session error: %s", e)
            return False

    # --- Observations -----------------------------------------

    def save_observation(
        self,
        session_id: str,
        project: str,
        title: str,
        content: str,
        obs_type: str = "discovery",
    ) -> dict[str, Any] | None:
        """
        Guarda una observación. Devuelve dict con `id` y `sync_id` si OK,
        None si falla.
        """
        payload = {
            "session_id": session_id,
            "project": project,
            "title": title,
            "content": content,
            "type": obs_type,
            "scope": "project",
        }
        try:
            r = httpx.post(
                f"{self.base_url}/observations",
                json=payload,
                timeout=self.timeout,
            )
            if r.status_code == 201:
                return r.json()
            logger.warning(
                "engram save_observation HTTP %s: %s",
                r.status_code, r.text[:200],
            )
            return None
        except Exception as e:
            logger.warning("engram save_observation error: %s", e)
            return None

    # --- Search -----------------------------------------------

    def search(
        self,
        query: str,
        project: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Busca observations relevantes. Devuelve lista vacía si falla o si query vacío."""
        if not query or not query.strip():
            # engram requiere q non-empty; skip the call para no logear 400.
            return []
        try:
            r = httpx.get(
                f"{self.base_url}/search",
                params={
                    "q": query,
                    "project": project,
                    "limit": str(limit),
                },
                timeout=self.timeout,
            )
            if r.status_code != 200:
                logger.warning(
                    "engram search HTTP %s: %s",
                    r.status_code, r.text[:200],
                )
                return []
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("engram search error: %s", e)
            return []


# Singleton — todos los services lo usan.
engram = EngramClient()
