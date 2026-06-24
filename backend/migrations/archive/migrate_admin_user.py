"""
Migración: crea tabla mentor_requests + admin user admin@anoven.ai.

Password del admin: anoven-admin-2026  (cambialo después en BD si querés).
"""

import sys
from app.database import SessionLocal, Base, engine
from app.models import (  # noqa: F401
    user, mentor, interview_attempt, interview_message,
    conversation, message, project, rule, cost_event, attachment, mentor_request,
)
from app.models.user import User
from app.core.security import hash_password


ADMIN_EMAIL = "admin@anoven.ai"
ADMIN_PASSWORD = "anoven-admin-2026"
ADMIN_NAME = "Admin Anoven"


def main() -> int:
    Base.metadata.create_all(bind=engine)
    print("✓ Tabla mentor_requests lista.")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if existing is not None:
            if existing.role != "admin":
                existing.role = "admin"
                db.commit()
                print(f"  {ADMIN_EMAIL} ya existía — role actualizado a 'admin'")
            else:
                print(f"  {ADMIN_EMAIL} ya existe como admin. Nada que hacer.")
            return 0

        admin = User(
            email=ADMIN_EMAIL,
            nombre=ADMIN_NAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            auth_provider="local",
            role="admin",
            onboarding_state="passed",
            onboarding_attempts=0,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"✓ Admin creado: id={admin.id}  email={admin.email}")
        print(f"  Password: {ADMIN_PASSWORD}")
        print(f"  Cambialo desde la UI o vía SQL cuando quieras.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
