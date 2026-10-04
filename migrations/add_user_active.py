"""Actualización explícita de Usuarios con respaldo previo; no convierte claves."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid


def migrate(database_path: Path) -> Path | None:
    """Añade activo de forma transaccional y devuelve la ubicación del respaldo."""
    database_path = database_path.resolve()
    connection = sqlite3.connect(database_path.as_uri() + "?mode=rw", uri=True)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(Usuarios)")}
        if not columns:
            raise ValueError("No existe la tabla Usuarios; inicializa primero la base.")
        if "activo" in columns:
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = database_path.with_name(
            f"{database_path.stem}.backup-{stamp}-{uuid.uuid4().hex[:8]}.db"
        )
        with closing(sqlite3.connect(backup_path)) as backup:
            connection.backup(backup)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "ALTER TABLE Usuarios ADD COLUMN activo INTEGER NOT NULL "
            "DEFAULT 1 CHECK (activo IN (0, 1))"
        )
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("La verificación de integridad falló.")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Existen relaciones inválidas; se canceló la actualización.")
        connection.commit()
        return backup_path
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    backup = migrate(arguments.database)
    print(f"Actualización terminada. Respaldo: {backup}" if backup
          else "La columna activo ya existe; no se realizaron cambios.")
