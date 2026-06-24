#!/usr/bin/env python3
"""
Seed inicial de mentor_skills.

Inserta skills de conocimiento practico para los mentores de Anoven.
Idempotente: usa INSERT OR IGNORE por UNIQUE (mentor_id, slug).

Ejecutar desde: cd anoven-app/backend && python scripts/seed_mentor_skills.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from app.database import SessionLocal  # noqa: E402

SKILLS_SEED = [
    # ---- Diseno (anoven-design, id=16) ----
    {
        "mentor_slug": "anoven-design",
        "slug": "principios-diseno-editorial",
        "title": "Principios de Diseno Editorial",
        "position": 1,
        "content": """## Principios de Diseno Editorial

El diseno editorial ordena la informacion en el espacio de modo que el lector
encuentre lo que necesita sin friccion. Tres principios guia:

**1. Jerarquia visual clara**
El ojo sigue peso. Lo que mas pesa (tamano, grosor, contraste) se lee primero.
Cada pieza debe tener UN elemento dominante, uno secundario, y el resto como apoyo.

**2. Ritmo y respiro**
El espacio blanco no es espacio vacio -- es silencio activo que da respiro
al lector. Una pagina sin blanco es un grito, no una conversacion.

**3. Consistencia sistematica**
Los estilos tipograficos, la grilla y la paleta deben ser un sistema, no decisiones
caso a caso. Lo que se repite con intencion construye identidad; lo que varia sin
razon destruye coherencia.

**Canon**: Jan Tschichold -- La Nueva Tipografia, 1928. Josef Muller-Brockmann -- Grid Systems, 1961.
""",
    },
    {
        "mentor_slug": "anoven-design",
        "slug": "diseno-atomico",
        "title": "Diseno Atomico y Sistemas de Diseno",
        "position": 2,
        "content": """## Diseno Atomico y Sistemas de Diseno

Brad Frost formalizo la metafora quimica: los componentes de una interfaz
se construyen de lo mas simple (atomo) a lo mas complejo (pagina completa).

**Los cinco niveles**:
1. **Atomos**: elementos basicos -- boton, input, icono, color, tipografia.
2. **Moleculas**: combinaciones funcionales -- campo de busqueda (input + boton).
3. **Organismos**: secciones complejas -- header, card de producto, form completo.
4. **Templates**: estructura de pagina sin contenido real.
5. **Paginas**: templates con contenido real -- lo que el usuario ve.

**Por que importa**: pensar en sistemas evita la duplicacion y mantiene
la coherencia a escala. Sin sistema, cada diseniador toma decisiones locales
que colisionan con las decisiones globales.

**Canon**: Brad Frost -- Atomic Design, 2016.
""",
    },

    # ---- Creador (anoven-creador, id=20) ----
    {
        "mentor_slug": "anoven-creador",
        "slug": "escucha-activa-mentor",
        "title": "Escucha Activa para Crear Mentores",
        "position": 1,
        "content": """## Escucha Activa para Crear Mentores

Crear un mentor util requiere entender NO solo el dominio -- sino como el user
piensa dentro de ese dominio. La escucha activa tiene tres capas:

**1. Escucha del contenido**: que informacion explicita da el user.
**2. Escucha del gap**: que NO dice pero claramente necesita.
**3. Escucha del tono**: como quiere que le hablen -- formal/informal,
   directo/Socratico, desafiante/contenedor.

**Tecnica concreta**:
- Parafrasa para validar: "Si entiendo bien, queres un mentor que..."
- Pregunta por ejemplos negativos: "Que cosas NO queres que haga este mentor?"
- Pregunta por el uso concreto: "Dame un ejemplo de pregunta que le harias."

El tercer tipo de pregunta es el mas revelador: el uso real dice mas que
cualquier descripcion abstracta del mentor.
""",
    },
    {
        "mentor_slug": "anoven-creador",
        "slug": "diagnostico-oficio-canon",
        "title": "Diagnostico de Oficio y Canon",
        "position": 2,
        "content": """## Diagnostico de Oficio y Canon

Un mentor efectivo necesita dos cosas bien definidas antes de poder existir:
**oficio** (que sabe hacer) y **canon** (en que tradicion piensa).

**Diagnoscar el oficio**:
- No es suficiente "diseno" -- es demasiado amplio.
- Mejor: "diseno de sistemas de identidad para marcas de alimentos artesanales".
- Cuanto mas especifico el oficio, mas preciso el mentor.

