"""
Conexión a la BD usando SQLAlchemy 2.x.

Concepto clave:
  - engine = el "motor" que habla con la BD.
  - SessionLocal = factoría de sesiones (cada request usa una).
  - Base = clase padre de TODOS los modelos (tablas).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


# Engine — la conexión a la BD.
# Para SQLite necesitamos `connect_args={"check_same_thread": False}`
# porque SQLite por default es single-thread.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=settings.debug,  # en debug, imprime todas las queries SQL
)

# Factoría de sesiones. Una sesión = una "conversación" con la BD.
# Cada request HTTP debe abrir una y cerrarla al terminar.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Clase padre de TODOS los modelos. SQLAlchemy infiere las tablas
    leyendo las clases que hereden de esta."""
    pass


def get_db():
    """
    Dependency injection para FastAPI.
    Cada endpoint que necesite BD recibe una sesión y la cierra al terminar.

    Uso:
        @router.get("/users")
        def listar(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
