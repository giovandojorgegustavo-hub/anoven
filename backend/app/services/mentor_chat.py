"""
mentor_chat — cliente de streaming + builder del system_prompt envuelto.

Sesión 3.3: el system_prompt que mandamos a Anthropic NO es el CLAUDE.md
crudo. Lo envolvemos con:

  1) Bloque PRIMARIO con voz, canon, filosofía, anti-patrones explícitos
     (parseados de §1 y §5 del CLAUDE.md).
  2) Bloque CONTEXTO DEL CHAT: reglas específicas de anoven-app
     (no skills, no engram, no turn-1, no handoffs).
  3) CLAUDE.md COMPLETO como referencia secundaria.

Por qué duplicar el contenido (extraído arriba + completo abajo): el LLM
da más peso a lo que aparece al INICIO del system_prompt y a lo que se
REPITE. El user quiso "más preciso lo que es Anoven" — esto le da
prioridad explícita a voz/canon/filosofía/anti-patrones por sobre el
resto del documento.

Iteración futura (Sesión 3.5+): después de analizar conversaciones reales,
curamos qué sacar de los CLAUDE.md (engram protocol, skills, etc.) para
que la referencia secundaria también esté limpia.
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Callable, Iterator, Optional
from zoneinfo import ZoneInfo

from anthropic import Anthropic

from app.config import settings
from app.models.mentor import Mentor
from app.services.context_window import estimate_tokens, trim_history


_client = Anthropic(api_key=settings.anthropic_api_key)


# Timezone de los users — todos en Perú por ahora.
# Si en algún momento hay users fuera de Perú, esto pasa a venir del frontend
# (Intl.DateTimeFormat().resolvedOptions().timeZone) en cada request.
_USER_TZ = ZoneInfo("America/Lima")

_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_actual_local() -> str:
    """Devuelve la fecha actual en Lima formateada en español para inyectar al LLM."""
    now = datetime.now(_USER_TZ)
    dia_semana = _DIAS_ES[now.weekday()]
    mes = _MESES_ES[now.month - 1]
    return f"{dia_semana} {now.day} de {mes} de {now.year}, {now.strftime('%H:%M')} hora de Lima"


# ============================================================
# Parser de secciones del CLAUDE.md
# ============================================================
#
# Las secciones tienen formato:  "## §N — Titulo"
# El parser busca §N específico y devuelve todo hasta el próximo "## §".
# ============================================================

_SECTION_HEADER_RE = re.compile(
    r"^##\s*§(\d+(?:\.\d+)?)\s*[—\-–][^\n]*$",
    re.MULTILINE,
)


def _extract_section(text: str, num: str) -> str:
    """
    Devuelve el contenido de `## §{num} — ...` excluyendo la línea del header.
    Si no encuentra la sección, devuelve string vacío.
    """
    matches = list(_SECTION_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1) == num:
            content_start = m.end()
            content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[content_start:content_end].strip()
    return ""


# Secciones del CLAUDE.md que NO queremos en el chat web (provocan ruido tipo
# "no hay engram cargado" o "Turn-1 presentation" en cada mensaje).
_SECTIONS_TO_STRIP = {"2", "8"}  # §2 Turn-1, §8 Engram protocol


def _strip_sections(text: str, sections_to_remove: set[str]) -> str:
    """
    Borra del CLAUDE.md las secciones especificadas (por número).
    Mantiene el resto intacto.
    """
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return text

    spans_to_remove: list[tuple[int, int]] = []
    for i, m in enumerate(matches):
        if m.group(1) in sections_to_remove:
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            spans_to_remove.append((start, end))

    if not spans_to_remove:
        return text

    # Recortamos los spans en orden inverso para no romper los índices.
    out = text
    for start, end in reversed(spans_to_remove):
        out = out[:start] + out[end:]
    return out


# ============================================================
# Builder del system_prompt envuelto
# ============================================================

CREATOR_MARKER_INSTRUCTIONS = """\
═══════════════════════════════════════════════════════
INSTRUCCIONES ESPECIALES (solo para el Creador)
═══════════════════════════════════════════════════════

