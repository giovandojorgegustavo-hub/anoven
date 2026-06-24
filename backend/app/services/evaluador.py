"""
Evaluador — servicio SEPARADO del Entrevistador.

Por qué separado: si el mismo LLM que entrevistó es el que evalúa, hay sesgo
(tiende a aprobarse a sí mismo). El Evaluador es otra llamada a Claude, con
otro system prompt, leyendo la conversación entera "desde afuera".

Cómo evita "alucinaciones de schema": usamos **tool use** de Anthropic. El
modelo está FORZADO a invocar la tool `submit_evaluation` con un schema fijo
— Anthropic valida la forma de los args antes de devolverlos. No JSON parsing
frágil ni regex.

El output del Evaluador alimenta:
  - `interview_attempts.score`           (Sesión 2.4 — métrica interna)
  - `interview_attempts.evaluator_feedback`  (Sesión 2.4 — interno)
  - `interview_attempts.profile_json`    (Sesión 2.5 — input del MentorMatcher)
"""

from typing import Any

from anthropic import Anthropic

from app.config import settings


# ============================================================
# System prompt del Evaluador
# ============================================================

EVALUADOR_SYSTEM_PROMPT = """\
Sos el Evaluador de Anoven. NO sos el Entrevistador — sos un servicio
independiente que lee una entrevista YA HECHA y extrae datos estructurados.

Tu trabajo es **customer discovery analysis** para Anoven. Anoven necesita
saber cómo se relaciona la gente con la IA para mejorar el producto, el
marketing y los prompts.

## QUÉ EXTRAÉS

1. **Score 0-100** — qué tan RICA fue la entrevista para Anoven.
   - 0-30: muy pobre, casi nada útil.
   - 31-60: tibia, algo se rescata.
   - 61-85: buena, perfil claro.
   - 86-100: excelente, datos jugosos con frases textuales potentes.

   El score NO juzga al user — juzga la conversación como fuente de insight.
   Una entrevista corta pero con info concreta puede sacar 80. Una entrevista
   larga pero con respuestas vagas saca 40.

2. **Profile estructurado** — datos que van a usar el MentorMatcher y los
   sistemas de Anoven. Solo lo que el user MENCIONÓ EXPLÍCITAMENTE. No inventes.

3. **Language gems** — frases LITERALES (palabras textuales) del user que
   sirvan para marketing y mejora de producto. Ej: "me da miedo que me
   reemplace", "siento que inventa cosas". NO parafrasees: copiá tal cual.

4. **Feedback interno** — qué le faltó a la entrevista. Para el equipo de
   Anoven, no para el user.

5. **Highlights** — 2 a 3 frases CORTAS en segunda persona para mostrarle al
   user que el sistema entendió. Tono cálido, directo:
   "Mencionaste que usás ChatGPT pero te frustra cuando inventa cosas."
   "Estás llevando adelante un café de especialidad."
   "Te asusta que la IA te reemplace."

6. **Mentor gaps** — detectá si en los dolores del user hay áreas que el
   catálogo público de Anoven NO cubre bien. Si las hay, sugerí qué mentor
   sería útil que NO tenemos. Máximo 2 gaps. Si todos sus dolores los cubren
   los 14 verticales del catálogo, devolvé lista vacía.

   El catálogo público actual incluye: Administración, Marketing, Finanzas,
   Operaciones, Personas, Filosofía, Análisis Adversarial, Legal, Software,
   Neuropsicología, Diseño, Docencia Jurídica, Escritura Jurídica, Brand Strategy.

   Ejemplos de gaps válidos:
   - "Cocina home" si menciona que cocina y no encuentra ayuda específica.
   - "Coaching deportivo" si el dolor es performance física.
   - "Crianza" si el dolor es parental.
   - NO sugieras "Coach de café boutique" si Marketing+Brand+Admin lo cubren.

## REGLAS DURAS

- SOLO usá la tool `submit_evaluation`. NO escribas texto suelto, NO expliques
  qué hiciste, NO comentes. Solo invocás la tool con sus args.
- Si un campo no aplica, lista vacía o null según corresponda.
- Si el user dijo algo medio ambiguo, anotalo en `language_gems` igual — la
  ambigüedad también es señal.
- Nunca inventes datos. Si no apareció en la conversación, no existe.
"""


# ============================================================
# Tool schema (validado por Anthropic antes de devolvernos el dict)
# ============================================================

