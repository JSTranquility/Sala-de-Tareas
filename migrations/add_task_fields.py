"""Actualiza tareas explícitamente, con respaldo y conservación de datos."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

from app.utils.data.database import TASK_TABLE_SQL


LEGACY_COLUMNS = (
    "id", "titulo", "descripcion", "fecha_creacion", "fecha_vencimiento",
    "estado", "usuario_id", "materia_id",
)
NEW_COLUMNS = ("prioridad", "creador_id", "fecha_actualizacion")


def check_integrity(connection: sqlite3.Connection) -> None:
    """Rechaza bases dañadas o relaciones inválidas sin corregir sus datos."""
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("La verificación de integridad falló.")
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("Existen relaciones inválidas; se canceló la actualización.")


def validate_legacy_tasks(connection: sqlite3.Connection) -> None:
    """Comprueba que la migración puede conservar el esquema y sus relaciones."""
    invalid_task = connection.execute(
        "SELECT 1 FROM Tareas WHERE estado NOT IN (?, ?, ?, ?) OR estado IS NULL",
        ("pendiente", "en_progreso", "completada", "cancelada"),
    ).fetchone()
    if invalid_task is not None:
        raise ValueError(
            "Hay estados históricos inválidos; revisarlos antes de migrar."
        )

    custom_schema = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE tbl_name = ? "
        "AND type IN ('index', 'trigger')", ("Tareas",),
    ).fetchone()
    if custom_schema is not None:
        raise ValueError(
            "Tareas tiene índices o triggers adicionales; revisar el esquema."
        )

    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    for table in tables:
        # El nombre de tabla se pasa como parámetro, igual que los demás valores.
        reference = connection.execute(
            'SELECT 1 FROM pragma_foreign_key_list(?) WHERE "table" = ?',
            (table["name"], "Tareas"),
        ).fetchone()
        if reference is not None:
            raise ValueError(
                "Hay tablas que referencian Tareas; revisar el esquema."
            )


def create_backup(database_path: Path) -> Path:
    """Copia toda la base antes de modificarla y comprueba el respaldo."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    backup_path = database_path.with_name(
        f"{database_path.stem}.backup-tasks-{stamp}-{suffix}.db"
    )
    source_uri = database_path.as_uri() + "?mode=rw"

    # Usa otra conexión de lectura mientras migrate mantiene bloqueadas escrituras.
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(backup_path)) as backup:
            source.backup(backup)
            check_integrity(backup)
    return backup_path


def replace_task_table(connection: sqlite3.Connection) -> None:
    """Copia y verifica las tareas antes de permitir una asignación opcional."""
    original_tasks = connection.execute(
        "SELECT * FROM Tareas ORDER BY id"
    ).fetchall()
    original_sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", ("Tareas",)
    ).fetchone()

    temporary_table_sql = TASK_TABLE_SQL.replace(
        "CREATE TABLE Tareas", "CREATE TABLE Tareas_etapa4", 1
    )
    connection.execute(temporary_table_sql)
    connection.execute("""
        INSERT INTO Tareas_etapa4 (
            id, titulo, descripcion, fecha_creacion,
            fecha_vencimiento, estado, usuario_id, materia_id
        )
        SELECT id, titulo, descripcion, fecha_creacion,
               fecha_vencimiento, estado, usuario_id, materia_id
        FROM Tareas
    """)

    copied_tasks = connection.execute("""
        SELECT id, titulo, descripcion, fecha_creacion,
               fecha_vencimiento, estado, usuario_id, materia_id
        FROM Tareas_etapa4
        ORDER BY id
    """).fetchall()
    if copied_tasks != original_tasks:
        raise ValueError(
            "La copia de tareas no coincide; se canceló la actualización."
        )

    # SQLite exige sustituir la tabla para quitar NOT NULL de usuario_id.
    # La copia ya está verificada y migrate revierte todo si hay un error.
    connection.execute("DROP TABLE Tareas")
    connection.execute("ALTER TABLE Tareas_etapa4 RENAME TO Tareas")

    # Conserva también los IDs de tareas que se habían eliminado anteriormente.
    if original_sequence is not None:
        connection.execute(
            "DELETE FROM sqlite_sequence WHERE name = ?", ("Tareas",)
        )
        connection.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
            ("Tareas", original_sequence["seq"]),
        )


def migrate(database_path: Path) -> Path | None:
    """Permite asignación opcional y añade metadatos sin inventar historia."""
    database_path = database_path.resolve()
    uri = database_path.as_uri() + "?mode=rw"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            # El bloqueo evita cambios entre el respaldo y la actualización.
            connection.execute("BEGIN IMMEDIATE")
            columns = connection.execute("PRAGMA table_info(Tareas)").fetchall()
            column_names = tuple(column["name"] for column in columns)
            check_integrity(connection)

            if column_names == LEGACY_COLUMNS + NEW_COLUMNS:
                for column in columns:
                    if column["name"] == "usuario_id" and not column["notnull"]:
                        connection.rollback()
                        return None  # Ya tiene el esquema de la etapa 4.

            if column_names != LEGACY_COLUMNS:
                raise ValueError(
                    "El esquema de Tareas no es el heredado compatible."
                )

            validate_legacy_tasks(connection)
            backup_path = create_backup(database_path)
            replace_task_table(connection)
            check_integrity(connection)
            connection.commit()
            return backup_path
        except Exception:
            connection.rollback()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    backup = migrate(parser.parse_args().database)
    if backup:
        print(f"Actualización terminada. Respaldo: {backup}")
    else:
        print("Tareas ya está actualizada; no se realizaron cambios.")
