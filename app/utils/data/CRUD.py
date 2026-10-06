"""Acceso SQL sin respuestas HTTP.

Crear devuelve un ID; modificar/eliminar devuelve filas afectadas (0 si no existe).
Consultar devuelve dict, None o lista. Los errores sqlite3 se propagan después del
rollback: IntegrityError para restricciones y OperationalError para fallos de acceso.
"""

from datetime import datetime, timezone
import sqlite3
from typing import Any

from werkzeug.security import generate_password_hash

from app.utils.data.database import get_connection
from app.models import MAX_PAYMENT_CENTS, PAYMENT_CURRENCIES, PAYMENT_METHODS


USER_FIELDS = "id, nombre, correo, telefono, rol, activo, fecha_creacion"

# LEFT JOIN conserva las tareas aunque no tengan asignado, creador o materia.
TASK_SELECT = """
    SELECT task.*,
           assigned_user.nombre AS usuario_asignado_nombre,
           creator.nombre AS creador_nombre,
           subject.nombre AS materia_nombre
    FROM Tareas AS task
    LEFT JOIN Usuarios AS assigned_user ON assigned_user.id = task.usuario_id
    LEFT JOIN Usuarios AS creator ON creator.id = task.creador_id
    LEFT JOIN Materias AS subject ON subject.id = task.materia_id
"""

PAYMENT_SELECT = """
    SELECT payment.*, recipient.nombre AS receptor_nombre, task.titulo AS tarea_titulo,
           CASE WHEN payment.tarea_id IS NULL OR payment.moneda IS NULL
                     OR payment.estado IS NULL OR payment.metodo IS NULL
                     OR payment.monto <= 0
                THEN 1 ELSE 0 END AS pendiente_completar
    FROM Pagos AS payment
    JOIN Usuarios AS recipient ON recipient.id = payment.usuario_id
    LEFT JOIN Tareas AS task ON task.id = payment.tarea_id
"""


# Estas funciones comparten la conexión y evitan repetir commit y rollback.


def _insert(sql: str, parameters: tuple) -> int:
    """Ejecuta un INSERT y devuelve el identificador creado."""
    with get_connection() as connection:
        cursor = connection.execute(sql, parameters)
        return cursor.lastrowid


def _modify(sql: str, parameters: tuple) -> int:
    """Ejecuta un UPDATE o DELETE y devuelve cuántas filas cambiaron."""
    with get_connection() as connection:
        return connection.execute(sql, parameters).rowcount


def _fetch_one(sql: str, parameters: tuple) -> dict[str, Any] | None:
    """Convierte una fila SQLite en un diccionario, si existe."""
    with get_connection() as connection:
        row = connection.execute(sql, parameters).fetchone()
    if row is None:
        return None
    return dict(row)


def _fetch_all(sql: str, parameters: tuple = ()) -> list[dict[str, Any]]:
    """Convierte las filas SQLite en una lista de diccionarios."""
    with get_connection() as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [dict(row) for row in rows]


