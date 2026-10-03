import sqlite3
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[2] / "saladetareas.db"


@contextmanager
def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS Usuarios (

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    correo TEXT NOT NULL UNIQUE,
    contrasena TEXT NOT NULL,
    telefono TEXT,
    rol TEXT NOT NULL,
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


initialize_database()


if __name__ == "__main__":
    print("Base de datos y tablas creadas exitosamente.")