"""
Smoke test del cliente engram. Ejecutar UNA vez para verificar conexión.

    cd /home/anoven/anoven-app/backend
    .venv/bin/python3 test_engram.py
"""

from app.services.engram_client import engram, project_for_user, new_session_id


def main() -> None:
    print("=== health ===")
    print("alive:", engram.health())

    print()
    print("=== create session ===")
    project = project_for_user(1)
    sid = new_session_id()
    print(f"project: {project}")
    print(f"session: {sid[:13]}...")
    print(f"created: {engram.create_session(sid, project)}")

    print()
    print("=== save observation ===")
    obs = engram.save_observation(
        session_id=sid,
        project=project,
        title="Smoke test desde backend Python",
        content=(
            "Jorge dijo que vende café boutique en Belgrano. 80 cafés/día. "
            "Quiere llegar a 200. Le frustra que ChatGPT le invente cosas."
        ),
        obs_type="discovery",
    )
    print(f"obs result: {obs}")

    print()
    print("=== search ===")
    results = engram.search(query="café boutique", project=project, limit=5)
    print(f"resultados: {len(results)}")
    for r in results[:3]:
        print(f"  id={r.get('id')} title={r.get('title')!r}")


if __name__ == "__main__":
    main()
