"""
Cliente de Google OAuth 2.0.

Authlib se encarga del protocolo:
- Construir la URL de autorización de Google (con el redirect_uri, scopes, state, PKCE).
- Recibir el `code` del callback y cambiarlo por un `access_token` + ID token.
- Validar el ID token (firma + audiencia + expiración).
- Devolvernos el `userinfo` (email, nombre, google_id).

Nosotros NO escribimos nada de eso a mano — Authlib lo resuelve.

`server_metadata_url` apunta al discovery doc de Google: ahí están todas las
URLs reales (authorize endpoint, token endpoint, JWKS para validar firmas).
Authlib lo lee al arrancar, así nunca harcodeamos URLs de Google que pueden cambiar.
"""

from authlib.integrations.starlette_client import OAuth

from app.config import settings


oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        # openid → ID token con email + sub
        # email + profile → userinfo con name, picture, etc.
        "scope": "openid email profile",
    },
)