def _current_utc_time() -> str:
    """Devuelve la fecha y hora UTC usada para registrar tareas y pagos."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# Usuarios


def create_user(nombre: str, correo: str, contrasena: str,
                telefono: str | None, rol: str, activo: int = 1) -> int:
    """Crea un usuario con hash de contraseña y devuelve su ID."""
    return _insert(
        "INSERT INTO Usuarios (nombre, correo, contrasena, telefono, rol, activo) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (nombre, correo, generate_password_hash(contrasena), telefono, rol, activo),
    )


def update_user(id: int, nombre: str, correo: str, contrasena: str | None,
                telefono: str | None, rol: str, activo: int = 1) -> int:
    """Actualiza el usuario; None conserva el hash de contraseña actual."""
    if contrasena is None:
        return _modify(
            "UPDATE Usuarios SET nombre = ?, correo = ?, telefono = ?, rol = ?, "
            "activo = ? WHERE id = ?", (nombre, correo, telefono, rol, activo, id),
        )
    return _modify(
        "UPDATE Usuarios SET nombre = ?, correo = ?, contrasena = ?, "
        "telefono = ?, rol = ?, activo = ? WHERE id = ?",
        (nombre, correo, generate_password_hash(contrasena), telefono, rol, activo, id),
    )


def delete_user(id: int) -> int:
    """Elimina un usuario si las claves foráneas lo permiten."""
    return _modify("DELETE FROM Usuarios WHERE id = ?", (id,))


def get_all_users() -> list[dict[str, Any]]:
    """Lista usuarios sin contraseñas ni hashes."""
    return _fetch_all(f"SELECT {USER_FIELDS} FROM Usuarios ORDER BY id")


def get_user_by_id(id: int) -> dict[str, Any] | None:
    """Consulta datos públicos por ID; devuelve None si no existe."""
    return _fetch_one(f"SELECT {USER_FIELDS} FROM Usuarios WHERE id = ?", (id,))


def get_user_by_email(correo: str) -> dict[str, Any] | None:
    """Consulta datos públicos por correo, sin credenciales."""
    return _fetch_one(
        f"SELECT {USER_FIELDS} FROM Usuarios WHERE correo = ? COLLATE NOCASE", (correo,)
    )


def get_user_for_auth_by_email(correo: str) -> dict[str, Any] | None:
    """Consulta interna con hash; nunca pasar este resultado a una respuesta."""
    return _fetch_one(
        f"SELECT {USER_FIELDS}, contrasena FROM Usuarios "
        "WHERE correo = ? COLLATE NOCASE",
        (correo,),
    )


def create_first_admin(nombre: str, correo: str, contrasena: str) -> int:
    """Crea el primer administrador activo, sin promover cuentas existentes."""
    password_hash = generate_password_hash(contrasena)
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM Usuarios WHERE rol = 'admin' AND activo = 1"
        ).fetchone():
            raise ValueError("Ya existe un administrador activo.")
        if connection.execute(
            "SELECT 1 FROM Usuarios WHERE correo = ? COLLATE NOCASE", (correo,)
        ).fetchone():
            raise ValueError("Ese correo ya pertenece a una cuenta existente.")
        cursor = connection.execute(
            "INSERT INTO Usuarios (nombre, correo, contrasena, rol) "
            "VALUES (?, ?, ?, 'admin')", (nombre, correo, password_hash)
        )
        return cursor.lastrowid


# Tareas: usuario_id es el asignado; creador_id es quien la creó.


def create_task(titulo: str, descripcion: str | None,
                fecha_vencimiento: str | None, estado: str,
                usuario_id: int | None, materia_id: int | None, *,
                prioridad: str = "media", creador_id: int | None = None) -> int:
    """Crea una tarea; usuario_id identifica al asignado, no al creador."""
    now = _current_utc_time()
    return _insert(
        "INSERT INTO Tareas (titulo, descripcion, fecha_vencimiento, estado, "
        "usuario_id, materia_id, prioridad, creador_id, fecha_creacion, "
        "fecha_actualizacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id,
         prioridad, creador_id, now, now),
    )


def update_task(id: int, titulo: str, descripcion: str | None,
                fecha_vencimiento: str | None, estado: str,
                usuario_id: int | None, materia_id: int | None, *,
                prioridad: str = "media") -> int:
    """Actualiza contenido y asignación; conserva el creador y fecha de alta."""
    updated_at = _current_utc_time()
    return _modify(
        "UPDATE Tareas SET titulo = ?, descripcion = ?, fecha_vencimiento = ?, "
        "estado = ?, usuario_id = ?, materia_id = ?, prioridad = ?, "
        "fecha_actualizacion = ? WHERE id = ?",
        (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id,
         prioridad, updated_at, id),
    )


def update_task_status(task_id: int, assigned_user_id: int, estado: str) -> int:
    """Cambia solo el estado de una tarea todavía asignada a ese miembro."""
    updated_at = _current_utc_time()
    return _modify(
        "UPDATE Tareas SET estado = ?, fecha_actualizacion = ? "
        "WHERE id = ? AND usuario_id = ?",
        (estado, updated_at, task_id, assigned_user_id),
    )


def delete_task(id: int) -> int:
    """Elimina sin cascadas; protege también una futura relación de pagos."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        payment_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(Pagos)")
        }
        # También admite la base anterior a migrate-payments, sin inventar relaciones.
        if "tarea_id" in payment_columns:
            payment = connection.execute(
                "SELECT 1 FROM Pagos WHERE tarea_id = ?", (id,)
            ).fetchone()
            if payment is not None:
                raise sqlite3.IntegrityError("La tarea tiene pagos asociados.")

        cursor = connection.execute("DELETE FROM Tareas WHERE id = ?", (id,))
        return cursor.rowcount


