"""Smoke test del retrieval de memoria — Sesión 4.4."""

from app.database import SessionLocal
from app.services.conversation_service import (
    ConversationService,
    _significant_tokens,
)


def main() -> None:
    db = SessionLocal()
    svc = ConversationService(db)

    query = "hola tienes memoria de lo que hablamos antes? algo de cafe?"
    project = "anoven-app-user-1-bonabowl"
    current_conv = 7

    print(f"query: {query}")
    print(f"tokens significativos: {_significant_tokens(query)}")
    print(f"project: {project}")
    print(f"current_conv (excluido): {current_conv}")
    print()

    mems = svc._retrieve_relevant_memories(
        query=query,
        engram_project=project,
        current_conv_id=current_conv,
        limit=3,
    )
    print(f"memorias recuperadas: {len(mems)}")
    for m in mems:
        print(f"  id={m['id']}")
        print(f"    title: {m['title'][:80]!r}")
        print(f"    rank:  {m.get('rank')}")
    db.close()


if __name__ == "__main__":
    main()
