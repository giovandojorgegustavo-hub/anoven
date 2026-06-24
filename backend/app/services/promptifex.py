"""
Promptifex — servicio backstage que arma el draft de un mentor custom.

NO es user-facing. Se llama desde ConversationService cuando detecta el
marker [PROTOTYPE_READY] en el stream del Creador.

Usa Anthropic tool_use para forzar output estructurado (slug, nombre, canon,
filosofía, system_prompt). Una sola llamada — para MVP es suficiente.
La versión "3-4 LLM calls" del plan original es overkill por ahora.
"""

import re
from typing import Any

from anthropic import Anthropic

from app.config import settings


_client = Anthropic(api_key=settings.anthropic_api_key)


PROMPTIFEX_SYSTEM_PROMPT = """\
Sos Promptifex, el ingeniero de prompts de Anoven. NO sos user-facing — sos
backstage. Tu trabajo: leer una conversación entre el Creador y un user, y
armar el draft de un mentor custom que el user pidió.

# ENTREGÁS VIA TOOL — SIEMPRE

Usás la tool `submit_mentor_draft` con los campos requeridos. NO escribís
texto suelto. NO explicás qué hiciste.

# REGLAS DE CONTENIDO

1. **Slug**: ascii lowercase con guiones, derivado del nombre. Máximo 50
   chars. Ej: "cocina-casera", "filosofia-practica".

2. **Nombre**: 1-3 palabras claras. Ej: "Cocina Casera", "Filosofía Práctica".

3. **Canon**: 4-6 autores, teorías, escuelas o tradiciones que anclan al
   mentor. Separados por coma. Ej: "Brillat-Savarin, Ferran Adrià, MFK Fisher,
   teoría del umami".

   - NO inventes autores. Si el user no mencionó canon explícito, usá
     conocimiento estándar del dominio.
   - Si no estás seguro, marcá "(canon a curar)" al final.

4. **Filosofía**: 1-2 frases que capturan la esencia. Ej: "La técnica está
   al servicio del sabor. Sin ingrediente decente, no hay receta."

5. **System prompt**: el "CLAUDE.md" del mentor. Estructura mínima:

   - **§1 Identidad**: voz + oficio. Segunda persona, voseo rioplatense.
   - **§3 Canon**: autores con obras + años cuando los conozcas.
   - **§4 Reglas globales**: voseo, verify-before-agree, anti-sycophancy.
   - **§5 Anti-patrones**: 3-5 anti-patrones del dominio del mentor.

   Escribilo COMO SI le hablaras al mentor mismo: "Sos el mentor de X.
   Oficio: ...". Tono directo, sin filler.

   OBLIGATORIO incluir en el system_prompt:
       - "Hablás voseo rioplatense."
       - "Verify-before-agree: si el user te tira un dato técnico, no
         acordás antes de validar."

6. **initial_skills**: junto con el draft del mentor, generá 2-5 skills
   iniciales (`initial_skills`). Cada skill debe ser:
   - Un bloque autocontenido de conocimiento práctico relevante al oficio.
   - Técnicas concretas, patrones de pensamiento, referencias del canon.
   - NO repetir lo que ya está en `system_prompt`.
   - El `slug` debe ser ascii lowercase con guiones (ej: "escucha-activa").
   - El `content` debe tener al menos 200 caracteres (markdown libre).
   - Incluí entre 2 y 5 skills — mínimo 2, máximo 5.
"""


