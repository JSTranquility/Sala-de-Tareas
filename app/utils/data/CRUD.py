"""Acceso SQL sin respuestas HTTP.

Crear devuelve un ID; modificar/eliminar devuelve filas afectadas (0 si no existe).
Consultar devuelve dict, None o lista. Los errores sqlite3 se propagan después del
rollback: IntegrityError para restricciones y OperationalError para fallos de acceso.
"""

from typing import Any

from werkzeug.security import generate_password_hash

from app.utils.data.database import get_connection


USER_FIELDS = "id, nombre, correo, telefono, rol, activo, fecha_creacion"


def _insert(sql: str, parameters: tuple) -> int:
    with get_connection() as connection:
        cursor = connection.execute(sql, parameters)
        return cursor.lastrowid


def _modify(sql: str, parameters: tuple) -> int:
    with get_connection() as connection:
        return connection.execute(sql, parameters).rowcount


def _fetch_one(sql: str, parameters: tuple) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(sql, parameters).fetchone()
    return dict(row) if row is not None else None


def _fetch_all(sql: str, parameters: tuple = ()) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [dict(row) for row in rows]


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
        f"SELECT {USER_FIELDS}, contrasena FROM Usuarios WHERE correo = ? COLLATE NOCASE",
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
        return connection.execute(
            "INSERT INTO Usuarios (nombre, correo, contrasena, rol) "
            "VALUES (?, ?, ?, 'admin')", (nombre, correo, password_hash)
        ).lastrowid


def create_task(titulo: str, descripcion: str | None,
                fecha_vencimiento: str | None, estado: str,
                usuario_id: int, materia_id: int | None) -> int:
    """Crea una tarea con el esquema actual y devuelve su ID."""
    return _insert(
        "INSERT INTO Tareas (titulo, descripcion, fecha_vencimiento, estado, "
        "usuario_id, materia_id) VALUES (?, ?, ?, ?, ?, ?)",
        (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id),
    )


def update_task(id: int, titulo: str, descripcion: str | None,
                fecha_vencimiento: str | None, estado: str,
                usuario_id: int, materia_id: int | None) -> int:
    """Actualiza una tarea y devuelve las filas afectadas."""
    return _modify(
        "UPDATE Tareas SET titulo = ?, descripcion = ?, fecha_vencimiento = ?, "
        "estado = ?, usuario_id = ?, materia_id = ? WHERE id = ?",
        (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id, id),
    )


def delete_task(id: int) -> int:
    """Elimina una tarea y devuelve las filas afectadas."""
    return _modify("DELETE FROM Tareas WHERE id = ?", (id,))


def get_task_by_id(id: int) -> dict[str, Any] | None:
    """Consulta una tarea por ID."""
    return _fetch_one("SELECT * FROM Tareas WHERE id = ?", (id,))


def get_all_tasks() -> list[dict[str, Any]]:
    """Lista tareas en orden estable; los permisos corresponden a las rutas."""
    return _fetch_all("SELECT * FROM Tareas ORDER BY id")


def get_tasks_by_user(usuario_id: int) -> list[dict[str, Any]]:
    """Consulta la relación usuario-tarea existente sin reinterpretarla."""
    return _fetch_all(
        "SELECT * FROM Tareas WHERE usuario_id = ? ORDER BY id", (usuario_id,)
    )


def create_subject(nombre: str, descripcion: str | None) -> int:
    """Conserva el alta de materias y devuelve su ID."""
    return _insert(
        "INSERT INTO Materias (nombre, descripcion) VALUES (?, ?)",
        (nombre, descripcion),
    )


def create_payment(usuario_id: int, monto: Any) -> int:
    """Alta heredada: monto sigue en unidades monetarias, no en centavos.

    La conversión del esquema REAL y las reglas de pagos quedan para la etapa 5.
    Esta función no se expone mediante una ruta.
    """
    return _insert(
        "INSERT INTO Pagos (usuario_id, monto) VALUES (?, ?)", (usuario_id, monto)
    )


def get_payment_by_id(id: int) -> dict[str, Any] | None:
    """Consulta un pago del esquema existente."""
    return _fetch_one("SELECT * FROM Pagos WHERE id = ?", (id,))


def get_all_payments() -> list[dict[str, Any]]:
    """Lista pagos sin cambiar su representación monetaria."""
    return _fetch_all("SELECT * FROM Pagos ORDER BY id")


def get_payments_by_user(usuario_id: int) -> list[dict[str, Any]]:
    """Consulta pagos asociados a un usuario."""
    return _fetch_all(
        "SELECT * FROM Pagos WHERE usuario_id = ? ORDER BY id", (usuario_id,)
    )


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
