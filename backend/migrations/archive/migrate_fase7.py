"""
Migración FASE 7: re-asignar mentores a TODOS los users existentes.

Hoy cada user tiene los 16 globals + sus custom. El cambio FASE 7:
  - Mantener source='default' SOLO para los 4 CORE_FOUR_SLUGS
  - Desactivar source='default' para los otros (admin/marketing/design/secondbrain quedan)
  - Mantener source='created_by_self' (custom del user) intacto
  - Mantener source='matched' intacto (si lo tenían — solo aplica si pasaron entrevista)

Para users sin profile de entrevista (los 25 migrados): quedan con solo 4 core.
Si en el futuro completan entrevista, el matcher les agrega hasta 2.
"""

import sys
from app.database import SessionLocal
from app.models.mentor import UserMentor, Mentor
from app.services.mentor_service import CORE_FOUR_SLUGS


def main():
    db = SessionLocal()
    try:
        # Obtener ids de los 4 core
        core_mentor_ids = set()
        for slug in CORE_FOUR_SLUGS:
            m = db.query(Mentor).filter(Mentor.slug == slug).first()
            if m:
                core_mentor_ids.add(m.id)
            else:
                print(f"  ⚠️ no encontré {slug} en BD — skip")

        if not core_mentor_ids:
            print("  ERROR: ningún core mentor encontrado")
            return 1

        print(f"  Core mentor ids: {sorted(core_mentor_ids)}")
        print()

        # Procesar todos los users
        from app.models.user import User
        users = db.query(User).order_by(User.id).all()
        print(f"  Procesando {len(users)} users...")
        print()

        total_deactivated = 0
        total_kept = 0
        total_added_core = 0

        for user in users:
            ums = db.query(UserMentor).filter(
                UserMentor.user_id == user.id,
                UserMentor.active == True,
            ).all()

            user_kept = 0
            user_deactivated = 0
            user_existing_core_ids = set()

            for um in ums:
                # Mantener: custom del user, matched, y los core con source='default'
                if um.source == "created_by_self":
                    user_kept += 1
                    continue
                if um.source == "matched":
                    user_kept += 1
                    continue
                if um.source == "default" and um.mentor_id in core_mentor_ids:
                    user_kept += 1
                    user_existing_core_ids.add(um.mentor_id)
                    continue
                # Resto: source='default' pero NO core → desactivar
                um.active = False
                user_deactivated += 1

            # Asegurar que los 4 core estén asignados (si faltaba alguno)
            missing_core = core_mentor_ids - user_existing_core_ids
            user_added_core = 0
            for mentor_id in missing_core:
                new_um = UserMentor(
                    user_id=user.id,
                    mentor_id=mentor_id,
                    source="default",
                )
                db.add(new_um)
                user_added_core += 1
                user_kept += 1

            print(
                f"  user_id={user.id:>2} {user.email[:35]:<35} "
                f"  kept={user_kept:>2}  deactivated={user_deactivated:>2}  "
                f"added_core={user_added_core}"
            )
            total_deactivated += user_deactivated
            total_kept += user_kept
            total_added_core += user_added_core

        db.commit()
        print()
        print("=== Resumen ===")
        print(f"  Users procesados:         {len(users)}")
        print(f"  Total mentores mantenidos: {total_kept}")
        print(f"  Total desactivados:        {total_deactivated}")
        print(f"  Total core auto-agregados: {total_added_core}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
