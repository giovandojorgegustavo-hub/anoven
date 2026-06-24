"""
Utilidades de seguridad: hash de passwords + JWT.

Uso `bcrypt` DIRECTO en vez de `passlib`. Razón: passlib 1.7.4 está roto
con bcrypt 5.0.0 — busca un atributo `__about__` que ya no existe y como
fallback hace un check incorrecto que rechaza CUALQUIER password.

bcrypt directo es más simple además: hash devuelve bytes, lo decodificamos
para guardar como str en la BD. Verify recibe ambos como bytes.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import settings


# Bcrypt tiene un límite real de 72 bytes en el password. Si truncamos
# manualmente nos aseguramos que un password legítimamente largo no rompa.
_BCRYPT_MAX = 72


def _truncate(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(password: str) -> str:
    """Convierte un password plain → hash bcrypt (incluye salt)."""
    h = bcrypt.hashpw(_truncate(password), bcrypt.gensalt())
    return h.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara un password plain con un hash bcrypt. True si coinciden."""
    try:
        return bcrypt.checkpw(_truncate(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# === JWT (sin cambios) ===

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        return int(user_id_str)
    except JWTError:
        return None
