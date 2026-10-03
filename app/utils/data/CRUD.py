from flask import jsonify

from app.utils.database import get_connection
#Funciones CRUD para la aplicacion

#Crear usuario
def create_user(nombre, correo, contrasena, telefono, rol):
    with get_connection() as connection:
        connection.execute('''INSERT INTO Usuarios (nombre, correo, contrasena, telefono, rol) VALUES (?, ?, ?, ?, ?)''',
                           (nombre, correo, contrasena, telefono, rol))

#Actualizar usuario
def update_user(id, nombre, correo, contrasena, telefono, rol):
    try:
        with get_connection() as connection:
            cursor = connection.execute('''UPDATE Usuarios SET nombre = ?, correo = ?, contrasena = ?, telefono = ?, rol = ? WHERE id = ?''',
                                         (nombre, correo, contrasena, telefono, rol, id))
            return cursor.rowcount
    except Exception as e:
        print(f"Error updating user: {e}")
        return 0

#Eliminar usuario
def delete_user(id):
    try:
        with get_connection() as connection:
            cursor = connection.execute('''DELETE FROM Usuarios WHERE id = ?''', (id,))
            return cursor.rowcount
    except Exception as e:
        print(f"Error borrando el usuario: {e}")
        return 0

#Mirar usuarios 
def get_all_users():
    with get_connection() as connection:
        users = connection.execute('''SELECT * FROM Usuarios''').fetchall()
    return jsonify([dict(row) for row in users])

#Crear tarea
def create_task(titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id):
    try:
        with get_connection() as connection:
            connection.execute('''INSERT INTO Tareas (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id) VALUES (?, ?, ?, ?, ?, ?)''',
                               (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id))
    except Exception as e:
        print(f"Error creando la tarea: {e}")

#Actualizar tarea
def update_task(id, titulo, descripcion, fecha_vencimiento, estado, usuario_id,
                    materia_id):
        try:
            with get_connection() as connection:
                cursor = connection.execute('''UPDATE Tareas SET titulo = ?, descripcion = ?, fecha_vencimiento = ?, estado = ?, usuario_id = ?, materia_id = ? WHERE id = ?''',
                                             (titulo, descripcion, fecha_vencimiento, estado, usuario_id, materia_id, id))
                return cursor.rowcount
        except Exception as e:
            print(f"Error actualizando la tarea: {e}")
            return 0

#Eliminar tarea
def delete_task(id):
    try:
        with get_connection() as connection:
            cursor = connection.execute('''DELETE FROM Tareas WHERE id = ?''', (id,))
            return cursor.rowcount
    except Exception as e:
        print(f"Error borrando la tarea: {e}")
        return 0

#Añadir materia
def create_subject(nombre, descripcion):
    try:
        with get_connection() as connection:
            connection.execute('''INSERT INTO Materias (nombre, descripcion) VALUES (?, ?)''',
                               (nombre, descripcion))
    except Exception as e:
        print(f"Error creando la materia: {e}")

#Añadir pago
def create_payment(usuario_id, monto):
    try:
        with get_connection() as connection:
            connection.execute('''INSERT INTO Pagos (usuario_id, monto) VALUES (?, ?)''',
                               (usuario_id, monto))
    except Exception as e:
        print(f"Error creando el pago: {e}")

#Añadir asistencia
def create_attendance(usuario_id):
    try:
        with get_connection() as connection:
            connection.execute('''INSERT INTO Asistencias (usuario_id) VALUES (?)''',
                               (usuario_id,))
    except Exception as e:
        print(f"Error añadiendo la asistencia: {e}")

#Editar asistencia
def update_attendance(id, usuario_id):
    try:
        with get_connection() as connection:
            cursor = connection.execute('''UPDATE Asistencias SET usuario_id = ? WHERE id = ?''',
                                         (usuario_id, id))
            return cursor.rowcount
    except Exception as e:
        print(f"Error actualizando la asistencia: {e}")
        return 0

#Eliminar asistencia
def delete_attendance(id):
    try:
        with get_connection() as connection:
            cursor = connection.execute('''DELETE FROM Asistencias WHERE id = ?''', (id,))
            return cursor.rowcount
    except Exception as e:
        print(f"Error borrando la asistencia: {e}")
        return 0

def get_user_by_email(correo):
    with get_connection() as connection:
        return connection.execute('''SELECT * FROM Usuarios WHERE correo = ?''', (correo,)).fetchone()