def get_task_by_id(id: int) -> dict[str, Any] | None:
    """Consulta una tarea por ID."""
    return _fetch_one(TASK_SELECT + "WHERE task.id = ?", (id,))


def get_all_tasks() -> list[dict[str, Any]]:
    """Lista tareas en orden estable; los permisos corresponden a las rutas."""
    return _fetch_all(TASK_SELECT + "ORDER BY task.id")


def get_tasks_by_user(usuario_id: int) -> list[dict[str, Any]]:
    """Lista exclusivamente las tareas asignadas al usuario indicado."""
    return _fetch_all(
        TASK_SELECT + "WHERE task.usuario_id = ? ORDER BY task.id", (usuario_id,)
    )


# Materias: se conservan las operaciones existentes.


def get_all_subjects() -> list[dict[str, Any]]:
    """Lista materias existentes para conservar la relación al editar tareas."""
    return _fetch_all("SELECT id, nombre FROM Materias ORDER BY nombre, id")


def get_subject_by_id(subject_id: int) -> dict[str, Any] | None:
    """Consulta una materia existente sin ampliar su gestión."""
    return _fetch_one("SELECT id, nombre FROM Materias WHERE id = ?", (subject_id,))


def create_subject(nombre: str, descripcion: str | None) -> int:
    """Conserva el alta de materias y devuelve su ID."""
    return _insert(
        "INSERT INTO Materias (nombre, descripcion) VALUES (?, ?)",
        (nombre, descripcion),
    )


# Pagos: monto representa centavos en la moneda indicada en cada registro.


