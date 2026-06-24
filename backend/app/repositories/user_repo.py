"""
Repository para User — encapsula todo el acceso SQL a la tabla users.

El resto del código (services, routes) NO sabe SQL.
Habla con esta clase usando métodos en español del dominio.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User


class UserRepository:
    """Acceso a la tabla users."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        """Busca un user por su id."""
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        """Busca un user por su email."""
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, email: str, password_hash: str, nombre: str, role: str = "user") -> User:
        """Crea un user nuevo y lo persiste en la BD."""
        user = User(
            email=email,
            password_hash=password_hash,
            nombre=nombre,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)  # refresh para que tenga el id auto-generado
        return user

    def email_exists(self, email: str) -> bool:
        """¿Existe ya un user con ese email?"""
        return self.get_by_email(email) is not None

    def get_by_google_id(self, google_id: str) -> User | None:
        """Busca un user por su google_id (el 'sub' que devuelve Google)."""
        stmt = select(User).where(User.google_id == google_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_google(self, email: str, nombre: str, google_id: str) -> User:
        """Crea un user que se registró con Google. NO tiene password_hash."""
        user = User(
            email=email,
            nombre=nombre,
            password_hash=None,
            auth_provider="google",
            google_id=google_id,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def link_google_to_user(self, user: User, google_id: str) -> User:
        """Asocia un google_id a un user existente (que se había registrado con email/password)."""
        user.google_id = google_id
        user.auth_provider = "google"
        self.db.commit()
        self.db.refresh(user)
        return user
