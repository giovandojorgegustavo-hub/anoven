"""
InterviewService — lógica de negocio del Entrevistador.

Sesión 2.1: crear/resumir intento.
Sesión 2.2: chat con streaming.
Sesión 2.3: marker [INTERVIEW_COMPLETE] + cierre del attempt (este archivo).
Sesión 2.4: Evaluador.
"""

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.interview_attempt import InterviewAttempt
from app.models.interview_message import InterviewMessage
from app.models.user import User
from app.repositories.interview_repo import InterviewRepository
from app.repositories.interview_message_repo import InterviewMessageRepository
from app.repositories.user_repo import UserRepository
from app.services.entrevistador import (
    INITIAL_GREETING,
    stream_entrevistador_reply,
)
from app.services.evaluador import evaluate_conversation
from app.services.mentor_matcher import match_mentors
from app.services.mentor_service import MentorService


# El marker que emite el Entrevistador cuando decide cerrar la entrevista.
# Lo definimos acá como constante para que el detector y el "stripper" usen
# la misma definición. En Fase 5 vamos a tener más markers (PROTOTYPE_READY,
# MENTOR_FINALIZED) y vamos a refactorear a strategy pattern — por ahora
# uno solo, inline.
COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"


class InterviewError(Exception):
    pass


class AlreadyPassed(InterviewError):
    pass


class AttemptNotFound(InterviewError):
    pass


class AttemptNotYours(InterviewError):
    pass


class AttemptClosed(InterviewError):
    pass


class AttemptNotReadyForEvaluation(InterviewError):
    """El attempt no está en estado 'completed' — no se puede evaluar todavía."""
    pass


class AlreadyEvaluated(InterviewError):
    pass


