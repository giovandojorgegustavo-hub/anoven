"""
TicketStorageAdapter — puerto de almacenamiento de archivos para tickets.

Patrón: Alistair Cockburn — Hexagonal Architecture (Ports & Adapters), 2005.
Si en v2 se migra a S3 o DO Spaces, solo se cambia este adapter.
El service NUNCA conoce el filesystem directamente.

Path de almacenamiento:
  ${ANOVEN_STORAGE_ROOT}/uploads/tickets/{ticket_id}/{uuid}.{ext}

El file_path almacenado en BD es relativo a ANOVEN_STORAGE_ROOT.
El adapter solo usa pathlib + uuid (stdlib). NO imports de fastapi.

Magic bytes para validación de MIME:
  PNG:  \\x89PNG (primeros 4 bytes)
  JPEG: \\xFF\\xD8\\xFF (primeros 3 bytes)
  WEBP: RIFF....WEBP (bytes 0-3 = RIFF, bytes 8-11 = WEBP)
"""

import os
import uuid
from pathlib import Path


# Magic bytes para cada MIME permitido
_MAGIC_BYTES: dict[str, bytes] = {
    "image/png":  b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
}

# WEBP tiene firma en dos lugares (RIFF y WEBP offset 8)
_WEBP_RIFF = b"RIFF"
_WEBP_MARK = b"WEBP"

ALLOWED_MIMES = frozenset(["image/png", "image/jpeg", "image/webp"])

# Extensiones por MIME
_MIME_TO_EXT: dict[str, str] = {
    "image/png":  "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


class AttachmentMimeNotAllowed(Exception):
    """MIME no está en la lista blanca o los magic bytes no coinciden."""
    pass


class AttachmentStorageError(Exception):
    """Error al escribir/leer/eliminar en disco."""
    pass


class TicketStorageAdapter:
    """
    Adapter de almacenamiento de archivos para tickets.

    Recibe ANOVEN_STORAGE_ROOT en __init__ — no lee env vars directamente
    para facilitar tests y inyección de dependencias.
    """

    def __init__(self, root: str):
        self._root = Path(root)

    def _validate_magic_bytes(self, data: bytes, declared_mime: str) -> None:
        """
        Valida que los primeros bytes del archivo coincidan con el MIME declarado.
        Raises AttachmentMimeNotAllowed si hay mismatch o MIME no permitido.
        """
        if declared_mime not in ALLOWED_MIMES:
            raise AttachmentMimeNotAllowed(
                f"Solo aceptamos imágenes PNG, JPEG o WebP."
            )

        if declared_mime == "image/webp":
            if len(data) < 12:
                raise AttachmentMimeNotAllowed("Solo aceptamos imágenes PNG, JPEG o WebP.")
            if data[:4] != _WEBP_RIFF or data[8:12] != _WEBP_MARK:
                raise AttachmentMimeNotAllowed("Solo aceptamos imágenes PNG, JPEG o WebP.")
        else:
            magic = _MAGIC_BYTES[declared_mime]
            if not data[:len(magic)] == magic:
                raise AttachmentMimeNotAllowed("Solo aceptamos imágenes PNG, JPEG o WebP.")

    @staticmethod
    def sanitize_filename(original_name: str, mime_type: str) -> str:
        """
        Devuelve un nombre de archivo seguro: {uuid}.{ext}.
        Elimina path traversal y nombres peligrosos.
        El nombre original se guarda en BD en original_name pero no se usa en el path.
        """
        ext = _MIME_TO_EXT.get(mime_type, "bin")
        return f"{uuid.uuid4().hex}.{ext}"

    def write(
        self,
        ticket_id: int,
        data: bytes,
        declared_mime: str,
        original_name: str,
    ) -> tuple[str, str]:
        """
        Valida los magic bytes, escribe en disco y devuelve
        (relative_path, safe_filename).

        relative_path es relativo a self._root — lo que se guarda en BD.

        Raises:
          AttachmentMimeNotAllowed: MIME inválido o magic bytes mismatch
          AttachmentStorageError: error de I/O al escribir
        """
        self._validate_magic_bytes(data, declared_mime)

        safe_filename = self.sanitize_filename(original_name, declared_mime)
        dir_path = self._root / "uploads" / "tickets" / str(ticket_id)

        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            file_path = dir_path / safe_filename
            file_path.write_bytes(data)
        except OSError as e:
            raise AttachmentStorageError(
                f"Error interno. Reintenta."
            ) from e

        # path relativo a root — lo que va a BD
        rel_path = str(Path("uploads") / "tickets" / str(ticket_id) / safe_filename)
        return rel_path, safe_filename

    def read(self, rel_path: str) -> bytes:
        """
        Lee el archivo desde disco.

        Raises:
          AttachmentStorageError: si el archivo no existe o no se puede leer
        """
        abs_path = self._root / rel_path
        try:
            return abs_path.read_bytes()
        except OSError as e:
            raise AttachmentStorageError("Error interno. Reintenta.") from e

    def get_absolute_path(self, rel_path: str) -> Path:
        """Devuelve la ruta absoluta (para FileResponse en el route)."""
        return self._root / rel_path

    def delete(self, rel_path: str) -> None:
        """
        Elimina el archivo. Silencioso si no existe (idempotente).

        Raises:
          AttachmentStorageError: si hay error de permisos
        """
        abs_path = self._root / rel_path
        try:
            if abs_path.exists():
                abs_path.unlink()
        except OSError as e:
            raise AttachmentStorageError("Error interno. Reintenta.") from e