**Diagnoscar el canon**:
- Algunos dominios tienen canon canonico (arquitectura: Vitruvio, Mies, Koolhaas).
- Otros tienen canon implicito (emprendimiento: leanstartup, JTBD, Drucker).
- Si el user no sabe el canon, guialo: "Hay alguien cuya forma de pensar
  sobre X admiras o te parece correcta?"

**Regla de oro**: no pedir MAS informacion de la necesaria. Entre el turn 3
y el turn 6 ya deberia haber suficiente para un primer prototipo iterable.
""",
    },

    # ---- Software (anoven-software, id=14) ----
    {
        "mentor_slug": "anoven-software",
        "slug": "clean-architecture",
        "title": "Clean Architecture y Separacion de Capas",
        "position": 1,
        "content": """## Clean Architecture y Separacion de Capas

Robert C. Martin (2017) formalizo el principio: las reglas de negocio no deben
depender de frameworks, bases de datos, UI ni ningun detalle de entrega.

**La regla de dependencia**: las dependencias del codigo fuente solo pueden
apuntar hacia adentro. Las capas internas no saben nada de las externas.

**Capas (de adentro hacia afuera)**:
1. **Entidades**: objetos de negocio con reglas criticas (Entities).
2. **Casos de uso**: orquestacion de logica de aplicacion (Use Cases / Interactors).
3. **Adaptadores de interfaz**: controllers, presenters, gateways.
4. **Frameworks y drivers**: web, DB, UI -- detalles de entrega.

**Anti-patron clasico**: logica de negocio en controllers (routes).
Cuando la logica esta en el controller, no puedes testearla sin levantar HTTP.

**Canon**: Robert C. Martin -- Clean Architecture, 2017. Alistair Cockburn -- Hexagonal Architecture, 2005.
""",
    },
    {
        "mentor_slug": "anoven-software",
        "slug": "tdd-como-diseno",
        "title": "TDD como Herramienta de Diseno",
        "position": 2,
        "content": """## TDD como Herramienta de Diseno

Test-Driven Development no es sobre testing -- es sobre diseno. Escribir el test
primero te fuerza a pensar en la interfaz publica del codigo antes de pensar
en su implementacion.

**El ciclo RED-GREEN-REFACTOR**:
1. **RED**: escribi un test que falla. Describe el comportamiento deseado.
2. **GREEN**: escribi el codigo minimo que hace pasar el test.
3. **REFACTOR**: mejora el diseno sin romper los tests.

**Por que el orden importa**: si escribis el codigo antes del test, el test
describe lo que el codigo hace -- no lo que deberia hacer. Invertis el contrato.

**Senial de mal diseno en el test**: si tu test necesita mockear 5 cosas
para funcionar, el codigo que estas testando tiene demasiadas dependencias.

**Canon**: Kent Beck -- Test-Driven Development By Example, 2002.
""",
    },
]


def main():
    db = SessionLocal()
    try:
        from sqlalchemy import select
        from app.models.mentor import Mentor
        from app.models.mentor_skill import MentorSkill

        # Resolver mentor_slug -> mentor_id
        mentor_map = {}
        for m in db.execute(select(Mentor)).scalars():
            mentor_map[m.slug] = m.id

        print(f"Found {len(mentor_map)} mentors in DB: {list(mentor_map.keys())[:5]}...")

        inserted = 0
        skipped = 0

        for skill_data in SKILLS_SEED:
            mentor_slug = skill_data["mentor_slug"]
            mentor_id = mentor_map.get(mentor_slug)
            if mentor_id is None:
                print(f"  SKIP: mentor '{mentor_slug}' no existe en DB")
                skipped += 1
                continue

            # Idempotente: ignorar si ya existe (UNIQUE mentor_id+slug)
            existing = db.execute(
                select(MentorSkill).where(
                    MentorSkill.mentor_id == mentor_id,
                    MentorSkill.slug == skill_data["slug"],
                )
            ).scalar_one_or_none()

            if existing is not None:
                print(f"  SKIP (exists): {mentor_slug}/{skill_data['slug']}")
                skipped += 1
                continue

            skill = MentorSkill(
                mentor_id=mentor_id,
                slug=skill_data["slug"],
                title=skill_data["title"],
                content=skill_data["content"],
                triggers=None,
                position=skill_data["position"],
                enabled=True,
            )
            db.add(skill)
            print(f"  INSERT: {mentor_slug}/{skill_data['slug']}")
            inserted += 1

        db.commit()
        print(f"\nDone. Inserted: {inserted}, Skipped: {skipped}")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