SUBMIT_EVALUATION_TOOL = {
    "name": "submit_evaluation",
    "description": (
        "Envía la evaluación estructurada de una entrevista de Anoven. "
        "Devuelve score, profile, feedback interno, highlights, y mentor_gaps."
    ),
    "input_schema": {
        "type": "object",
        "required": ["score", "profile", "feedback", "highlights", "mentor_gaps"],
        "properties": {
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Riqueza de la entrevista para Anoven (0-100).",
            },
            "profile": {
                "type": "object",
                "required": [
                    "uses_ai",
                    "tools",
                    "fears",
                    "frustrations",
                    "expectations_unmet",
                    "current_focus",
                    "language_gems",
                    "interests",
                ],
                "properties": {
                    "uses_ai": {
                        "type": ["boolean", "null"],
                        "description": "¿El user usa IA hoy? null si no quedó claro.",
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Herramientas de IA mencionadas explícitamente (ChatGPT, Gemini, Claude, Copilot, etc.).",
                    },
                    "fears": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Miedos / desconfianzas que expresó sobre la IA.",
                    },
                    "frustrations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lo que le frustra de la(s) IA que usa hoy.",
                    },
                    "expectations_unmet": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Expectativas que tuvo con la IA y no se cumplieron.",
                    },
                    "current_focus": {
                        "type": ["string", "null"],
                        "description": "Qué proyecto, hobby o tema lo tiene ocupado ahora. null si no quedó claro.",
                    },
                    "language_gems": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Frases LITERALES del user (no parafraseadas) que sirvan para marketing y producto.",
                    },
                    "interests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Áreas o temas que mencionó (negocio, hobby, aprendizaje, etc.).",
                    },
                },
            },
            "feedback": {
                "type": "string",
                "description": "Notas internas: qué le faltó a la entrevista. No se muestra al user.",
            },
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
                "description": "2-3 frases cortas en segunda persona para mostrar al user que entendimos.",
            },
            "mentor_gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["nombre", "why"],
                    "properties": {
                        "nombre": {
                            "type": "string",
                            "maxLength": 80,
                            "description": "Nombre corto del mentor que falta. Ej: 'Cocina home', 'Crianza'.",
                        },
                        "proposed_canon": {
                            "type": "string",
                            "maxLength": 300,
                            "description": "Canon tentativo: autores/tradiciones de referencia. Opcional.",
                        },
                        "why": {
                            "type": "string",
                            "maxLength": 300,
                            "description": "1-2 frases explicando POR QUÉ este user lo necesita. Anclar en su perfil.",
                        },
                    },
                },
                "minItems": 0,
                "maxItems": 2,
                "description": "Mentores que el user necesita y NO están en el catálogo. Vacío si los 14 verticales cubren todo.",
            },
        },
    },
}


# ============================================================
# Cliente Anthropic
# ============================================================

_client = Anthropic(api_key=settings.anthropic_api_key)


def evaluate_conversation(messages: list[dict]) -> dict[str, Any]:
    """
    Llama al Evaluador con la conversación entera y devuelve el dict validado
    según el schema de `submit_evaluation`.

    `messages` es la lista de mensajes del attempt en formato Anthropic:
        [{"role": "user"|"assistant", "content": "..."}, ...]

    Lo formateamos como UN solo mensaje legible para el Evaluador — así Claude
    ve la transcripción completa de una y devuelve la evaluación.
    """
    transcript = _format_transcript(messages)

    response = _client.messages.create(
        model="claude-opus-4-8",  # Critical evaluator: Opus hardcoded para mejor scoring + feedback
        max_tokens=2048,
        system=EVALUADOR_SYSTEM_PROMPT,
        tools=[SUBMIT_EVALUATION_TOOL],
        # Forzamos a usar específicamente esta tool — el modelo NO puede
        # escribir texto suelto, tiene que invocar `submit_evaluation`.
        tool_choice={"type": "tool", "name": "submit_evaluation"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Acá está la transcripción de la entrevista a evaluar. "
                    "Invocá la tool `submit_evaluation` con tu análisis.\n\n"
                    "---\n\n"
                    f"{transcript}"
                ),
            }
        ],
    )

    # Buscamos el bloque de tipo tool_use en la respuesta.
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_evaluation":
            return block.input  # ya validado por Anthropic contra el schema

    # Esto NO debería pasar dado que forzamos tool_choice, pero defendemos
    # por si Anthropic cambia el comportamiento.
    raise RuntimeError("El Evaluador no invocó submit_evaluation.")


def _format_transcript(messages: list[dict]) -> str:
    """Formatea los mensajes como transcripción legible."""
    lines = []
    for m in messages:
        role_label = "ENTREVISTADOR" if m["role"] == "assistant" else "USER"
        lines.append(f"[{role_label}]\n{m['content']}\n")
    return "\n".join(lines)
