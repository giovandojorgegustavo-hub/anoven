"""
AuthService — la lógica de negocio de registración y login.

Orquesta: validaciones, repository (DB), security (hashing/JWT),
y asignación automática de mentores default al registrarse.
"""

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.core.security import hash_password, verify_password, create_access_token
from app.services.mentor_service import MentorService
from app.services.project_service import ProjectService


class AuthError(Exception):
    pass


class EmailAlreadyExists(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.mentor_service = MentorService(db)
        self.project_service = ProjectService(db)

    def _bootstrap_user(self, user: User) -> None:
        """Setup post-creación común para users nuevos: defaults de mentores
        + project default 'General' + active_project_id apuntando a él."""
        self.mentor_service.assign_defaults_to_user(user.id)
        project = self.project_service.ensure_default_for_user(user.id)
        user.active_project_id = project.id
        self.db.commit()
        self.db.refresh(user)

    def register(self, email: str, password: str, nombre: str) -> tuple[User, str]:
        """Registra un user nuevo, le asigna los mentores default,
        y devuelve (user, jwt_token)."""

        if self.user_repo.email_exists(email):
            raise EmailAlreadyExists(f"El email '{email}' ya está registrado.")

        password_hash_str = hash_password(password)

        user = self.user_repo.create(
            email=email,
            password_hash=password_hash_str,
            nombre=nombre,
        )

        # ===== Bootstrap: mentores default + project default =====
        self._bootstrap_user(user)

        token = create_access_token(user.id)
        return user, token

    def login(self, email: str, password: str) -> tuple[User, str]:
        user = self.user_repo.get_by_email(email)
        if user is None:
            raise InvalidCredentials("Email o password incorrectos.")

        if user.password_hash is None:
            # El user se registró con Google y no tiene password local
            raise InvalidCredentials(
                "Este email se registró con Google. Iniciá sesión con Google."
            )

        if not verify_password(password, user.password_hash):
            raise InvalidCredentials("Email o password incorrectos.")

        token = create_access_token(user.id)
        return user, token

    def login_or_register_google(
        self,
        google_id: str,
        email: str,
        nombre: str,
    ) -> tuple[User, str]:
        """
        Maneja el callback de Google OAuth. Tres caminos posibles:
        1. Ya existe user con ese google_id → login (devolver JWT).
        2. Existe user con ese email pero auth_provider=local → linkear Google al user.
        3. No existe → crear user nuevo + asignarle los mentores default.

        Devuelve (user, jwt_token).
        """
        # Camino 1: ya conocemos a este google_id
        user = self.user_repo.get_by_google_id(google_id)
        if user is not None:
            token = create_access_token(user.id)
            return user, token

        # Camino 2: el email ya está registrado, pero como local. Linkeamos.
        existing = self.user_repo.get_by_email(email)
        if existing is not None:
            user = self.user_repo.link_google_to_user(existing, google_id)
            token = create_access_token(user.id)
            return user, token

        # Camino 3: user nuevo. Crear + bootstrap completo.
        user = self.user_repo.create_google(
            email=email,
            nombre=nombre,
            google_id=google_id,
        )
        self._bootstrap_user(user)

        token = create_access_token(user.id)
        return user, token
