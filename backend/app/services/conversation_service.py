"""
ConversationService — lógica de negocio del chat con mentor.

Sesión 3.1: crear o resumir conversación + load by id.
Sesión 3.2: list_messages + send_user_message_and_stream (este archivo).
"""

import json
import logging
import re
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.mentor_repo import MentorRepository, UserMentorRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.project_repo import ProjectRepository, UseCaseRepository
from app.services.engram_client import (
    engram,
    project_for_user,
    project_for_user_and_project,
    session_id_for_conversation,
)
from app.services.mentor_chat import stream_mentor_reply
from app.services.model_resolver import ModelResolver
from app.services.tool_dispatcher import ToolContext
from app.services.engram_client import session_id_for_conversation as _conv_session_id
from app.services.promptifex import generate_mentor_draft
from app.services.title_generator import generate_title
from app.services.skill_loader import SkillLoader
from app.repositories.mentor_skill_repository import MentorSkillRepository
from app.models.attachment import Attachment


CREATOR_PROTOTYPE_MARKER = "[PROTOTYPE_READY]"


logger = logging.getLogger(__name__)


class ConversationError(Exception):
    pass


class MentorNotAccessible(ConversationError):
    """El user no tiene asignado este mentor."""
    pass


class ConversationNotFound(ConversationError):
    pass


class MentorUnavailable(ConversationError):
    """El mentor está inactivo / archivado."""
    pass


