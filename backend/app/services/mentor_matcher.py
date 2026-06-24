"""
MentorMatcher — tercer servicio LLM del flujo de onboarding.

Pipeline completo:
  1) Entrevistador (Sesión 2.2) — chat customer discovery
  2) Evaluador (Sesión 2.4) — extrae profile_json + score
  3) MentorMatcher (Sesión 2.5, este archivo) — elige 5 mentores del catálogo

Input:
  - profile (dict): lo que armó el Evaluador (uses_ai, tools, fears,
    frustrations, expectations_unmet, current_focus, language_gems, interests).
  - catalog (list[dict]): los mentores `global+active`, solo metadatos
    (id, slug, nombre, canon, filosofia). NO mandamos system_prompts —
    son enormes y el matcher decide solo por descripción.

Output:
  list de 5 dicts: { slug: str, reason: str (1-2 frases) }

Usa tool_use forzado para que Claude devuelva el match estructurado.
"""

from typing import Any

from anthropic import Anthropic

from app.config import settings


# ============================================================
# System prompt del MentorMatcher
# ============================================================

MENTOR_MATCHER_SYSTEM_PROMPT = """\
Sos el MentorMatcher de Anoven. Tu trabajo es elegir los 5 mentores del
catálogo público que más se ajustan al perfil de un user específico.

# CÓMO ELEGIR

El user te llega con un `profile` extraído por el Evaluador. Mirá esos
campos en este orden de prioridad:

1. `current_focus` — qué proyecto / hobby / interés tiene HOY. Es el
   ancla más fuerte. Si dijo "tengo una panadería", probablemente quiera
   mentores de admin / marketing / finanzas. Si dijo "aprendo cocina por
   hobby", la cosa cambia (creatividad / aprendizaje / diseño).

2. `frustrations` + `expectations_unmet` + `fears` — esto indica DOLOR.
   Mentores que aborden ese dolor pesan más.

3. `interests` — areas declaradas explícitamente.

4. `language_gems` y `tools` — pistas extra. Si menciona Brand, Brand
   Strategy es candidato fuerte. Si menciona aspectos cognitivos,
   Neuropsicología puede sumar.

# CRITERIOS DE BALANCE

Devolvé exactamente 5 mentores. Mezclá:

- 3 verticales **directos al focus declarado**: si el user es emprendedor,
  Admin + Marketing + Finanzas; si es creativo, Diseño + Creatividad + Brand.
- 1 vertical **transversal** que enriquezca: Filosofía (reflexión),
  Neuropsicología (cómo funciona la mente), People (trabajar con otros).
- 1 vertical **complementario o sorpresa**: algo que el user no pidió
  explícitamente pero que su perfil sugiere que le va a venir bien.

NO elijas 5 mentores del mismo eje (ej: Admin + Marketing + Finanzas +
Operations + People todos juntos) — eso es 5 mentores de "empresa". Aburre
y limita.

# REGLAS DURAS

1. SOLO usá la tool `submit_match`. NO escribas texto suelto.
2. EXACTAMENTE 5 mentores. Ni 4 ni 6.
3. Cada `slug` que devuelvas TIENE que estar en el catálogo que te paso.
   NO inventes slugs ni elijas mentores que no figuran.
4. Cada `reason` es 1 a 2 frases CORTAS en español rioplatense. Tono
   directo, segundo persona ("te conviene X porque mencionaste Y").
   NO uses "el user" — hablás al user.
5. Las `reason` tienen que anclar en CONTENIDO real del profile: nombrar
   las frustraciones / herramientas / focus que aparecen en los datos.
   Genérico es banderazo rojo.
"""


# ============================================================
# Tool schema
# ============================================================

SUBMIT_MATCH_TOOL = {
    "name": "submit_match",
    "description": (
        "Envía los 5 mentores elegidos para el user con la razón corta de cada uno."
    ),
    "input_schema": {
        "type": "object",
        "required": ["matches"],
        "properties": {
            "matches": {
                "type": "array",
                "minItems": 5,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "required": ["slug", "reason"],
                    "properties": {
                        "slug": {
                            "type": "string",
                            "description": "Slug del mentor (tiene que existir en el catálogo).",
                        },
                        "reason": {
                            "type": "string",
                            "maxLength": 240,
                            "description": "1-2 frases cortas en voseo explicando por qué este mentor encaja con este user.",
                        },
                    },
                },
            }
        },
    },
}


# ============================================================
# Cliente Anthropic
# ============================================================

_client = Anthropic(api_key=settings.anthropic_api_key)


def match_mentors(profile: dict, catalog: list[dict]) -> list[dict[str, Any]]:
    """
    Elige 5 mentores del catalog basado en el profile.

    `catalog` es list de dicts con: id, slug, nombre, canon, filosofia.
    Devolvemos list de dicts: [{slug, reason}, ...] × 5.

    El llamador (interview_service) resuelve el slug → id usando el catalog.
    """
    catalog_text = _format_catalog(catalog)
    profile_text = _format_profile(profile)

    response = _client.messages.create(
        model=settings.default_model,
        max_tokens=2048,
        system=MENTOR_MATCHER_SYSTEM_PROMPT,
        tools=[SUBMIT_MATCH_TOOL],
        tool_choice={"type": "tool", "name": "submit_match"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Acá tenés el catálogo de mentores disponibles:\n\n"
                    f"{catalog_text}\n\n"
                    "---\n\n"
                    "Y este es el perfil del user a matchear:\n\n"
                    f"{profile_text}\n\n"
                    "Elegí los 5 mentores más adecuados invocando "
                    "`submit_match`."
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_match":
            matches = block.input.get("matches", [])
            # Sanity check: los slugs devueltos tienen que estar en el catálogo.
            valid_slugs = {m["slug"] for m in catalog}
            filtered = [m for m in matches if m["slug"] in valid_slugs]
            return filtered

    raise RuntimeError("El MentorMatcher no invocó submit_match.")


def _format_catalog(catalog: list[dict]) -> str:
    """Imprime el catálogo de mentores de forma legible para el LLM."""
    lines = []
    for m in catalog:
        lines.append(
            f"- slug: {m['slug']}\n"
            f"  nombre: {m['nombre']}\n"
            f"  filosofia: {m.get('filosofia', '(sin descripción)')}\n"
            f"  canon: {m.get('canon', '(sin canon)')}"
        )
    return "\n".join(lines)


def _format_profile(profile: dict) -> str:
    """Imprime el profile_json en formato legible."""
    return (
        f"uses_ai: {profile.get('uses_ai')}\n"
        f"tools: {profile.get('tools', [])}\n"
        f"fears: {profile.get('fears', [])}\n"
        f"frustrations: {profile.get('frustrations', [])}\n"
        f"expectations_unmet: {profile.get('expectations_unmet', [])}\n"
        f"current_focus: {profile.get('current_focus')}\n"
        f"interests: {profile.get('interests', [])}\n"
        f"language_gems: {profile.get('language_gems', [])}"
    )
