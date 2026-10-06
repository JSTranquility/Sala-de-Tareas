"""Ubicación de SQLite, conexiones y creación explícita de tablas."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, has_app_context


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "saladetareas.db"
logger = logging.getLogger(__name__)

# usuario_id conserva su nombre histórico y significa usuario asignado.
TASK_TABLE_SQL = """CREATE TABLE Tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento TIMESTAMP,
    estado TEXT NOT NULL CHECK (estado IN
        ('pendiente', 'en_progreso', 'completada', 'cancelada')),
    usuario_id INTEGER,
    materia_id INTEGER,
    prioridad TEXT CHECK (prioridad IN ('baja', 'media', 'alta')),
    creador_id INTEGER,
    fecha_actualizacion TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios (id),
    FOREIGN KEY (materia_id) REFERENCES Materias (id),
    FOREIGN KEY (creador_id) REFERENCES Usuarios (id)
)"""

PAYMENT_TABLE_SQL = """CREATE TABLE Pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    monto INTEGER NOT NULL CHECK (typeof(monto) = 'integer'),
    fecha TIMESTAMP,
    tarea_id INTEGER,
    moneda TEXT CHECK (moneda IN ('USD', 'DOP')),
    estado TEXT CHECK (estado IN ('pendiente', 'pagado', 'anulado')),
    metodo TEXT CHECK (metodo IN ('efectivo', 'transferencia', 'tarjeta', 'otro')),
    fecha_pago TIMESTAMP,
    notas TEXT,
    fecha_creacion TIMESTAMP,
    monto_original TEXT,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios (id),
    FOREIGN KEY (tarea_id) REFERENCES Tareas (id),
    CHECK (estado != 'pagado' OR fecha_pago IS NOT NULL),
    CHECK (monto_original IS NOT NULL OR (
        tarea_id IS NOT NULL AND moneda IS NOT NULL AND estado IS NOT NULL
        AND metodo IS NOT NULL AND fecha_creacion IS NOT NULL AND monto > 0
    ))
)"""


def get_database_path() -> Path:
    """Resuelve la base configurada, relativa a la raíz del proyecto."""
    if has_app_context() and "DATABASE_PATH" in current_app.config:
        configured_path = current_app.config["DATABASE_PATH"]
    else:
        configured_path = os.environ.get("DATABASE_PATH") or DB_PATH

    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@contextmanager
def get_connection(*, create: bool = False):
    """Gestiona una transacción; crear el archivo requiere una acción explícita."""
    path = get_database_path()
    # rw exige una base existente; rwc permite crearla solo al inicializar.
    mode = "rwc" if create else "rw"
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)
    except sqlite3.Error:
        logger.error("No se pudo abrir la conexión SQLite.")
        raise
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # Aquí se ejecuta el bloque que usa `with get_connection()`.
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


def initialize_database() -> None:
    """Crea las tablas faltantes sin modificar el esquema de las existentes."""
    with get_connection(create=True) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS Usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                correo TEXT NOT NULL UNIQUE,
                contrasena TEXT NOT NULL,
                telefono TEXT,
                rol TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS Materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Se comparte la definición de Tareas con su script de actualización.
        connection.execute(TASK_TABLE_SQL.replace(
            "CREATE TABLE Tareas", "CREATE TABLE IF NOT EXISTS Tareas", 1
        ))

        connection.execute(PAYMENT_TABLE_SQL.replace(
            "CREATE TABLE Pagos", "CREATE TABLE IF NOT EXISTS Pagos", 1
        ))

        connection.execute("""
            CREATE TABLE IF NOT EXISTS Asistencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES Usuarios (id)
            )
        """)


if __name__ == "__main__":
    initialize_database()
    print("Base de datos y tablas creadas exitosamente.")