class InterviewService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = InterviewRepository(db)
        self.msg_repo = InterviewMessageRepository(db)
        self.user_repo = UserRepository(db)

    # ============================================================
    # Iniciar / Resumir
    # ============================================================

    def start_or_resume(self, user: User) -> InterviewAttempt:
        # Si el user ya pasó, devolvemos su último attempt (esté en estado
        # 'completed' o 'evaluated'). El frontend lee `attempt.status` y
        # decide qué mostrar: panel de "evaluando" si está completed, o
        # el resultado cached si ya está evaluated.
        # Solo tiramos AlreadyPassed si no hay ningún attempt previo
        # (caso defensivo — no debería pasar si onboarding_state='passed').
        if user.onboarding_state == "passed":
            latest = self.repo.get_latest_for_user(user.id)
            if latest is not None:
                return latest
            raise AlreadyPassed(
                "Ya pasaste la entrevista pero no se encuentra el intento."
            )

        attempt = self.repo.get_in_progress_for_user(user.id)
        if attempt is None:
            attempt = self.repo.create(user_id=user.id)
            user.onboarding_state = "in_progress"
            user.onboarding_attempts += 1
            self.db.commit()
            self.db.refresh(user)

        # Si no hay mensajes, insertamos el saludo inicial pre-escrito.
        existing = self.msg_repo.list_for_attempt(attempt.id)
        if not existing:
            self.msg_repo.create(
                attempt_id=attempt.id,
                role="assistant",
                content=INITIAL_GREETING,
            )

        return attempt

    def list_messages(self, attempt_id: int, user_id: int) -> list[InterviewMessage]:
        attempt = self._load_and_verify(attempt_id, user_id)
        return self.msg_repo.list_for_attempt(attempt.id)

    # ============================================================
    # Chat con streaming + detección del marker
    # ============================================================

    def send_user_message_and_stream(
        self,
        attempt_id: int,
        user_id: int,
        content: str,
    ) -> Iterable[str]:
        """
        Flujo (Sesión 2.3):
          1. Verifica que el intento sea del user y esté `in_progress`.
          2. Persiste el mensaje del user.
          3. Llama al Entrevistador en streaming.
          4. Mientras llega el stream, busca el marker [INTERVIEW_COMPLETE]:
             - Lo STRIPEA del texto que se envía al frontend.
             - Cuando lo detecta, marca `attempt.status='completed'`,
               `attempt.finished_at=now`, y `user.onboarding_state='passed'`.
             - Emite un evento SSE `event: interview_complete` antes del [DONE].
          5. Persiste el mensaje del assistant (sin el marker) en BD.

        Yields strings ya en formato SSE — la route los pasa a StreamingResponse.
        """
        attempt = self._load_and_verify(attempt_id, user_id)
        if attempt.status != "in_progress":
            raise AttemptClosed(
                f"Este intento está en estado '{attempt.status}', no se puede chatear."
            )

        # 1) Persistir el mensaje del user.
        self.msg_repo.create(attempt_id=attempt.id, role="user", content=content)

        # 2) Armar el history.
        history = [
            {"role": m.role, "content": m.content}
            for m in self.msg_repo.list_for_attempt(attempt.id)
        ]

        # Capturamos referencias locales para usar en el generator (la sesión
        # de SQLAlchemy sigue viva durante el streaming gracias a FastAPI).
        attempt_id_local = attempt.id
        user_id_local = user_id

        def generator() -> Iterable[str]:
            # buffer: lo que todavía no emitimos (puede contener prefijo del marker).
            # accumulated: TODO el texto recibido (para persistir).
            buffer = ""
            accumulated_parts: list[str] = []
            marker_detected = False

            try:
                for chunk in stream_entrevistador_reply(history):
                    accumulated_parts.append(chunk)

                    if marker_detected:
                        # Una vez visto el marker, dejamos consumir el stream
                        # pero no emitimos más texto al user.
                        continue

                    buffer += chunk

                    # ¿Apareció el marker completo en buffer?
                    if COMPLETE_MARKER in buffer:
                        idx = buffer.index(COMPLETE_MARKER)
                        # Emitimos solo el texto ANTES del marker.
                        pre = buffer[:idx]
                        if pre:
                            yield _sse_data({"text": pre})
                        buffer = ""
                        marker_detected = True
                        continue

                    # Si buffer es más largo que el marker, emitimos la parte
                    # "segura" (lo que no puede ser prefijo del marker) y
                    # retenemos los últimos len(MARKER) chars por las dudas.
                    if len(buffer) > len(COMPLETE_MARKER):
                        safe_len = len(buffer) - len(COMPLETE_MARKER)
                        safe = buffer[:safe_len]
                        yield _sse_data({"text": safe})
                        buffer = buffer[safe_len:]

                # Stream terminó. Si nunca apareció el marker, vaciamos el
                # buffer (era texto normal sin marker).
                if not marker_detected and buffer:
                    yield _sse_data({"text": buffer})

                # Si vimos el marker, cerramos el attempt + pasamos al user.
                if marker_detected:
                    self._close_attempt_and_pass_user(
                        attempt_id=attempt_id_local,
                        user_id=user_id_local,
                    )
                    yield _sse_event("interview_complete", {"attempt_id": attempt_id_local})

                yield "data: [DONE]\n\n"
            finally:
                # Persistimos lo que vino (sin el marker para que el chat
                # quede limpio en futuras cargas).
                full_text = "".join(accumulated_parts)
                cleaned = full_text.replace(COMPLETE_MARKER, "").rstrip()
                if cleaned:
                    self.msg_repo.create(
                        attempt_id=attempt_id_local,
                        role="assistant",
                        content=cleaned,
                    )

        return generator()

    # ============================================================
    # Helpers privados
    # ============================================================

    # ============================================================
    # Evaluador (Sesión 2.4)
    # ============================================================

    def evaluate_attempt(self, attempt_id: int, user_id: int) -> dict:
        """
        Pipeline post-entrevista:
          1) Evaluador → score + profile_json + feedback + highlights
          2) MentorMatcher → 5 mentores del catálogo según el profile
          3) Replace user_mentors → desactivar defaults + asignar matched

        Idempotente: si ya fue evaluado, devuelve lo guardado (no re-cobra
        Anthropic). El matcher SÍ se recorre si por algún motivo no se
        replazaron los mentors.

        Returns un dict para EvaluationResponse:
            { "score": int, "highlights": [str], "matched_mentors": [{slug, nombre, reason}] }
        El profile_json y el feedback se quedan en BD — internos.
        """
        attempt = self._load_and_verify(attempt_id, user_id)

        if attempt.status == "evaluated":
            return self._build_response_from_stored(attempt, user_id)

        if attempt.status != "completed":
            raise AttemptNotReadyForEvaluation(
                f"Attempt está en '{attempt.status}', se evalúa solo cuando está 'completed'."
            )

        # ===== Paso 1: Evaluador =====
        msgs = self.msg_repo.list_for_attempt(attempt.id)
        history = [{"role": m.role, "content": m.content} for m in msgs]
        raw = evaluate_conversation(history)

        # Defensive: aunque el tool schema marca todos como required, Anthropic
        # ocasionalmente devuelve incompleto. Llenamos defaults para no crashear.
        score = int(raw.get("score") or 0)
        profile = raw.get("profile") or {}
        feedback = raw.get("feedback") or ""
        highlights = raw.get("highlights") or _highlights_from_profile(profile)

        self.repo.save_evaluation(
            attempt_id=attempt.id,
            score=score,
            profile_json=json.dumps(profile, ensure_ascii=False),
            evaluator_feedback=feedback,
        )

        # Persistimos los mentor_gaps detectados como MentorRequests con
        # source='interview'. Quedan pending para que el user los cree o
        # vos como admin los curaste.
        gaps = raw.get("mentor_gaps") or []
        if gaps:
            from app.models.mentor_request import MentorRequest
            for gap in gaps:
                nombre = (gap.get("nombre") or "").strip()
                why = (gap.get("why") or "").strip()
                if not nombre or not why:
                    continue
                req = MentorRequest(
                    user_id=user_id,
                    source="interview",
                    proposed_name=nombre[:120],
                    proposed_canon=(gap.get("proposed_canon") or "").strip()[:500] or None,
                    why=why,
                    status="pending",
                )
                self.db.add(req)
            self.db.commit()

        # ===== Paso 2: MentorMatcher =====
        mentor_service = MentorService(self.db)
        catalog = mentor_service.list_global_catalog()

        matches = match_mentors(profile=profile, catalog=catalog)

        # ===== Paso 3: Reemplazar asignaciones del user =====
        new_assignments = mentor_service.replace_with_matched(
            user_id=user_id,
            matches=matches,
        )

        # Armamos el response combinando match (slug+reason) + mentor (nombre).
        slug_to_reason = {m["slug"]: m["reason"] for m in matches}
        slug_to_mentor = {m["slug"]: m for m in catalog}
        matched_mentors = []
        for um in new_assignments:
            mentor = slug_to_mentor.get(
                next((c["slug"] for c in catalog if c["id"] == um.mentor_id), "")
            )
            if mentor is None:
                continue
            matched_mentors.append({
                "slug": mentor["slug"],
                "nombre": mentor["nombre"],
                "reason": slug_to_reason.get(mentor["slug"], ""),
            })

        return {
            "score": score,
            "highlights": highlights,
            "matched_mentors": matched_mentors,
        }

    def _build_response_from_stored(
        self,
        attempt: InterviewAttempt,
        user_id: int,
    ) -> dict:
        """
        Reconstruye la respuesta para el frontend desde lo guardado en BD.
        Los highlights se derivan del profile. Los matched_mentors salen de
        las asignaciones activas del user (source='matched').
        """
        profile = json.loads(attempt.profile_json or "{}")
        highlights = _highlights_from_profile(profile)

        # Reconstruimos matched_mentors desde las asignaciones activas.
        # Las razones AHORA sí están guardadas en user_mentors.match_reason.
        mentor_service = MentorService(self.db)
        ums_data = mentor_service.list_user_mentors_with_data(user_id)
        matched_mentors = [
            {
                "slug": item["mentor"].slug,
                "nombre": item["mentor"].nombre,
                "reason": item.get("match_reason") or "",
            }
            for item in ums_data
            if item["source"] == "matched"
        ]

        return {
            "score": attempt.score or 0,
            "highlights": highlights or ["Tu perfil ya está procesado."],
            "matched_mentors": matched_mentors,
        }

    # ============================================================
    # Helpers privados
    # ============================================================

    def _close_attempt_and_pass_user(self, attempt_id: int, user_id: int) -> None:
        """
        Cuando se detecta el marker:
          - attempt: status='completed', finished_at=now
          - user: onboarding_state='passed' (NO hay gate — todos pasan)

        Si más adelante el Evaluador (Sesión 2.4) quiere registrar score
        bajo, NO modifica `onboarding_state` — el score es solo métrica
        interna para Anoven.
        """
        attempt = self.db.get(InterviewAttempt, attempt_id)
        user = self.db.get(User, user_id)
        if attempt is None or user is None:
            return
        attempt.status = "completed"
        attempt.finished_at = datetime.utcnow()
        user.onboarding_state = "passed"
        self.db.commit()

    def _load_and_verify(self, attempt_id: int, user_id: int) -> InterviewAttempt:
        attempt = self.db.get(InterviewAttempt, attempt_id)
        if attempt is None:
            raise AttemptNotFound(f"Intento {attempt_id} no existe.")
        if attempt.user_id != user_id:
            raise AttemptNotFound(f"Intento {attempt_id} no existe.")
        return attempt


def _highlights_from_profile(profile: dict) -> list[str]:
    """
    Fallback que arma highlights a partir del profile_json cuando el LLM no
    devolvió el campo `highlights` explícitamente, o cuando estamos re-armando
    la respuesta desde lo guardado en BD.
    """
    out: list[str] = []
    if profile.get("current_focus"):
        out.append(f"Estás con: {profile['current_focus']}.")
    if profile.get("tools"):
        out.append(f"Usás: {', '.join(profile['tools'][:3])}.")
    if profile.get("fears"):
        out.append(f"Te preocupa: {profile['fears'][0]}.")
    if not out:
        out = ["Tu perfil ya está procesado."]
    return out


# ============================================================
# Helpers de SSE
# ============================================================

def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_event(event_name: str, payload: dict) -> str:
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )
