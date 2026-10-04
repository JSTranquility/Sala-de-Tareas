import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, has_app_context


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "saladetareas.db"
logger = logging.getLogger(__name__)


def get_database_path() -> Path:
    """Resuelve la base configurada, relativa a la raíz del proyecto."""
    configured_path = (
        current_app.config["DATABASE_PATH"]
        if has_app_context() and "DATABASE_PATH" in current_app.config
        else os.environ.get("DATABASE_PATH") or DB_PATH
    )
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@contextmanager
def get_connection(*, create: bool = False):
    """Gestiona una transacción; crear el archivo requiere una acción explícita."""
    path = get_database_path()
    mode = "rwc" if create else "rw"
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)
    except sqlite3.Error:
        logger.error("No se pudo abrir la conexión SQLite.")
        raise
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise
    except sqlite3.Error:
        connection.rollback()
        logger.error("Falló una operación SQLite; se revirtió la transacción.")
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Crea las tablas faltantes sin modificar el esquema de las existentes."""
    with get_connection(create=True) as connection:
        cursor = connection.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS Usuarios (

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    correo TEXT NOT NULL UNIQUE,
    contrasena TEXT NOT NULL,
    telefono TEXT,
    rol TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS Materias (

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS Tareas (

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento TIMESTAMP,
    estado TEXT NOT NULL,
    usuario_id INTEGER NOT NULL,
    materia_id INTEGER,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios (id),
    FOREIGN KEY (materia_id) REFERENCES Materias (id)

)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS Pagos (

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    monto REAL NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios (id)

)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS Asistencias (

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios (id)

)''')


if __name__ == "__main__":
    initialize_database()
    print("Base de datos y tablas creadas exitosamente.")