class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ConversationRepository(db)
        self.mentor_repo = MentorRepository(db)
        self.user_mentor_repo = UserMentorRepository(db)
        self.msg_repo = MessageRepository(db)
        self.project_repo = ProjectRepository(db)
        self.use_case_repo = UseCaseRepository(db)
        self.skill_loader = SkillLoader(repo=MentorSkillRepository(db))

    def start_or_resume(
        self,
        user: User,
        mentor_id: int,
        force_new: bool = False,
    ) -> Conversation:
        """
        Verifica acceso del user al mentor y devuelve/crea conversación
        en el active_project del user (default use_case del project).

        Excepción: mentores con visibility='special' (ej: el Creador) NO
        requieren asignación previa. Cualquier user puede iniciarles chat
        directo desde el flow "Crear mentor".
        """
        mentor = self.mentor_repo.get_by_id(mentor_id)
        if mentor is None:
            raise MentorNotAccessible(
                f"El mentor {mentor_id} no está disponible."
            )
        # Mentores propios del user (created_by_self) se permiten aunque esten
        # en pending_review (esperando curacion del admin). Mentores ajenos
        # solo si status=active.
        is_own = mentor.created_by_user_id == user.id
        allowed_statuses = ("active", "pending_review") if is_own else ("active",)
        if mentor.status not in allowed_statuses:
            raise MentorNotAccessible(
                f"El mentor {mentor_id} no está disponible."
            )

        # Special mentors (el Creador) NO requieren user_mentor assignment.
        if mentor.visibility != "special":
            if not self.user_mentor_repo.is_assigned(user.id, mentor_id):
                raise MentorNotAccessible(
                    f"No tenés asignado el mentor {mentor_id}."
                )

        # Resolvemos el use_case en el active_project del user.
        use_case_id = self._resolve_default_use_case_id(user)

        if not force_new:
            existing = self.repo.latest_for_user_mentor_and_use_case(
                user_id=user.id,
                mentor_id=mentor_id,
                use_case_id=use_case_id,
            )
            if existing is not None:
                return existing

        conv = self.repo.create(
            user_id=user.id,
            mentor_id=mentor_id,
            use_case_id=use_case_id,
        )

        # TODOS los mentores reciben un saludo inicial pre-escrito en cada
        # conversación nueva. Tres fuentes en cascada:
        #   1. Hardcoded por slug (Creador, Entrevistador, etc.)
        #   2. Extraído del §2 Turn-1 presentation del CLAUDE.md del mentor
        #   3. Generado del nombre + filosofía como último recurso
        #
        # Esto evita el bug del "mentor responde genérico porque no sabe para
        # qué vino" cuando el user abre un chat nuevo. Cada mentor rompe el
        # hielo con su voz canónica.
        greeting = _build_initial_greeting(mentor)
        if greeting:
            self.msg_repo.create(
                conv_id=conv.id,
                role="assistant",
                content=greeting,
            )

        return conv

    def _find_similar_mentors(self, draft: dict) -> list:
        """Para 5.4 dedup. Delega al MentorService."""
        from app.services.mentor_service import MentorService
        ms = MentorService(self.db)
        return ms.find_similar(
            canon=draft.get("canon", ""),
            filosofia=draft.get("filosofia", ""),
        )

    def _create_custom_mentor_from_draft(self, user_id: int, draft: dict):
        """Para 5.3 persistencia + auto-asignación."""
        from app.services.mentor_service import MentorService
        ms = MentorService(self.db)
        return ms.create_custom_mentor(
            user_id=user_id,
            slug=draft["slug"],
            nombre=draft["nombre"],
            canon=draft["canon"],
            filosofia=draft["filosofia"],
            system_prompt=draft["system_prompt"],
        )

    def _build_rules_block(self, user_id: int, use_case_id: int | None) -> str:
        """
        Devuelve el bloque de reglas activas del user con scope aplicable.

        Implementado en Sesión 4.5 (Rules). Por ahora stub que devuelve
        string vacío — el system_prompt no inyecta nada.
        """
        try:
            from app.services.rule_service import RuleService
            return RuleService(self.db).build_block_for_user(user_id, use_case_id)
        except ImportError:
            return ""

    def _resolve_engram_project(self, conv: Conversation, user_id: int) -> str:
        """
        Devuelve el namespace de engram para esta conversación, basado en
        el anoven-project al que pertenece (via use_case → project).

        Fallback: si la conv no tiene use_case asociado (legacy), usamos
        el default project del user. Como último recurso, namespace legacy.
        """
        if conv.use_case_id is not None:
            uc = self.use_case_repo.get_by_id(conv.use_case_id)
            if uc is not None:
                project = self.project_repo.get_by_id(uc.project_id)
                if project is not None:
                    return project_for_user_and_project(user_id, project.slug)

        default = self.project_repo.get_default_for_user(user_id)
        if default is not None:
            return project_for_user_and_project(user_id, default.slug)

        return project_for_user(user_id)

    def _retrieve_relevant_memories(
        self,
        query: str,
        engram_project: str,
        current_conv_id: int,
        limit: int = 3,
    ) -> list[dict]:
        """
        Busca memorias relevantes en engram, EXCLUYENDO la conversación actual.

        Estrategia en 2 pasos:

        1. **Por relevancia**: una search por token significativo, dedupe, sort
           por rank FTS5. Engram NO soporta OR/AND como keywords, así que
           hacemos N micro-searches.

        2. **Fallback por recencia**: si paso 1 no encontró nada (mensaje del
           user sin overlap con memorias — typo, query muy abstracta, etc.),
           devolvemos las últimas N observations del project. Mejor algún
           contexto que ningún contexto.
        """
        current_session_id = session_id_for_conversation(current_conv_id)

        # === Paso 1: relevance search ===
        tokens = _significant_tokens(query)
        seen_ids: set = set()
        combined: list[dict] = []

        for token in tokens[:8]:
            results = engram.search(token, project=engram_project, limit=5)
            for obs in results:
                obs_id = obs.get("id")
                if obs_id is None or obs_id in seen_ids:
                    continue
                if obs.get("session_id") == current_session_id:
                    continue
                seen_ids.add(obs_id)
                combined.append(obs)

        combined.sort(key=lambda o: o.get("rank", 0))
        if combined:
            return combined[:limit]

        # === Paso 2: fallback semantico ===
        # Si la busqueda principal no dio suficiente, intentamos con el ultimo
        # mensaje del user como query. engram requiere q non-empty.
        fallback_query = (query or "").strip()[:200]
        if not fallback_query:
            return []
        recent = engram.search(fallback_query, project=engram_project, limit=limit * 3)
        out: list[dict] = []
        for obs in recent:
            if obs.get("session_id") == current_session_id:
                continue
            out.append(obs)
            if len(out) >= limit:
                break
        return out

    def _resolve_default_use_case_id(self, user: User) -> int | None:
        """
        Devuelve el id del default use_case del active project del user.
        Si por alguna razón no hay project ni use_case (edge case), devolvemos
        None — la conversación queda 'huérfana' y caerá al default mostrado.
        """
        active_project_id = user.active_project_id
        if active_project_id is None:
            project = self.project_repo.get_default_for_user(user.id)
            if project is None:
                return None
            active_project_id = project.id
        default_uc = self.use_case_repo.get_default_for_project(active_project_id)
        return default_uc.id if default_uc else None

    def get_for_user(self, conv_id: int, user_id: int) -> Conversation:
        """Devuelve la conversación si pertenece al user, sino 404."""
        conv = self.repo.get_by_id(conv_id)
        if conv is None or conv.user_id != user_id:
            raise ConversationNotFound(
                f"Conversación {conv_id} no existe."
            )
        return conv

    def rename_title(self, conv_id: int, user_id: int, title: str) -> Conversation:
        conv = self.get_for_user(conv_id, user_id)
        return self.repo.set_title(conv.id, title.strip()[:200]) or conv

    def delete_for_user(self, conv_id: int, user_id: int) -> None:
        """Borra la conversación y sus mensajes (no engram, eso queda para histórico)."""
        conv = self.get_for_user(conv_id, user_id)
        # Borrar mensajes primero (no hay cascade configurado)
        from app.models.message import Message
        self.db.query(Message).filter(Message.conversation_id == conv.id).delete()
        self.db.delete(conv)
        self.db.commit()

    def list_for_user(self, user: User) -> list[Conversation]:
        """
        Conversaciones del user EN SU PROJECT ACTIVO. Si el user está en su
        default project, también incluye conversaciones huérfanas (sin use_case_id).
        Ordenadas por updated_at desc.
        """
        active_project_id = user.active_project_id
        if active_project_id is None:
            default = self.project_repo.get_default_for_user(user.id)
            if default is None:
                return []
            active_project_id = default.id

        use_cases = self.use_case_repo.list_for_project(active_project_id)
        use_case_ids = [uc.id for uc in use_cases]

        default_project = self.project_repo.get_default_for_user(user.id)
        include_orphans = (
            default_project is not None
            and active_project_id == default_project.id
        )

        return self.repo.list_for_user_in_use_cases(
            user_id=user.id,
            use_case_ids=use_case_ids,
            include_orphans=include_orphans,
        )

    # ============================================================
    # Mensajes (Sesión 3.2)
    # ============================================================

    def list_messages(self, conv_id: int, user_id: int) -> list[Message]:
        """Mensajes de la conversación, en orden cronológico.

        Inyecta attachment_urls (lista de /storage/...) en cada Message para
        que el frontend pueda renderizar imágenes (generadas o adjuntadas) al
        cargar la conversación.
        """
        conv = self.get_for_user(conv_id, user_id)
        msgs = self.msg_repo.list_for_conversation(conv.id)
        if not msgs:
            return msgs
        msg_ids = [m.id for m in msgs]
        atts = (
            self.db.query(Attachment)
            .filter(Attachment.message_id.in_(msg_ids))
            .order_by(Attachment.id.asc())
            .all()
        )
        by_msg: dict[int, list[str]] = {}
        for a in atts:
            by_msg.setdefault(a.message_id, []).append(f"/storage/{a.file_path}")
        for m in msgs:
            m.attachment_urls = by_msg.get(m.id, [])
        return msgs

    def send_user_message_and_stream(
        self,
        conv_id: int,
        user_id: int,
        content: str,
        attachment_ids: list[int] | None = None,
        billing_resolver=None,
    ) -> Iterable[str]:
        """
        Flujo:
          1. Verifica que la conversación pertenezca al user.
          2. Carga el mentor y su system_prompt (el CLAUDE.md importado).
          3. Persiste el mensaje del user.
          4. Llama a Claude en streaming con system_prompt + history.
          5. Yields chunks formateados como SSE `data: {...}\\n\\n`.
          6. Al terminar, persiste el mensaje completo del assistant.

        Yields strings en formato SSE — la route los pasa a StreamingResponse.
        """
        conv = self.get_for_user(conv_id, user_id)

        mentor = self.mentor_repo.get_by_id(conv.mentor_id)
        if mentor is None:
            raise MentorUnavailable(
                f"El mentor de esta conversación no está disponible."
            )
        is_own_mentor = mentor.created_by_user_id == user_id
        allowed_statuses = ("active", "pending_review") if is_own_mentor else ("active",)
        if mentor.status not in allowed_statuses:
            raise MentorUnavailable(
                f"El mentor de esta conversación no está disponible."
            )

        # 1) Persistir mensaje del user.
        user_msg = self.msg_repo.create(conv_id=conv.id, role="user", content=content, author_user_id=user_id)

        # 1b) Si vinieron attachments, los vinculamos al mensaje del user.
        # Ramificación por tipo:
        #   - image/*       -> bloque type:image (Anthropic vision).
        #   - PDF indexado  -> NO se manda inline; el RAG inyecta contexto aparte.
        #   - PDF no-indexado (<=100 pag) -> bloque type:document (Anthropic PDF nativo).
        attachment_blocks: list[dict] = []
        if attachment_ids:
            atts = (
                self.db.query(Attachment)
                .filter(Attachment.id.in_(attachment_ids))
                .filter(Attachment.user_id == user_id)
                .all()
            )
            import base64
            from pathlib import Path
            storage_root = Path("/home/anoven/anoven-app/storage/uploads")
            for a in atts:
                a.message_id = user_msg.id
                if a.mime_type == "application/pdf" and a.is_indexed:
                    # RAG-managed: skip inline. El retrieval mas abajo se encarga.
                    continue
                file_full = storage_root / a.file_path
                if file_full.exists():
                    # Word docs (docx/doc): extraer texto y mandar como text block.
                    # Claude no soporta docx nativo; convertimos a texto.
                    if a.mime_type in (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "application/msword",
                    ):
                        try:
                            from docx import Document as _DocxDoc
                            _doc = _DocxDoc(str(file_full))
                            _docx_text = "\n\n".join(p.text for p in _doc.paragraphs if p.text.strip())
                            if _docx_text.strip():
                                attachment_blocks.append({
                                    "type": "text",
                                    "text": (
                                        f"=== Contenido del documento adjunto ({a.original_name or documento.docx}) ===\n\n"
                                        f"{_docx_text}\n\n"
                                        f"=== Fin del documento ==="
                                    ),
                                })
                        except Exception:
                            logger.exception("Failed to extract text from docx att=%s", a.id)
                        continue
                    raw = file_full.read_bytes()
                    b64 = base64.standard_b64encode(raw).decode("ascii")
                    if a.mime_type == "application/pdf":
                        attachment_blocks.append({
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": b64,
                            },
                        })
                    else:
                        attachment_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": a.mime_type,
                                "data": b64,
                            },
                        })
            self.db.commit()

        # 1c) RAG retrieval — si la conversacion tiene PDFs indexados (de este o
        # cualquier turno previo), traemos top-k chunks relevantes a la query del
        # user y los inyectamos como bloque de texto antes del mensaje del user.
        from app.services.document_retriever import (
            has_indexed_documents,
            search_chunks,
            chunks_to_context_text,
        )
        rag_context_text: str = ""
        if has_indexed_documents(self.db, conv.id):
            chunks = search_chunks(self.db, conv.id, user_msg.content)
            rag_context_text = chunks_to_context_text(chunks)

        # 2) Resolver project_id para billing + context builder.
        _project_id_for_billing: int | None = None
        if conv.use_case_id is not None:
            _uc = self.use_case_repo.get_by_id(conv.use_case_id)
            if _uc is not None:
                _project_id_for_billing = _uc.project_id

        # 2b) Resolver billed_user_id via BillingResolver (shared project = owner paga).
        # Si la route inyectó el singleton (billing_resolver param), usarlo para
        # aprovechar el LRU cache cross-request. Si no, crear instancia local.
        _billed_user_id: int | None = None
        if _project_id_for_billing is not None:
            try:
                _br = billing_resolver
                if _br is None:
                    from app.services.billing_resolver import BillingResolver
                    from app.database import SessionLocal as _SessionLocal
                    _br = BillingResolver(db_factory=_SessionLocal)
                _billed_user_id = _br.resolve_billing_owner_id(_project_id_for_billing)
            except Exception:
                _billed_user_id = None  # Fallback: sin billing routing

        # 2c) Armar history para Anthropic. El ULTIMO mensaje (el del user que
        # recien persistimos) va multimodal si hay attachment_blocks o rag_context.
        # Para conversaciones compartidas usamos SharedProjectContextBuilder.
        all_msgs = self.msg_repo.list_for_conversation(conv.id)
        history: list[dict] = []
        for i, m in enumerate(all_msgs):
            is_last_user = (i == len(all_msgs) - 1 and m.role == "user")
            if is_last_user and (attachment_blocks or rag_context_text):
                multimodal: list[dict] = list(attachment_blocks)
                if rag_context_text:
                    multimodal.append({"type": "text", "text": rag_context_text})
                multimodal.append({"type": "text", "text": m.content})
                history.append({"role": "user", "content": multimodal})
            else:
                history.append({"role": m.role, "content": m.content})

        # 3) Resolvemos el engram project (namespace) para retrieval + save.
        engram_project = self._resolve_engram_project(conv, user_id)

        # 4) Retrieval (Sesión 4.4): buscamos memorias relevantes del MISMO
        # project para inyectar al system_prompt. Excluimos la conversación
        # actual — sus turns ya están en el chat history.
        memories = self._retrieve_relevant_memories(
            query=content,
            engram_project=engram_project,
            current_conv_id=conv.id,
            limit=3,
        )
        memory_block = _format_memory_block(memories)

        # 5) Streaming. Acumulamos el texto completo para persistirlo al final.
        conv_id_local = conv.id
        user_id_local = user_id
        user_message_local = content
        mentor_name_local = mentor.nombre
        engram_project_local = engram_project
        is_first_turn = len(history) == 1 and conv.title is None

        # 4.5: rules block — buscamos las reglas activas del user con scope
        # aplicable a este project / use_case. Por ahora puede venir vacío.
        rules_block = self._build_rules_block(user_id_local, conv.use_case_id)

        # Fase 1 — Skills block: ensamblamos las skills habilitadas del mentor.
        # Llamada sincrona, antes del stream. Vacío si el mentor no tiene skills.
        skills_block = self.skill_loader.build_block_for_mentor(mentor)

        # Phase 2 — Tool context: resolve engram_project BEFORE generator (needed here too).
        # conversation_tool_budget persists across turns for the same conv (in-memory).
        # Since generator() is re-created per request, this is per-turn. The per-conv
        # budget lives in the ToolBudget inside the agentic loop across iterations.
        _tool_context = ToolContext(
            engram_project=engram_project,
            engram_session_id=_conv_session_id(conv.id),
            conversation_id=conv.id,
            user_id=user_id,
            db=self.db,
        )
        # Per-conversation budget dict: mutated inside agentic loop across tool turns.
        # Fresh per request (each HTTP request = one user turn). The agentic loop
        # only needs this to track per-turn counters across multiple stream() calls.
        _conv_tool_budget: dict = {}

        is_creator = mentor.slug == "anoven-creador"
        history_for_promptifex = list(history)
        usage_capture: dict = {}

        def _on_usage(usage_data):
            """Accept a usage dict (from both legacy and agentic path).
            Legacy path sends: {"input_tokens":N, "output_tokens":N,
                                "cache_read_input_tokens":N, "cache_creation_input_tokens":N}
            """
            try:
                if isinstance(usage_data, dict):
                    usage_capture["input_tokens"] = usage_data.get("input_tokens", 0) or 0
                    usage_capture["output_tokens"] = usage_data.get("output_tokens", 0) or 0
                    usage_capture["cached_tokens"] = (
                        (usage_data.get("cache_creation_input_tokens", 0) or 0)
                        + (usage_data.get("cache_read_input_tokens", 0) or 0)
                    )
                else:
                    # Fallback: legacy object with .usage attribute
                    usage = getattr(usage_data, "usage", usage_data)
                    usage_capture["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
                    usage_capture["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
                    usage_capture["cached_tokens"] = (
                        (getattr(usage, "cache_creation_input_tokens", 0) or 0)
                        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
                    )
            except Exception:
                pass

        def generator() -> Iterable[str]:
            accumulated_parts: list[str] = []
            buffer = ""
            marker_seen = False
            _image_attachment_ids: list[int] = []  # track generate_image attachment IDs for message linking
            status_holder: list[dict] = []

            def _on_context_status(s: dict) -> None:
                status_holder.append(s)

            # sdd/per-mentor-model-assignment-v1: resolve effective Claude model
            # via 3-tier chain (user_override → mentor.model → env DEFAULT_MODEL).
            # Audit log row is written async by the resolver itself.
            from app.config import settings as _settings_for_resolver
            _resolver = ModelResolver(
                db_session=self.db,
                default_model=_settings_for_resolver.default_model,
            )
            _resolved = _resolver.resolve(
                user_id=user_id_local,
                mentor_id=mentor.id,
                conversation_id=conv_id_local,
            )
            _effective_model_for_turn = _resolved.effective_model

            try:
                _stream_gen = stream_mentor_reply(
                    mentor,
                    history,
                    memory_block=memory_block,
                    rules_block=rules_block,
                    skills_block=skills_block,
                    on_usage=_on_usage,
                    on_context_status=_on_context_status,
                    tool_context=_tool_context,
                    conversation_tool_budget=_conv_tool_budget,
                    model=_effective_model_for_turn,
                )

                # Emit ctx events BEFORE first content chunk (ADR-3).
                # on_context_status fires synchronously inside stream_mentor_reply
                # before Anthropic stream opens, so status_holder is populated
                # before any chunk is yielded.
                import itertools as _itools
                # _stream_gen now yields (event_type, payload) tuples.
                # Pull the first event to allow ctx status events to fire first.
                _first_chunk_buf = []
                for _fc in _stream_gen:
                    _first_chunk_buf.append(_fc)
                    break

                if status_holder:
                    _s = status_holder[0]
                    if _s.get("was_trimmed"):
                        _util_after = _s.get("utilization_after", 0.0)
                        yield _sse_event("ctx_compacted", {
                            "messages_dropped": _s.get("dropped_count", 0),
                            "tokens_before": _s.get("tokens_before", 0),
                            "tokens_after": _s.get("tokens_after", 0),
                        })
                        if _util_after >= 0.70:
                            yield _sse_event("ctx_warning", {
                                "utilization": round(_util_after, 4),
                                "tokens_used": _s.get("tokens_after", 0),
                                "tokens_max": 200000,
                                "tokens_reserved": 8192,
                            })
                    else:
                        _util = _s.get("utilization_after", _s.get("utilization_before", 0.0))
                        if _util >= 0.70:
                            yield _sse_event("ctx_warning", {
                                "utilization": round(_util, 4),
                                "tokens_used": _s.get("tokens_after", _s.get("tokens_before", 0)),
                                "tokens_max": 200000,
                                "tokens_reserved": 8192,
                            })

                for _evt in _itools.chain(_first_chunk_buf, _stream_gen):
                    # _evt is a (event_type, payload) tuple from stream_mentor_reply.
                    evt_type, payload = _evt

                    # ── Non-text events: emit SSE directly, skip marker scanning. ──
                    if evt_type == "tool_started":
                        yield _sse_event("tool_started", payload)
                        # generate_image: also emit image_generation_started for frontend
                        if payload.get("tool") == "generate_image":
                            yield _sse_event("image_generation_started", {"prompt": payload.get("input_preview", "")[:200]})
                        continue
                    elif evt_type == "tool_completed":
                        yield _sse_event("tool_completed", payload)
                        # generate_image: emit image_generated with attachment data for frontend
                        if payload.get("tool_name") == "generate_image" and payload.get("status") == "ok":
                            try:
                                import json as _json
                                _img_data = _json.loads(payload.get("content", "{}"))
                                _img_att_id = _img_data.get("attachment_id")
                                if _img_att_id:
                                    _image_attachment_ids.append(_img_att_id)
                                yield _sse_event("image_generated", {
                                    "attachment_id": _img_data.get("attachment_id"),
                                    "file_path": _img_data.get("file_path", ""),
                                    "url": _img_data.get("image_url", ""),
                                    "mime_type": _img_data.get("mime_type", "image/png"),
                                })
                            except Exception:
                                logger.exception("Failed to parse generate_image result for SSE")
                        continue
                    elif evt_type == "tool_failed":
                        yield _sse_event("tool_failed", payload)
                        # generate_image: also emit image_failed for frontend
                        if payload.get("tool_name") == "generate_image":
                            yield _sse_event("image_failed", {"error": payload.get("error", "unknown error")[:300]})
                        continue
                    elif evt_type == "tool_cap_reached":
                        yield _sse_event("tool_cap_reached", payload)
                        continue
                    elif evt_type != "text":
                        # Unknown event type — silently discard (forward compat)
                        continue

                    # ── Text event: run through marker scanning (unchanged logic). ──
                    chunk = payload
                    accumulated_parts.append(chunk)

                    # Passthrough si ni Creator ni Designer (o ya vimos marker).
                    if not is_creator or marker_seen:
                        yield _sse_chunk(chunk)
                        continue

                    buffer += chunk

                    if is_creator:
                        if CREATOR_PROTOTYPE_MARKER in buffer:
                            idx = buffer.index(CREATOR_PROTOTYPE_MARKER)
                            pre = buffer[:idx]
                            if pre:
                                yield _sse_chunk(pre)
                            marker_seen = True
                            buffer = ""
                            continue
                        if len(buffer) > len(CREATOR_PROTOTYPE_MARKER):
                            safe_len = len(buffer) - len(CREATOR_PROTOTYPE_MARKER)
                            yield _sse_chunk(buffer[:safe_len])
                            buffer = buffer[safe_len:]
                # Flush buffer pendiente si no apareció el marker
                if is_creator and not marker_seen and buffer:
                    yield _sse_chunk(buffer)

                # Si el Creador disparó el marker, corremos Promptifex.
                if is_creator and marker_seen:
                    yield _sse_event("mentor_creation_started", {})
                    yield _sse_chunk("\n\n_Armando tu mentor, dame unos segundos..._\n")
                    try:
                        full_clean = "".join(accumulated_parts).replace(
                            CREATOR_PROTOTYPE_MARKER, ""
                        ).rstrip()
                        promptifex_history = history_for_promptifex + [
                            {"role": "assistant", "content": full_clean}
                        ]
                        draft = generate_mentor_draft(promptifex_history)

                        # Dedup (5.4): si hay similar en el catálogo público,
                        # se lo señalamos al user antes de crear.
                        similar = self._find_similar_mentors(draft)

                        if similar:
                            yield _sse_event("similar_mentor_found", {
                                "draft": {
                                    "nombre": draft["nombre"],
                                    "canon": draft["canon"],
                                    "filosofia": draft["filosofia"],
                                },
                                "existing": [
                                    {
                                        "id": m.id,
                                        "nombre": m.nombre,
                                        "canon": m.canon,
                                        "filosofia": m.filosofia,
                                    }
                                    for m in similar[:3]
                                ],
                            })

                        # Persistimos igual el draft — si el user prefiere usar
                        # el existente lo puede borrar después.
                        new_mentor = self._create_custom_mentor_from_draft(
                            user_id=user_id_local,
                            draft=draft,
                        )

                        # Fase 1 — B2: insertar skills iniciales del mentor nuevo.
                        # Si Promptifex devolvio initial_skills, los sembramos.
                        # Errores aqui NO bloquean event: mentor_created.
                        initial_skills = draft.get("initial_skills") or []
                        if initial_skills:
                            try:
                                skill_repo = MentorSkillRepository(self.db)
                                skill_repo.bulk_create(
                                    mentor_id=new_mentor.id,
                                    skills=initial_skills,
                                )
                                self.skill_loader.invalidate(new_mentor.id)
                            except Exception:
                                logger.exception(
                                    "bulk_create initial_skills failed "
                                    "(mentor_id=%s) — mentor_created will still emit",
                                    new_mentor.id,
                                )

                        yield _sse_event("mentor_created", {
                            "mentor_id": new_mentor.id,
                            "nombre": new_mentor.nombre,
                            "canon": new_mentor.canon,
                            "filosofia": new_mentor.filosofia,
                        })
                    except Exception as e:
                        logger.exception("Promptifex pipeline failed")
                        yield _sse_event("mentor_creation_failed", {
                            "error": str(e)[:200],
                        })

            finally:
                full = "".join(accumulated_parts)
                full = full.replace(CREATOR_PROTOTYPE_MARKER, "").rstrip()
                _assistant_msg = None
                if full:
                    _assistant_msg = self.msg_repo.create(
                        conv_id=conv_id_local,
                        role="assistant",
                        content=full,
                    )


                # Link any generate_image tool attachments to the assistant message.
                if _image_attachment_ids and _assistant_msg:
                    try:
                        from app.models.attachment import Attachment as _Att
                        for _att_id in _image_attachment_ids:
                            _att_link = self.db.get(_Att, _att_id)
                            if _att_link:
                                _att_link.message_id = _assistant_msg.id
                        self.db.commit()
                    except Exception:
                        logger.exception("Failed to link generate_image attachment to message")

                # Persistir el turno (user msg + assistant msg) en engram para
                # que el mentor pueda recuperar contexto en turnos futuros.
                # ANTES estaba indentado DENTRO del if _image_attachment_ids,
                # asi que solo se guardaba cuando habia imagen generada.
                # Resultado: el mentor no recordaba conversaciones sin imagen.
                if _assistant_msg and full:
                    _save_turn_to_engram(
                        conv_id=conv_id_local,
                        engram_project=engram_project_local,
                        user_message=user_message_local,
                        assistant_message=full,
                        mentor_name=mentor_name_local,
                    )

                if is_first_turn and full:
                    try:
                        title = generate_title(user_message_local, full)
                        self.repo.set_title(conv_id_local, title)
                    except Exception:
                        pass

                # Tracking de costo del turn (Fase 7)
                # sdd/per-mentor-model-assignment-v1: use the SAME resolved model
                # as the stream call, not settings.default_model — otherwise cost
                # tracking misreports the actual model billed.
                if usage_capture:
                    from app.services.cost_tracker import track_cost
                    track_cost(
                        db=self.db,
                        user_id=user_id_local,
                        conversation_id=conv_id_local,
                        mentor_id=mentor.id,
                        model=_effective_model_for_turn,
                        input_tokens=usage_capture.get("input_tokens", 0),
                        output_tokens=usage_capture.get("output_tokens", 0),
                        cached_tokens=usage_capture.get("cached_tokens", 0),
                        purpose="chat",
                        billed_user_id=_billed_user_id,
                    )

        return generator()


# ============================================================
# Helpers
# ============================================================

def _sse_chunk(text: str) -> str:
    """SSE data event con un fragmento de texto."""
    payload = json.dumps({"text": text}, ensure_ascii=False, allow_nan=False)
    return f"data: {payload}\n\n"


def _sse_event(name: str, data: dict) -> str:
    """SSE named event con payload JSON."""
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
    return f"event: {name}\ndata: {payload}\n\n"


def _save_turn_to_engram(
    conv_id: int,
    engram_project: str,
    user_message: str,
    assistant_message: str,
    mentor_name: str,
) -> None:
    """
    Guarda un turn (user msg + assistant msg) como UNA observation en engram,
    en el namespace específico del anoven-project de esta conversación.

    Fail-safe: si engram falla, loguea y sigue — el chat NO se rompe.
    """
    try:
        session_id = session_id_for_conversation(conv_id)
        engram.create_session(session_id, engram_project)

        clean_user = user_message.strip()
        title = (clean_user[:80] + "...") if len(clean_user) > 80 else clean_user
        content = (
            f"[USER]\n{user_message.strip()}\n\n"
            f"[MENTOR — {mentor_name}]\n{assistant_message.strip()}"
        )
        engram.save_observation(
            session_id=session_id,
            project=engram_project,
            title=title,
            content=content,
            obs_type="discovery",
        )
    except Exception:
        logger.exception(
            "engram turn save failed (conv_id=%s, project=%s)",
            conv_id, engram_project,
        )


# ============================================================
# Saludos iniciales — cascade: hardcoded → §2 del CLAUDE.md → generado
# ============================================================

# Overrides hardcoded para casos donde el §2 no sirve (mentores especiales).
_INITIAL_GREETINGS_OVERRIDE: dict[str, str] = {
    "anoven-creador": (
        "Hola. Soy el Creador de Anoven.\n\n"
        "Estoy acá para ayudarte a armar un mentor hecho a tu medida. No es "
        "un formulario — es una charla. Te voy a hacer preguntas para entender "
        "qué oficio querés que tenga ese mentor, qué autores o tradición querés "
        "que use como canon, cómo querés que te hable (formal, cálido, picante, "
        "directo), y qué cosas NO querés que haga.\n\n"
        "Cuando tenga el cuadro claro, armo un primer prototipo y vos validás. "
        "Si te gusta, queda como mentor tuyo en el dashboard.\n\n"
        "Para arrancar: ¿qué área o necesidad te trae acá? ¿Hay algo concreto "
        "que sentís que te falta cubrir con tus mentores actuales, o es un "
        "tema completamente nuevo?"
    ),
}


def _build_initial_greeting(mentor) -> str | None:
    """
    Devuelve el saludo inicial del mentor para una conversación nueva.

    Cascada:
      1. Hardcoded override por slug — para Creador, Entrevistador, especiales.
      2. Extracción del §2 Turn-1 presentation del CLAUDE.md del mentor —
         para los 14 mentores oficiales del catálogo, que ya lo tienen escrito.
      3. Generación a partir de nombre + filosofía — último recurso defensivo.
    """
    # 1. Override
    if mentor.slug in _INITIAL_GREETINGS_OVERRIDE:
        return _INITIAL_GREETINGS_OVERRIDE[mentor.slug]

    # 2. Extraer §2 del CLAUDE.md
    from app.services.mentor_chat import _extract_section
    section_2 = _extract_section(mentor.system_prompt or "", "2")
    if section_2:
        extracted = _parse_turn1_blockquote(section_2)
        if extracted:
            return extracted

    # 3. Fallback genérico
    return (
        f"Hola. Soy {mentor.nombre} de Anoven.\n\n"
        f"{(mentor.filosofia or '').strip()}\n\n"
        "¿Qué tema querés trabajar?"
    ).strip()


def _parse_turn1_blockquote(section_text: str) -> str | None:
    """
    Parsea el contenido en blockquote (lines starting with '>') del §2 y lo
    devuelve como texto plano. Si la sección no tiene blockquotes, devuelve None.
    """
    lines: list[str] = []
    in_quote = False
    for raw in section_text.split("\n"):
        stripped = raw.strip()
        if stripped.startswith(">"):
            # Sacar el '>' y un espacio opcional
            content = stripped[1:].lstrip()
            lines.append(content)
            in_quote = True
        elif in_quote and stripped == "":
            # Línea vacía dentro del blockquote mantiene la separación de párrafos
            lines.append("")
        elif in_quote and not stripped.startswith(">"):
            # Salimos del blockquote — paramos. (Hay texto post-§2 que no es
            # parte del saludo, ej: "Si tema concreto en turn 1: ...")
            break

    if not lines:
        return None

    text = "\n".join(lines).strip()
    return text or None


# Stopwords mínimas para sacar ruido obvio del OR-search.
_SEARCH_STOPWORDS = {
    "que", "lo", "de", "del", "el", "la", "los", "las", "un", "una", "uno",
    "y", "o", "es", "se", "te", "me", "mi", "tu", "su", "por", "para", "con",
    "sin", "en", "ya", "no", "si", "ser", "soy", "sos", "son", "como", "qué",
    "cuál", "donde", "cuando", "porqué", "porque", "hola", "este", "esta",
    "estos", "estas", "ese", "esa", "eso", "muy", "más", "menos", "tan",
    "hay", "hace", "hizo", "tienes", "tiene", "tener", "tengo", "tenes",
    "habla", "hablar", "hablamos", "hablo", "hablás", "voy", "ir", "ver",
}


def _significant_tokens(message: str) -> list[str]:
    """
    Extrae tokens significativos del mensaje del user para hacer multi-search.
    Filtra stopwords y tokens muy cortos. Dedup manteniendo orden de aparición.

    Min length 3 — captura abreviaciones, acrónimos y typos cortos.
    """
    tokens = re.findall(r"\w+", message.lower(), flags=re.UNICODE)
    seen: set = set()
    out: list[str] = []
    for t in tokens:
        if len(t) < 3 or t in _SEARCH_STOPWORDS or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _format_memory_block(memories: list[dict]) -> str:
    """
    Arma un bloque de texto con las memorias relevantes para inyectar al
    system_prompt. Si no hay memorias, devuelve string vacío (no se inyecta).
    """
    if not memories:
        return ""

    lines = [
        "═══════════════════════════════════════════════════════",
        "MEMORIA DE CONVERSACIONES PREVIAS (mismo project del user)",
        "═══════════════════════════════════════════════════════",
        "",
        "Estas son cosas que el user ya te contó (o le contó a otros mentores",
        "de Anoven) en charlas anteriores DENTRO DEL MISMO PROYECTO. Usalas",
        "para anclar tu respuesta — NO le pidas que repita información que",
        "está acá. Cuando referencies, hacelo natural:",
        "",
        '  "como mencionaste antes, X..."',
        '  "siguiendo el tema del café boutique que charlaste..."',
        "",
        "Las memorias están ordenadas por relevancia al mensaje actual:",
        "",
    ]
    for i, mem in enumerate(memories, 1):
        title = mem.get("title", "(sin título)")
        content = mem.get("content", "").strip()
        lines.append(f"### Memoria {i} — {title}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)