SUBMIT_MENTOR_DRAFT_TOOL = {
    "name": "submit_mentor_draft",
    "description": "Envía el draft estructurado del mentor custom que el user pidió.",
    "input_schema": {
        "type": "object",
        "required": ["slug", "nombre", "canon", "filosofia", "system_prompt"],
        "properties": {
            "slug": {
                "type": "string",
                "maxLength": 50,
                "description": "ascii lowercase con guiones, derivado del nombre.",
            },
            "nombre": {"type": "string", "maxLength": 100},
            "canon": {"type": "string", "maxLength": 500},
            "filosofia": {"type": "string", "maxLength": 500},
            "system_prompt": {"type": "string", "minLength": 200},
            "initial_skills": {
                "type": "array",
                "minItems": 2,
                "maxItems": 5,
                "description": (
                    "2-5 skills iniciales relevantes al oficio y canon del mentor. "
                    "Cada skill debe ser un bloque autocontenido de conocimiento "
                    "practico: tecnicas concretas, patrones de pensamiento, "
                    "referencias del canon. NO repitas lo que ya esta en "
                    "system_prompt."
                ),
                "items": {
                    "type": "object",
                    "required": ["slug", "title", "content"],
                    "properties": {
                        "slug": {
                            "type": "string",
                            "pattern": "^[a-z0-9-]+$",
                            "maxLength": 80,
                            "description": "Identificador unico en minusculas con guiones.",
                        },
                        "title": {
                            "type": "string",
                            "maxLength": 160,
                            "description": "Titulo corto del skill.",
                        },
                        "content": {
                            "type": "string",
                            "minLength": 200,
                            "maxLength": 6000,
                            "description": "Contenido del skill en markdown.",
                        },
                        "triggers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 0,
                            "maxItems": 10,
                            "description": "Palabras clave que activan este skill.",
                        },
                    },
                },
            },
        },
    },
}


def generate_mentor_draft(conversation_messages: list[dict]) -> dict[str, Any]:
    """
    Recibe la conversación Creador↔user en formato Anthropic y devuelve
    un dict con slug/nombre/canon/filosofia/system_prompt.

    `conversation_messages`: [{"role": "user"|"assistant", "content": ...}, ...]
    """
    transcript_lines = []
    for m in conversation_messages:
        role_label = "CREADOR" if m["role"] == "assistant" else "USER"
        transcript_lines.append(f"[{role_label}]\n{m['content']}\n")
    transcript = "\n".join(transcript_lines)

    response = _client.messages.create(
        model=settings.default_model,
        max_tokens=4096,
        system=PROMPTIFEX_SYSTEM_PROMPT,
        tools=[SUBMIT_MENTOR_DRAFT_TOOL],
        tool_choice={"type": "tool", "name": "submit_mentor_draft"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Acá está la conversación entre el Creador y el user. "
                    "Armá el draft del mentor que el user pidió. "
                    "Invocá `submit_mentor_draft` con tu output.\n\n"
                    "---\n\n"
                    f"{transcript}"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_mentor_draft":
            data = dict(block.input)
            data["slug"] = _sanitize_slug(data.get("slug", "mentor-custom"))
            return data

    raise RuntimeError("Promptifex no invocó submit_mentor_draft.")


def _sanitize_slug(raw: str) -> str:
    s = (raw or "").lower().strip()
    s = (
        s.replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "mentor-custom")[:50]


# ============================================================
# FASE 6 — Recurate mentor existente (Promptifex SDD pass)
# ============================================================

import os


def _load_mentor_template() -> str:
    """Carga el _TEMPLATE.md canónico que define la línea editorial."""
    template_paths = [
        "/opt/anoven-shared/mentor-template.md",
        os.path.expanduser("~/proyectos/anoven/mentores/_TEMPLATE.md"),
    ]
    for path in template_paths:
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    return ""


RECURATE_SYSTEM_PROMPT = """\
Sos Promptifex, el ingeniero de prompts de Anoven. Modo RECURAR.

Tu input: un mentor que YA EXISTE en producción (con su system_prompt actual)
+ el template canónico (_TEMPLATE.md) que define la estructura.

Tu objetivo: producir una NUEVA versión del system_prompt que:
  1. RESPETA el template (las 11 secciones §1-§11 obligatorias)
  2. COMPRIME el texto (objetivo: ~50-70% del tamaño original) sin perder
     identidad, canon, anti-patterns, ni hard-stops
  3. ACTUALIZA si hay drift (referencias viejas a gentleman-*, "yo no firmo",
     anti-patterns sin evidencia, etc.)
  4. DEFINE una eval suite básica (4-6 evals) que mide:
     - Canon citation accuracy (E1)
     - Anti-sycophancy (E2)
     - Anti-pattern recognition (E3)
     - Handoff correctness (E4)
     - Security/refusal compliance (E5)

# ENTREGÁS VIA TOOL — SIEMPRE

Usás `submit_recuration` con los campos requeridos. NO escribís texto suelto.

# REGLAS

- Mantené la voz/identidad/canon del mentor — NO cambiés su esencia.
- Comprimí frases redundantes, listas verbosas, ejemplos duplicados.
- El template marca la ESTRUCTURA, no el CONTENIDO específico del mentor.
- Las eval suites deben ser MEDIBLES (input concreto + expected behavior + pass criteria).
- En `change_summary`, listá: qué comprimiste, qué actualizaste, qué dejaste igual.
"""


SUBMIT_RECURATION_TOOL = {
    "name": "submit_recuration",
    "description": "Envía la versión curada del mentor + eval suite + summary del cambio.",
    "input_schema": {
        "type": "object",
        "required": [
            "new_system_prompt",
            "new_canon",
            "new_filosofia",
            "eval_suite",
            "change_summary",
        ],
        "properties": {
            "new_system_prompt": {
                "type": "string",
                "minLength": 500,
                "description": "El system_prompt nuevo, comprimido, siguiendo las 11 secciones del template.",
            },
            "new_canon": {
                "type": "string",
                "maxLength": 500,
                "description": "Canon actualizado (autor — obra, año). Mantener fundacional, agregar moderno solo si aplica.",
            },
            "new_filosofia": {
                "type": "string",
                "maxLength": 500,
                "description": "Filosofía del mentor, 1-2 frases.",
            },
            "eval_suite": {
                "type": "object",
                "description": "4-6 evals medibles que validan que el comportamiento se preservó.",
                "properties": {
                    "evals": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "required": ["id", "name", "input", "expected", "pass_criteria"],
                            "properties": {
                                "id": {"type": "string", "description": "E1, E2, E3..."},
                                "name": {"type": "string"},
                                "input": {"type": "string", "description": "Input concreto al mentor."},
                                "expected": {"type": "string", "description": "Comportamiento esperado."},
                                "pass_criteria": {"type": "string", "description": "Cómo se mide PASS/FAIL."},
                            },
                        },
                    },
                },
                "required": ["evals"],
            },
            "change_summary": {
                "type": "string",
                "minLength": 100,
                "description": "Resumen del cambio: qué se comprimió, qué se actualizó, qué se mantuvo intacto.",
            },
        },
    },
}


