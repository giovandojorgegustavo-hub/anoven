"""
Tool Dispatcher — Phase 2 of mentor-tools-system SDD cycle.

Dispatches tool_use blocks from the LLM to registered handlers.

Key invariants:
- NEVER raises — every failure mode maps to a structured result dict.
  The LLM always gets a tool_result (even on error/timeout/rate_limit).
- Sync handlers are wrapped via asyncio.to_thread so timeouts fire correctly.
- ToolBudget tracks per-turn + per-conversation invocation counts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

logger = logging.getLogger(__name__)


# ─── Context ────────────────────────────────────────────────────────────────

@dataclass
class ToolContext:
    """
    Context passed to every tool handler.
    Carries the engram project namespace, client reference, and conversation ID.
    """
    engram_project: str         # e.g. "anoven-app-user-3-mi-cafe"
    engram_session_id: str      # conversation-level session ID
    conversation_id: int
    user_id: int
    db: object | None = None    # SQLAlchemy Session — needed by tools that write to DB (generate_image)


# ─── Budget ─────────────────────────────────────────────────────────────────

@dataclass
class ToolBudget:
    """
    Per-turn + per-conversation counters.

    per_conversation_state is passed by reference and mutated in-place so
    usage persists across turns within the same generator lifecycle.
    """
    per_turn: dict[str, int] = field(default_factory=dict)
    per_conversation: dict[str, int] = field(default_factory=dict)


# ─── Result ──────────────────────────────────────────────────────────────────

class ToolDispatchResult(TypedDict):
    tool_use_id: str
    tool_name: str
    status: Literal["ok", "error", "timeout", "rate_limited", "not_authorized"]
    content: str            # JSON-stringified result body — sent to LLM as tool_result content
    duration_ms: int
    error: str | None       # human-readable error (for SSE events)
    result_preview: str | None  # short human-readable summary for SSE event


# ─── Helpers ────────────────────────────────────────────────────────────────

def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 1] + "…"


def _make_result(
    tool_use_id: str,
    tool_name: str,
    status: str,
    body: dict,
    started: float,
    *,
    preview: str | None = None,
) -> ToolDispatchResult:
    duration_ms = int((time.monotonic() - started) * 1000)
    error_msg = body.get("error") if status != "ok" else None
    return ToolDispatchResult(
        tool_use_id=tool_use_id,
        tool_name=tool_name,
        status=status,
        content=json.dumps(body, ensure_ascii=False),
        duration_ms=duration_ms,
        error=_truncate(str(error_msg), 240) if error_msg else None,
        result_preview=preview,
    )


def _summarize_result(tool_name: str, result_body: dict) -> str:
    """Build a short human-readable preview for the SSE tool_completed event."""
    if tool_name == "mem_search":
        count = result_body.get("count", 0)
        return f"{count} observación{'es' if count != 1 else ''} encontrada{'s' if count != 1 else ''}"
    if tool_name == "mem_save":
        if result_body.get("success"):
            return f"Insight guardado (id={result_body.get('id', '?')})"
        return f"No guardado: {result_body.get('reason', 'error')}"
    return "ok"


# ─── Dispatcher ─────────────────────────────────────────────────────────────

async def dispatch_tool(
    block: Any,             # anthropic.types.ToolUseBlock
    mentor: Any,            # app.models.mentor.Mentor
    context: ToolContext,
    budget: ToolBudget,
) -> ToolDispatchResult:
    """
    Dispatch one tool_use block to its handler.

    Returns a ToolDispatchResult in ALL cases — never raises.
    The `content` field is the JSON string to pass as tool_result to the LLM.
    """
    from app.services.tool_registry import get_registry

    started = time.monotonic()
    name = block.name
    tool_use_id = block.id
    registry = get_registry()
    tool_def = registry.get(name)

    # ── Phase 3: server-side tool guard ─────────────────────────────────────
    # Server-side tools (e.g. web_search) execute inside Anthropic; we should
    # never reach dispatch for them. If we do (defensive), no-op without raising.
    # C5.2: dispatcher NEVER raises; return None and caller skips tool_result.
    if tool_def is not None and tool_def.server_side:
        logger.warning(
            "server_side_tool_unexpectedly_dispatched",
            extra={"tool": name, "mentor": mentor.slug},
        )
        return None

    # ── Authorization check ──────────────────────────────────────────────────
    if tool_def is None or name not in (mentor.allowed_tools or []):
        logger.warning(
            "tool_not_authorized",
            extra={"tool": name, "mentor": mentor.slug, "allowed": mentor.allowed_tools},
        )
        return _make_result(
            tool_use_id, name, "not_authorized",
            {"error": f"tool '{name}' not authorized for this mentor"},
            started,
        )

    # ── Per-turn rate limit ──────────────────────────────────────────────────
    if tool_def.rate_limit_per_turn is not None:
        if budget.per_turn.get(name, 0) >= tool_def.rate_limit_per_turn:
            return _make_result(
                tool_use_id, name, "rate_limited",
                {"error": "rate_limited", "scope": "turn",
                 "limit": tool_def.rate_limit_per_turn},
                started,
            )

    # ── Per-conversation rate limit ──────────────────────────────────────────
    if tool_def.rate_limit_per_conversation is not None:
        if budget.per_conversation.get(name, 0) >= tool_def.rate_limit_per_conversation:
            return _make_result(
                tool_use_id, name, "rate_limited",
                {"error": "rate_limited", "scope": "conversation",
                 "limit": tool_def.rate_limit_per_conversation},
                started,
            )

    # ── Execute with timeout ─────────────────────────────────────────────────
    validated_input = block.input or {}
    try:
        coro = tool_def.handler(
            input=validated_input,
            mentor=mentor,
            context=context,
        )
        if not asyncio.iscoroutine(coro):
            # Sync handler — wrap via to_thread so asyncio.wait_for fires correctly
            coro = asyncio.to_thread(
                lambda: tool_def.handler(
                    input=validated_input,
                    mentor=mentor,
                    context=context,
                )
            )
        result_body = await asyncio.wait_for(coro, timeout=tool_def.timeout_seconds)

    except asyncio.TimeoutError:
        logger.warning(
            "tool_timeout",
            extra={"tool": name, "mentor": mentor.slug,
                   "timeout": tool_def.timeout_seconds},
        )
        return _make_result(
            tool_use_id, name, "timeout",
            {"error": "timeout", "tool": name,
             "limit_seconds": tool_def.timeout_seconds},
            started,
        )
    except Exception as exc:
        logger.exception(
            "tool_handler_error",
            extra={"tool": name, "mentor": mentor.slug},
        )
        return _make_result(
            tool_use_id, name, "error",
            {"error": _truncate(str(exc), 240)},
            started,
        )

    # ── Success — increment budgets ──────────────────────────────────────────
    budget.per_turn[name] = budget.per_turn.get(name, 0) + 1
    budget.per_conversation[name] = budget.per_conversation.get(name, 0) + 1

    preview = _summarize_result(name, result_body)
    return _make_result(
        tool_use_id, name, "ok",
        result_body,
        started,
        preview=preview,
    )
