"""
ContextBuilder — Port (interfaz) para estrategias de construcción de contexto.

Alistair Cockburn — Hexagonal Architecture, 2005:
  Port = contrato entre el dominio y sus adapters. Las dos estrategias
  (Individual y SharedProject) son adapters intercambiables sin modificar
  los callers (conversation_service.py).

Kent Beck — TDD By Example, 2002:
  Protocol (structural subtyping) es más testable que ABC porque no
  requiere herencia — los tests pueden proveer fakes sin subclassing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ContextBuilder(Protocol):
    """
    Contrato de construcción de contexto de conversación para el API de Anthropic.

    build() recibe los parámetros de la conversación y devuelve:
      - messages: lista de dicts {role, content} listos para Anthropic
      - status: metadata del trimming (was_trimmed, dropped_count, etc.)

    Ambos implementadores (IndividualContextBuilder, SharedProjectContextBuilder)
    deben respetar este contrato exactamente.
    """

    def build(
        self,
        conversation_id: int,
        max_tokens: int,
        output_reserved: int,
    ) -> tuple[list[dict], dict]:
        """
        Construye la lista de mensajes a enviar a Anthropic.

        Args:
            conversation_id: id de la conversación en DB.
            max_tokens: presupuesto total de tokens del modelo.
            output_reserved: tokens reservados para la respuesta del modelo.

        Returns:
            (messages, status)
            - messages: lista de dicts con 'role' y 'content'.
            - status: dict con metadatos (was_trimmed, dropped_count, ...).
        """
        ...