def validate_payment_data(connection, usuario_id, monto_centavos, tarea_id,
                          moneda, metodo, estado, notas) -> None:
    """Comprueba reglas dentro de la transacción para evitar relaciones obsoletas."""
    if type(monto_centavos) is not int or not 1 <= monto_centavos <= MAX_PAYMENT_CENTS:
        raise ValueError("El monto debe ser un entero positivo en centavos.")
    if moneda not in PAYMENT_CURRENCIES or metodo not in PAYMENT_METHODS:
        raise ValueError("Selecciona una moneda y un método válidos.")
    if estado not in {"pendiente", "pagado"}:
        raise ValueError("El estado no es válido para guardar un pago.")
    if notas is not None and len(notas) > 2000:
        raise ValueError("Las notas admiten hasta 2000 caracteres.")

    task = connection.execute(
        "SELECT estado FROM Tareas WHERE id = ?", (tarea_id,)
    ).fetchone()
    recipient = connection.execute(
        "SELECT activo FROM Usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    if task is None or task["estado"] == "cancelada":
        raise ValueError("Selecciona una tarea existente que no esté cancelada.")
    if recipient is None or recipient["activo"] != 1:
        raise ValueError("Selecciona un usuario receptor activo existente.")


def create_payment(usuario_id: int, monto_centavos: int, tarea_id: int,
                   moneda: str, metodo: str, estado: str = "pendiente",
                   notas: str | None = None) -> int:
    """Registra un pago nuevo; no cobra ni transfiere dinero."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        validate_payment_data(
            connection, usuario_id, monto_centavos, tarea_id,
            moneda, metodo, estado, notas,
        )
        now = _current_utc_time()
        paid_at = now if estado == "pagado" else None
        cursor = connection.execute(
            "INSERT INTO Pagos (usuario_id, monto, fecha, tarea_id, moneda, estado, "
            "metodo, fecha_pago, notas, fecha_creacion) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (usuario_id, monto_centavos, now, tarea_id, moneda, estado,
             metodo, paid_at, notas, now),
        )
        return cursor.lastrowid


def update_payment(payment_id: int, usuario_id: int, monto_centavos: int,
                   tarea_id: int, moneda: str, metodo: str, estado: str,
                   notas: str | None = None) -> int:
    """Edita pagos pendientes o completa datos históricos sin borrar su origen."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        payment = connection.execute(
            "SELECT * FROM Pagos WHERE id = ?", (payment_id,)
        ).fetchone()
        if payment is None:
            return 0
        if payment["estado"] in {"pagado", "anulado"}:
            raise ValueError(
                "Los datos de un pago pagado o anulado no se pueden modificar."
            )
        validate_payment_data(
            connection, usuario_id, monto_centavos, tarea_id,
            moneda, metodo, estado, notas,
        )
        paid_at = _current_utc_time() if estado == "pagado" else None
        return connection.execute(
            "UPDATE Pagos SET usuario_id = ?, monto = ?, tarea_id = ?, moneda = ?, "
            "metodo = ?, estado = ?, fecha_pago = ?, notas = ? WHERE id = ?",
            (usuario_id, monto_centavos, tarea_id, moneda, metodo,
             estado, paid_at, notas, payment_id),
        ).rowcount


def update_payment_notes(payment_id: int, notas: str | None) -> int:
    """Permite corregir notas de un pago pagado; conserva sus datos económicos."""
    if notas is not None and len(notas) > 2000:
        raise ValueError("Las notas admiten hasta 2000 caracteres.")
    return _modify(
        "UPDATE Pagos SET notas = ? WHERE id = ? AND estado = 'pagado'",
        (notas, payment_id),
    )


def annul_payment(payment_id: int) -> int:
    """Anula sin borrar el registro, el importe ni la fecha de pago existente."""
    return _modify(
        "UPDATE Pagos SET estado = 'anulado' WHERE id = ? "
        "AND (estado IS NULL OR estado != 'anulado')", (payment_id,),
    )


def get_payment_by_id(id: int) -> dict[str, Any] | None:
    """Consulta un pago; monto siempre está en centavos después de migrar."""
    return _fetch_one(PAYMENT_SELECT + "WHERE payment.id = ?", (id,))


def get_all_payments() -> list[dict[str, Any]]:
    """Lista pagos con tarea, receptor y advertencia de información pendiente."""
    return _fetch_all(PAYMENT_SELECT + "ORDER BY payment.id")


def get_payments_by_user(usuario_id: int) -> list[dict[str, Any]]:
    """Consulta pagos asociados a un usuario."""
    return _fetch_all(
        PAYMENT_SELECT + "WHERE payment.usuario_id = ? ORDER BY payment.id", (usuario_id,)
    )


# Asistencias: se conservan las operaciones existentes.


def create_attendance(usuario_id: int) -> int:
    """Conserva el alta de asistencias y devuelve su ID."""
    return _insert("INSERT INTO Asistencias (usuario_id) VALUES (?)", (usuario_id,))


def update_attendance(id: int, usuario_id: int) -> int:
    """Actualiza una asistencia y devuelve las filas afectadas."""
    return _modify(
        "UPDATE Asistencias SET usuario_id = ? WHERE id = ?", (usuario_id, id)
    )


def delete_attendance(id: int) -> int:
    """Elimina una asistencia y devuelve las filas afectadas."""
    return _modify("DELETE FROM Asistencias WHERE id = ?", (id,))