Cuando creas que ya tenés información suficiente para que el sistema arme
el mentor custom (oficio claro, alguna pista de canon o tradición, idea
de voz), cerrá tu respuesta con UNA frase corta de despedida + el marker
EXACTO al final:

    "Listo, dejame armar el primer prototipo. [PROTOTYPE_READY]"

El marker `[PROTOTYPE_READY]` es OBLIGATORIO y va una sola vez al final.
Después de emitirlo, el sistema corre Promptifex en backstage y arma el
mentor draft. NO digas nada después del marker.

# Cuándo emitirlo
- Tenés AREA / OFICIO del mentor identificado.
- Tenés alguna pista del CANON (autores, tradición, o nada explícito pero
  el dominio es estándar).
- Sabés cómo querés que SUENE (formal, cálido, directo, etc.) — esto
  podés inferirlo del propio user.

# Cuándo NO emitirlo todavía
- El user te dijo solo "quiero un mentor de X" sin profundizar — pedile
  ejemplos concretos de cómo lo usaría.
- Te falta saber qué NO querría del mentor.

Recomendación: entre el turn 3 y el turn 6 del user. No exageres pidiendo
diez detalles — el user puede iterar después en el admin si quiere.\
"""



CHAT_CONTEXT_RULES = """\
Estás conversando con un user dentro de la app web de Anoven.

# REGLAS CRÍTICAS DE LENGUAJE (release-blockers)

NUNCA, JAMÁS le menciones al user los siguientes términos técnicos. Son
infraestructura interna de Anoven y al user le sonarían a jerga rota:

  - "engram" (sistema de memoria — usá "lo que charlamos antes")
  - "skill", "skills", "mem_save", "mem_search", "MCP", "ADR", "eval suite"
  - "Turn-1 presentation", "architectural debt", "context window"
  - "CLAUDE.md", "vertical", "Gentleman X" (cuando refieras a otros mentores
    decí simplemente "el mentor de Marketing" o el nombre del vertical sin
    el prefijo Gentleman)

Si tu CLAUDE.md interno menciona algo de esto, PARÁ y NO lo verbalices.

# QUÉ HACER CON LA MEMORIA

Más abajo puede aparecer una sección "MEMORIA DE CONVERSACIONES PREVIAS"
con fragmentos de charlas previas del user. Si aparece:

  ✅ USALA como contexto válido. El user te contó esa info antes y querés
     que la recuerdes.
  ✅ Si referencias, hacelo natural: "lo que mencionaste antes", "ya hablamos
     de X", "como te conté", etc.
  ❌ NUNCA digas "no tengo memoria" o "no recuerdo" si la sección está poblada.
  ❌ NUNCA expliques cómo Anoven hace memoria internamente.

Si la sección "MEMORIA DE CONVERSACIONES PREVIAS" NO aparece o está vacía:
es la primera conversación con este user sobre este tema. Arrancá fresh
con curiosidad, sin verbalizar nada técnico sobre el sistema.

# OTRAS REGLAS DE CONTEXTO

- NO te presentes con tu Turn-1 presentation (rol + canon + handoffs largo).
  La app ya muestra tu identidad en el header del chat. Arrancá directo
  al problema del user.
- NO sugieras al user "andate con otro mentor" — ya tiene su equipo asignado
  por el MentorMatcher de Anoven. Si el tema cruza, podés mencionar de pasada
  que "lo profundo de Y se trabaja con Marketing" sin redirigirlo.