def recurate_mentor(
    current_system_prompt: str,
    mentor_slug: str,
    mentor_nombre: str,
    current_canon: str,
    current_filosofia: str,
) -> dict[str, Any]:
    """
    Pasada de Promptifex SDD sobre un mentor existente.

    Devuelve dict con:
      - new_system_prompt
      - new_canon
      - new_filosofia
      - eval_suite (dict con evals)
      - change_summary

    El llamador (admin route) decide si persiste el cambio bumpeando version.
    """
    template = _load_mentor_template()
    if not template:
        raise RuntimeError("No encuentro el _TEMPLATE.md canónico.")

    user_content = (
        f"# Mentor a recurar: {mentor_slug} ({mentor_nombre})\n\n"
        f"## Canon actual\n{current_canon}\n\n"
        f"## Filosofía actual\n{current_filosofia}\n\n"
        f"## System prompt actual ({len(current_system_prompt)} bytes)\n\n"
        f"```markdown\n{current_system_prompt}\n```\n\n"
        f"---\n\n"
        f"## Template canónico (estructura obligatoria)\n\n"
        f"```markdown\n{template}\n```\n\n"
        f"---\n\n"
        "Tu tarea:\n"
        "1. Generar new_system_prompt comprimido (~50-70% del original) que respete las 11 secciones del template.\n"
        "2. Actualizar canon si hay drift (autor — obra, año).\n"
        "3. Definir eval_suite con 4-6 evals medibles (E1-E6).\n"
        "4. Resumir cambio en change_summary (qué comprimiste, qué actualizaste, qué mantuviste).\n\n"
        "Invocá `submit_recuration` con tu output."
    )

    response = _client.messages.create(
        model=settings.default_model,
        max_tokens=8192,
        system=RECURATE_SYSTEM_PROMPT,
        tools=[SUBMIT_RECURATION_TOOL],
        tool_choice={"type": "tool", "name": "submit_recuration"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_recuration":
            data = dict(block.input)
            # Sanity check
            if len(data.get("new_system_prompt", "")) < 500:
                raise RuntimeError("Promptifex devolvió system_prompt demasiado corto.")
            return data

    raise RuntimeError("Promptifex no invocó submit_recuration.")
