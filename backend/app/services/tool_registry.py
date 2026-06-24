"""
Tool Registry -- Phase 2 of mentor-tools-system SDD cycle.

Central registry of all tools available in the agentic loop.
Each entry maps a slug -> ToolDefinition (Anthropic schema + handler ref).

tools_for_mentor(mentor) -> list of Anthropic-shaped dicts for only the tools
the mentor is allowed to use (filtered by mentor.allowed_tools).

Handlers are imported lazily at the bottom to avoid circular imports.

Phase 3 (skills-platform-with-telemetry): added server_side + anthropic_schema
fields to ToolDefinition for web_search_20250305 server-side tool support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolDefinition:
    """A tool the LLM can call, backed by a sync or async handler."""
    name: str                               # canonical slug -- matches DB allowed_tools entry
    description: str                        # sent to Anthropic (empty for server-side tools)
    input_schema: dict                      # JSON schema for tool input (empty for server-side)
    handler: Callable[..., Any] | None      # sync or async -- None for server-side tools
    timeout_seconds: float = 1.5            # per-invocation timeout (N/A for server-side)
    rate_limit_per_turn: int | None = None  # None = unlimited
    rate_limit_per_conversation: int | None = None
    # Phase 3 (skills-platform-with-telemetry): server-side tool support
    # When True, Anthropic executes the tool; we never dispatch it locally (ADR-4).
    server_side: bool = False
    # Anthropic-native schema dict for server-side tools (e.g. web_search_20250305).
    # For client-side tools this is None; tools_for_mentor() uses name/description/input_schema.
    anthropic_schema: dict | None = None


# Forward refs -- filled after imports below
_REGISTRY_DATA: dict[str, dict] = {
    "mem_search": {
        "description": (
            "Buscá en la memoria persistente del usuario (engram). "
            "Usalo cuando necesites contexto sobre proyectos previos, decisiones, "
            "o preferencias que el usuario haya mencionado en sesiones anteriores. "
            "NO lo uses para conocimiento general -- solo para datos del usuario. "
            "No repitas la misma búsqueda más de una vez por turno."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Palabras clave o frase natural para buscar en memoria",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                    "description": "Número máximo de resultados (1-10, default 5)",
                },
            },
            "required": ["query"],
        },
        "timeout_seconds": 1.5,
        "rate_limit_per_turn": None,
        "rate_limit_per_conversation": None,
    },
    "generate_image": {
        "description": (
            "Generá una imagen a partir de un prompt en lenguaje natural. "
            "Usalo cuando el usuario pida explícitamente crear, generar, o mostrar "
            "una foto, imagen, mockup, render, ilustración, o composición visual. "
            "El prompt SIEMPRE en INGLÉS -- Gemini funciona mejor en inglés. "
            "Incluí sujeto, estilo, iluminación, fondo y mood. "
            "Usalo UNA SOLA VEZ por respuesta, al final."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed visual description in English",
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "ultra"],
                    "description": (
                        "standard = imagen-4 generate (default, calidad editorial). "
                        "ultra = imagen-4 ultra (top calidad, hero shots). "
                        "Usá ultra SOLO si el user pide máxima calidad / hero shot / campaña final."
                    ),
                },
            },
            "required": ["prompt"],
        },
        "timeout_seconds": 30.0,
        "rate_limit_per_turn": None,
        "rate_limit_per_conversation": None,
    },
    "mem_save": {
        "description": (
            "Guardá una observación importante en la memoria persistente del usuario. "
            "Usalo SOLO para preferencias claras, decisiones firmes, o user-facts "
            "no triviales que probablemente quieras recordar en sesiones futuras. "
            "NO lo uses para trivia de la conversación actual ni para greetings. "
            "MÁXIMO 1 uso por turno, 3 por conversación total."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título corto y buscable (4-160 chars)",
                    "minLength": 4,
                    "maxLength": 160,
                },
                "content": {
                    "type": "string",
                    "description": "Contenido de la observación (10-4000 chars)",
                    "minLength": 10,
                    "maxLength": 4000,
                },
                "type": {
                    "type": "string",
                    "enum": ["decision", "preference", "user-fact", "discovery"],
                    "default": "user-fact",
                    "description": "Tipo semántico de la observación",
                },
            },
            "required": ["title", "content"],
        },
        "timeout_seconds": 2.0,
        "rate_limit_per_turn": 1,
        "rate_limit_per_conversation": 3,
    },
}


def _build_registry() -> dict[str, ToolDefinition]:
    """Build TOOL_REGISTRY after handler imports resolve."""
    from app.services.tool_handlers import handle_mem_search, handle_generate_image, handle_mem_save
    return {
        "mem_search": ToolDefinition(
            name="mem_search",
            description=_REGISTRY_DATA["mem_search"]["description"],
            input_schema=_REGISTRY_DATA["mem_search"]["input_schema"],
            handler=handle_mem_search,
            timeout_seconds=1.5,
        ),
        "generate_image": ToolDefinition(
            name="generate_image",
            description=_REGISTRY_DATA["generate_image"]["description"],
            input_schema=_REGISTRY_DATA["generate_image"]["input_schema"],
            handler=handle_generate_image,
            timeout_seconds=30.0,
        ),
        "mem_save": ToolDefinition(
            name="mem_save",
            description=_REGISTRY_DATA["mem_save"]["description"],
            input_schema=_REGISTRY_DATA["mem_save"]["input_schema"],
            handler=handle_mem_save,
            timeout_seconds=2.0,
            rate_limit_per_turn=1,
            rate_limit_per_conversation=3,
        ),
        # Phase 3: web_search server-side tool (web_search_20250305).
        # server_side=True means Anthropic executes this; we never dispatch locally.
        # max_uses=5 enforces X6.2 (rate limit on cost-bearing tool).
        "web_search": ToolDefinition(
            name="web_search",
            description="",          # Anthropic provides built-in description
            input_schema={},          # Anthropic provides built-in schema
            handler=None,             # Server-side — no Python handler
            timeout_seconds=0.0,      # N/A — Anthropic enforces timeout
            rate_limit_per_turn=None, # Anthropic enforces via max_uses
            rate_limit_per_conversation=None,
            server_side=True,
            anthropic_schema={
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5,        # X6.2: rate limit at registration time
            },
        ),
    }


# Lazy singleton -- built on first access
_TOOL_REGISTRY: dict[str, ToolDefinition] | None = None


def get_registry() -> dict[str, ToolDefinition]:
    """Return the tool registry, building it on first call."""
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is None:
        _TOOL_REGISTRY = _build_registry()
    return _TOOL_REGISTRY


def tools_for_mentor(mentor) -> list[dict]:
    """
    Return Anthropic-shaped tool dicts for the tools this mentor is allowed to use.
    Empty list if mentor.allowed_tools is [] or None.

    Phase 3: server-side tools (server_side=True) return their anthropic_schema dict
    directly; client-side tools return the standard {name, description, input_schema} shape.
    This allows mixing server-side (web_search) and client-side (mem_search, mem_save, etc.)
    tools in the same Anthropic API call.
    """
    allowed = set(mentor.allowed_tools or [])
    if not allowed:
        return []
    registry = get_registry()
    result = []
    for slug, td in registry.items():
        if slug not in allowed:
            continue
        if td.server_side and td.anthropic_schema is not None:
            # Server-side tool: return the Anthropic-native schema dict
            result.append(td.anthropic_schema)
        else:
            # Client-side tool: return standard Anthropic tool shape
            result.append({
                "name": td.name,
                "description": td.description,
                "input_schema": td.input_schema,
            })
    return result