Todo lo demás de tu definición (voz, canon, filosofía, anti-patrones, voseo,
verify-before-agree, refusal de seguridad) sigue valiendo al 100%.\
"""


def build_system_blocks(
    mentor: Mentor,
    memory_block: str = "",
    rules_block: str = "",
    skills_block: str = "",
) -> tuple[str, str]:
    """
    Arma el system_prompt como DOS bloques separados para Anthropic prompt caching.

    Devuelve (static_part, dynamic_part):

    - **static_part**: idéntico para todos los users que charlen con el mismo
      mentor. Cacheable con `cache_control: ephemeral` → 90% descuento en
      input tokens cuando se reutiliza dentro de 5 min.
      Contiene: identidad, voz, canon, filosofía, anti-patrones, CLAUDE.md
      podado, reglas chat, y marker especial del Creador.

    - **dynamic_part**: cambia por user/sesión. NO cacheable.
      Contiene: rules_block del user, memory_block del project, RECORDATORIO
      FINAL — todo lo último que ve el modelo para mantener recency bias.
    """
    voz_y_oficio = _extract_section(mentor.system_prompt, "1") or (
        "(ver tu definición más abajo, §1)"
    )
    anti_patrones = _extract_section(mentor.system_prompt, "5") or (
        "(ver tu definición más abajo, §5)"
    )

    pruned_claude_md = _strip_sections(mentor.system_prompt, _SECTIONS_TO_STRIP)

    # ---- STATIC (cacheable) ----
    static_parts = [
        f"Sos {mentor.nombre}, mentor de Anoven.",
        "",
        "═══════════════════════════════════════════════════════",
        "QUIÉN SOS (ancla rápida)",
        "═══════════════════════════════════════════════════════",
        "",
        "## VOZ Y OFICIO",
        voz_y_oficio,
        "",
        "## CANON",
        mentor.canon,
        "",
        "## FILOSOFÍA",
        mentor.filosofia,
        "",
        "## ANTI-PATRONES",
        anti_patrones,
        "",
        "═══════════════════════════════════════════════════════",
        "DEFINICIÓN COMPLETA (referencia — sin §2 ni §8 por contexto web)",
        "═══════════════════════════════════════════════════════",
        "",
        pruned_claude_md,
        "",
        "═══════════════════════════════════════════════════════",
        "REGLAS DEL CHAT EN ANOVEN (PRIORIDAD MÁXIMA — release-blockers)",
        "═══════════════════════════════════════════════════════",
        "",
        CHAT_CONTEXT_RULES,
    ]

    if mentor.slug == "anoven-creador":
        static_parts.extend(["", CREATOR_MARKER_INSTRUCTIONS])

    # ---- DYNAMIC (no cacheable) ----
    dynamic_parts = [
        "═══════════════════════════════════════════════════════",
        "FECHA Y HORA ACTUAL",
        "═══════════════════════════════════════════════════════",
        "",
        f"Hoy es {_fecha_actual_local()}.",
        "Si el user menciona fechas pasadas o futuras (\"el miércoles\", \"hace 3 días\","
        " \"el mes que viene\"), calculá SIEMPRE relativo a esta fecha actual.",
        "NUNCA inventes el día de la semana ni la fecha — usá únicamente la de arriba.",
        "",
    ]

    if rules_block:
        dynamic_parts.extend([rules_block, ""])

    if skills_block:
        dynamic_parts.extend([skills_block, ""])

    if memory_block:
        dynamic_parts.extend([memory_block, ""])

    dynamic_parts.extend([
        "═══════════════════════════════════════════════════════",
        "RECORDATORIO FINAL (releélo antes de responder)",
        "═══════════════════════════════════════════════════════",
        "",
        "Si arriba aparece una sección MEMORIA DE CONVERSACIONES PREVIAS,",
        "el user YA TE CONTÓ esa info. NO digas 'no recuerdo' ni 'no tengo",
        "contexto'. Usá esos datos como tuyos. Si no aparece esa sección,",
        "es la primera vez que hablás de este tema — empezá con curiosidad,",
        "sin verbalizar nada sobre cómo Anoven hace memoria.",
        "",
        "NUNCA verbalices al user: 'engram', 'mem_save', 'skill', 'MCP',",
        "'CLAUDE.md', 'vertical', 'eval suite', 'ADR'. Son términos internos.",
    ])

    return "\n".join(static_parts), "\n".join(dynamic_parts)


def build_system_prompt(
    mentor: Mentor,
    memory_block: str = "",
    rules_block: str = "",
    skills_block: str = "",
) -> str:
    """
    Wrapper retro-compatible que concatena static + dynamic en un solo string.
    Se mantiene para que tests viejos sigan funcionando. El call real a
    Anthropic usa `build_system_blocks` directamente para aprovechar el cache.
    """
    static_part, dynamic_part = build_system_blocks(
        mentor,
        memory_block=memory_block,
        rules_block=rules_block,
        skills_block=skills_block,
    )
    return static_part + "\n\n" + dynamic_part


# ============================================================
# Cliente Anthropic
# ============================================================


def _utcnow_iso() -> str:
    """UTC timestamp in ISO 8601 format for SSE event payloads."""
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()


# Type alias for stream events: (event_type, payload)
# event_type: "text" | "tool_started" | "tool_completed" | "tool_failed" |
#             "tool_cap_reached" | "iteration_started"
StreamEvent = tuple[str, Any]

# Maximum tool turns per user turn (agentic loop cap)
_MAX_TOOL_TURNS = 5


def stream_mentor_reply(
    mentor: Mentor,
    history: list[dict],
    memory_block: str = "",
    rules_block: str = "",
    skills_block: str = "",
    on_usage=None,
    on_context_status: Optional[Callable[[dict], None]] = None,
    tool_context=None,   # ToolContext | None — required for agentic path
    conversation_tool_budget: dict | None = None,  # per-conversation counters
    model: str | None = None,  # sdd/per-mentor-model-assignment-v1: resolved upstream
) -> Iterator[StreamEvent]:
    """
    Llama a Claude en streaming con el system_prompt ENVUELTO + historia
    + (opcionales) memoria + reglas del user inyectadas.

    Yields StreamEvent tuples: (event_type, payload).

    For the legacy path (mentor.allowed_tools empty):
      - Yields only ("text", str_chunk) events — identical SSE output to before.

    For the agentic path (mentor.allowed_tools non-empty):
      - Yields ("text", str), ("tool_started", dict), ("tool_completed", dict),
        ("tool_failed", dict), ("tool_cap_reached", dict) events.
      - The agentic loop runs synchronously via asyncio.run() since the caller
        is a sync generator inside conversation_service.py.

    `history`: [{"role": "user"|"assistant", "content": str | list[dict]}, ...]
    `memory_block`: Sesión 4.4 — memorias previas del project.
    `rules_block`: Sesión 4.5 — reglas activas del user.
    `skills_block`: Fase 1 — skills habilitadas del mentor para inyectar.
    `on_usage`: callback optional — receives accumulated usage dict at end of turn.
    `on_context_status`: callback optional invocado ANTES de abrir el stream.
    `tool_context`: ToolContext for agentic path (None = legacy).
    `conversation_tool_budget`: mutable dict for per-conversation rate limits.
    """
    from app.services.tool_registry import tools_for_mentor

    static_part, dynamic_part = build_system_blocks(
        mentor,
        memory_block=memory_block,
        rules_block=rules_block,
        skills_block=skills_block,
    )

    # --- Context window management (ADR-1: policy in service, not route) ---
    budget = settings.context_max_tokens - settings.context_output_reserved
    tokens_total = sum(
        4 + estimate_tokens(m.get("content", "")) for m in history
    )
    utilization = tokens_total / budget if budget > 0 else 0.0

    working_history = history
    if utilization >= settings.context_compact_threshold:
        trimmed, status = trim_history(
            history, settings.context_max_tokens, settings.context_output_reserved
        )
        working_history = trimmed
        if on_context_status is not None:
            on_context_status(status)
    elif utilization >= settings.context_warning_threshold:
        if on_context_status is not None:
            on_context_status({
                "was_trimmed": False,
                "dropped_count": 0,
                "tokens_before": tokens_total,
                "tokens_after": tokens_total,
                "utilization_before": utilization,
                "utilization_after": utilization,
            })

    # System como lista de bloques: el static lleva `cache_control: ephemeral`
    system_blocks = [
        {
            "type": "text",
            "text": static_part,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": dynamic_part,
        },
    ]

    # ─── Branch: LEGACY vs AGENTIC ──────────────────────────────────────────
    allowed_tools = tools_for_mentor(mentor)

    if not allowed_tools:
        # ═══════════════════════════════════════════════════════════════════
        # LEGACY PATH — UNCHANGED from Batch 1 behavior.
        # Creador, every mentor with allowed_tools=[] takes this branch.
        # Yields ("text", chunk) events — identical SSE behavior to before.
        # ═══════════════════════════════════════════════════════════════════
        # sdd/per-mentor-model-assignment-v1: prefer caller-resolved model,
        # fall back to system default only if caller didn't resolve (e.g. tests).
        _effective_model = model or settings.default_model
        with _client.messages.stream(
            model=_effective_model,
            max_tokens=2048,
            system=system_blocks,
            messages=working_history,
        ) as stream:
            for chunk in stream.text_stream:
                yield ("text", chunk)
            # Capturamos usage para tracking.
            if on_usage is not None:
                try:
                    final = stream.get_final_message()
                    # Build usage dict compatible with agentic accumulator format
                    usage = final.usage
                    on_usage({
                        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    })
                except Exception:
                    pass
        return

    # ═══════════════════════════════════════════════════════════════════════
    # AGENTIC PATH — Phase 2 loop.
    # Only mentors with non-empty allowed_tools reach here.
    # Runs the async agentic loop synchronously via asyncio.run().
    # ═══════════════════════════════════════════════════════════════════════

    # Collect events from async loop then yield them synchronously
    # (sync generator cannot directly await — we run the coroutine to completion
    # per iteration step via an event queue pattern)
    import queue as _queue

    _event_queue: _queue.Queue = _queue.Queue()
    _SENTINEL = object()

    async def _agentic_loop() -> None:
        from app.services.tool_dispatcher import ToolBudget, dispatch_tool

        turn_messages = list(working_history)
        per_conv_budget = conversation_tool_budget if conversation_tool_budget is not None else {}
        budget_obj = ToolBudget(
            per_turn={},
            per_conversation=per_conv_budget,
        )
        accumulated_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        consecutive_failures = 0

        for iteration in range(_MAX_TOOL_TURNS + 1):
            pending_tool_uses = []

            # sdd/per-mentor-model-assignment-v1: same _effective_model as legacy path
            _effective_model_agentic = model or settings.default_model
            with _client.messages.stream(
                model=_effective_model_agentic,
                max_tokens=2048,
                system=system_blocks,
                messages=turn_messages,
                tools=allowed_tools,
            ) as stream:
                for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and hasattr(event, "delta")
                        and getattr(event.delta, "type", None) == "text_delta"
                    ):
                        _event_queue.put(("text", event.delta.text))
                    elif (
                        event.type == "content_block_start"
                        and hasattr(event, "content_block")
                        and getattr(event.content_block, "type", None) == "tool_use"
                    ):
                        cb = event.content_block
                        _event_queue.put(("tool_started", {
                            "tool_id": cb.id,
                            "tool": cb.name,
                            "input_preview": "",  # filled after final message
                            "iteration": iteration,
                            "started_at": _utcnow_iso(),
                        }))
                    # Phase 3: server-side tool blocks (web_search_20250305).
                    # Anthropic emits server_tool_use for web_search; emit SSE events
                    # so frontend shows ToolActivityPill (A2.2, design para4.5).
                    elif (
                        event.type == "content_block_start"
                        and hasattr(event, "content_block")
                        and getattr(event.content_block, "type", None) == "server_tool_use"
                    ):
                        cb = event.content_block
                        if getattr(cb, "name", None) == "web_search":
                            _event_queue.put(("tool_started", {
                                "tool_id": cb.id,
                                "tool": "web_search",
                                "input_preview": "",
                                "iteration": iteration,
                                "started_at": _utcnow_iso(),
                                "server_side": True,
                            }))
                    elif (
                        event.type == "content_block_start"
                        and hasattr(event, "content_block")
                        and getattr(event.content_block, "type", None) == "web_search_tool_result"
                    ):
                        cb = event.content_block
                        _event_queue.put(("tool_completed", {
                            "tool_use_id": getattr(cb, "tool_use_id", ""),
                            "tool": "web_search",
                            "status": "ok",
                            "result_preview": "Busqueda completada",
                            "duration_ms": 0,
                            "server_side": True,
                        }))
                final = stream.get_final_message()

            # Accumulate usage (ADR-6)
            if final.usage:
                for k in accumulated_usage:
                    accumulated_usage[k] += getattr(final.usage, k, 0) or 0

            # Collect tool_use blocks
            pending_tool_uses = [
                b for b in final.content
                if hasattr(b, "type") and b.type == "tool_use"
            ]

            if final.stop_reason != "tool_use" or not pending_tool_uses:
                break  # Normal text completion — done

            # Append assistant message (text + tool_use blocks)
            turn_messages.append({"role": "assistant", "content": final.content})

            # Dispatch each tool, collect results
            tool_result_blocks = []
            for block in pending_tool_uses:
                result = await dispatch_tool(
                    block=block,
                    mentor=mentor,
                    context=tool_context,
                    budget=budget_obj,
                )
                # Phase 3: None return means server-side tool (e.g. web_search).
                # Anthropic handled it internally; no tool_result to append.
                if result is None:
                    continue
                if result["status"] == "ok":
                    consecutive_failures = 0
                    _event_queue.put(("tool_completed", {
                        "tool_id": result["tool_use_id"],
                        "tool": result["tool_name"],
                        "tool_name": result["tool_name"],
                        "status": "ok",
                        "result_preview": result.get("result_preview") or "",
                        "duration_ms": result["duration_ms"],
                        "content": result.get("content", ""),
                    }))
                else:
                    consecutive_failures += 1
                    _event_queue.put(("tool_failed", {
                        "tool_id": result["tool_use_id"],
                        "tool": result["tool_name"],
                        "error": result.get("error") or result["status"],
                        "duration_ms": result["duration_ms"],
                    }))

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": result["tool_use_id"],
                    "content": result["content"],
                    "is_error": result["status"] != "ok",
                })

            turn_messages.append({"role": "user", "content": tool_result_blocks})

            if consecutive_failures >= 3:
                _event_queue.put(("tool_cap_reached", {
                    "reason": "consecutive_failures",
                    "max_uses": _MAX_TOOL_TURNS,
                }))
                break
        else:
            # Loop exhausted MAX_TOOL_TURNS without natural exit
            _event_queue.put(("tool_cap_reached", {
                "reason": "max_turns",
                "limit": _MAX_TOOL_TURNS,
                "max_uses": _MAX_TOOL_TURNS,
            }))

        # Emit accumulated usage
        if on_usage is not None:
            try:
                on_usage(accumulated_usage)
            except Exception:
                pass

        _event_queue.put(_SENTINEL)

    import threading as _threading

    def _run_loop() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_agentic_loop())
        finally:
            loop.close()

    t = _threading.Thread(target=_run_loop, daemon=True)
    t.start()

    while True:
        evt = _event_queue.get()
        if evt is _SENTINEL:
            break
        yield evt

    t.join(timeout=30)