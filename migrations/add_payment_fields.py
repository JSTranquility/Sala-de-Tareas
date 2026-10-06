"""Convierte pagos heredados a centavos con respaldo y sin inventar relaciones."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sqlite3
import uuid

from app.models import MAX_PAYMENT_CENTS
from app.utils.data.database import PAYMENT_TABLE_SQL
from migrations.add_task_fields import check_integrity


LEGACY_COLUMNS = ("id", "usuario_id", "monto", "fecha")
NEW_COLUMNS = (
    "tarea_id", "moneda", "estado", "metodo", "fecha_pago", "notas",
    "fecha_creacion", "monto_original",
)


def legacy_amount_to_cents(amount) -> tuple[int, str]:
    """Redondea importes heredados con ROUND_HALF_UP y conserva su valor textual."""
    original_amount = str(amount)
    try:
        decimal_amount = Decimal(original_amount)
        if not decimal_amount.is_finite():
            raise ValueError("Hay importes históricos no finitos; revisarlos antes de migrar.")
        cents = int((decimal_amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(
            "Hay importes históricos inválidos; revisarlos antes de migrar."
        ) from error
    if abs(cents) > MAX_PAYMENT_CENTS:
        raise ValueError("Un importe histórico supera el límite de SQLite.")
    return cents, original_amount


def validate_legacy_schema(connection: sqlite3.Connection) -> None:
    """Evita perder índices, triggers o referencias personalizados."""
    custom_schema = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE tbl_name = ? "
        "AND type IN ('index', 'trigger')", ("Pagos",),
    ).fetchone()
    if custom_schema is not None:
        raise ValueError("Pagos tiene índices o triggers adicionales; revisar el esquema.")
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    for table in tables:
        reference = connection.execute(
            'SELECT 1 FROM pragma_foreign_key_list(?) WHERE "table" = ?',
            (table["name"], "Pagos"),
        ).fetchone()
        if reference is not None:
            raise ValueError("Hay tablas que referencian Pagos; revisar el esquema.")
    task_columns = {row["name"] for row in connection.execute("PRAGMA table_info(Tareas)")}
    if "creador_id" not in task_columns:
        raise ValueError("Actualiza primero las tareas con migrate-tasks.")


def create_backup(database_path: Path) -> Path:
    """Guarda un respaldo completo mientras migrate bloquea otras escrituras."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    backup_path = database_path.with_name(
        f"{database_path.stem}.backup-payments-{stamp}-{suffix}.db"
    )
    source_uri = database_path.as_uri() + "?mode=rw"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(backup_path)) as backup:
            source.backup(backup)
            check_integrity(backup)
    return backup_path


def replace_payment_table(connection: sqlite3.Connection, payments: list) -> None:
    """Copia los importes convertidos y verifica cada registro antes de reemplazar."""
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", ("Pagos",)
    ).fetchone()
    connection.execute(PAYMENT_TABLE_SQL.replace(
        "CREATE TABLE Pagos", "CREATE TABLE Pagos_etapa5", 1
    ))
    connection.executemany(
        "INSERT INTO Pagos_etapa5 (id, usuario_id, monto, fecha, fecha_creacion, "
        "monto_original) VALUES (?, ?, ?, ?, ?, ?)", payments,
    )
    copied = connection.execute(
        "SELECT id, usuario_id, monto, fecha, fecha_creacion, monto_original "
        "FROM Pagos_etapa5 ORDER BY id"
    ).fetchall()
    if [tuple(row) for row in copied] != payments:
        raise ValueError("La copia de pagos no coincide; se canceló la actualización.")

    # SQLite requiere sustituir la tabla para cambiar REAL a INTEGER y restringirlo.
    # La copia está verificada y migrate revierte todo si ocurre un error.
    connection.execute("DROP TABLE Pagos")
    connection.execute("ALTER TABLE Pagos_etapa5 RENAME TO Pagos")
    if sequence is not None:
        connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", ("Pagos",))
        connection.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
            ("Pagos", sequence["seq"]),
        )


def migrate(database_path: Path) -> Path | None:
    """Actualiza explícitamente, conserva fechas y deja los datos desconocidos vacíos."""
    database_path = database_path.resolve()
    uri = database_path.as_uri() + "?mode=rw"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            columns = connection.execute("PRAGMA table_info(Pagos)").fetchall()
            column_names = tuple(column["name"] for column in columns)
            check_integrity(connection)
            if column_names == LEGACY_COLUMNS + NEW_COLUMNS:
                if columns[2]["type"].upper() == "INTEGER":
                    connection.rollback()
                    return None
            if column_names != LEGACY_COLUMNS:
                raise ValueError("El esquema de Pagos no es el heredado compatible.")
            validate_legacy_schema(connection)

            converted_payments = []
            for payment in connection.execute("SELECT * FROM Pagos ORDER BY id"):
                cents, original_amount = legacy_amount_to_cents(payment["monto"])
                converted_payments.append((
                    payment["id"], payment["usuario_id"], cents, payment["fecha"],
                    payment["fecha"], original_amount,
                ))

            backup_path = create_backup(database_path)
            replace_payment_table(connection, converted_payments)
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
        print("Pagos ya está actualizada; no se realizaron cambios.")
