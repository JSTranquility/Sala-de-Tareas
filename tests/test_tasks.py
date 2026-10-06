from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.security import generate_password_hash

from app.routes import register_routes
from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection, initialize_database
from migrations.add_task_fields import migrate
from migrations.add_task_fields import check_integrity


LEGACY_TASK_SQL = """CREATE TABLE Tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL, descripcion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento TIMESTAMP, estado TEXT NOT NULL,
    usuario_id INTEGER NOT NULL, materia_id INTEGER,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id),
    FOREIGN KEY (materia_id) REFERENCES Materias(id)
)"""


class TaskTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "tasks.db"
        self.app = Flask(__name__, template_folder=str(Path("app/templates").resolve()))
        self.app.config.update(TESTING=True, SECRET_KEY="solo-pruebas",
                               DATABASE_PATH=str(self.path))
        register_routes(self.app)
        with self.app.app_context():
            initialize_database()
            with get_connection() as connection:
                password_hash = generate_password_hash("clave-pruebas", method="pbkdf2:sha256:1000")
                connection.executemany(
                    "INSERT INTO Usuarios (id, nombre, correo, contrasena, rol, activo) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [(1, "Admin", "admin@example.test", password_hash, "admin", 1),
                     (2, "Ana", "ana@example.test", password_hash, "member", 1),
                     (3, "Luis", "luis@example.test", password_hash, "member", 1),
                     (4, "Inactivo", "inactive@example.test", password_hash, "member", 0)],
                )
            self.subject_id = crud.create_subject("Matemáticas", "Conservar")
            self.task_id = crud.create_task("Tarea de Ana", "Resolver ejercicios", "2026-11-01",
                                            "pendiente", 2, self.subject_id, creador_id=1)
            self.other_id = crud.create_task("Tarea de Luis", None, None, "pendiente", 3,
                                             None, creador_id=1)
            self.unassigned_id = crud.create_task("Sin asignación", None, None, "pendiente",
                                                  None, None, creador_id=1)
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def authenticate(self, user_id=1):
        # Autenticación real se cubre en test_users_auth; aquí se prueban permisos.
        with self.client.session_transaction() as session:
            session.clear()
            session.update(user_id=user_id, csrf_token="token-de-pruebas")

    def post(self, path, data=None, **kwargs):
        return self.client.post(path, data={"csrf_token": "token-de-pruebas", **(data or {})},
                                **kwargs)

    def task_data(self, **changes):
        values = dict(titulo="Nueva tarea", descripcion="Descripción", estado="pendiente",
                      prioridad="alta", fecha_vencimiento="2026-12-01",
                      usuario_asignado_id="2", materia_id=str(self.subject_id))
        values.update(changes)
        return values

    def read_task(self, task_id=None):
        with self.app.app_context():
            return crud.get_task_by_id(task_id or self.task_id)


class TasksTests(TaskTestCase):
    def test_admin_complete_crud_and_creator_cannot_be_forged(self):
        self.authenticate()
        self.assertEqual(self.client.get("/tasks/new").status_code, 200)
        response = self.post("/tasks/new", self.task_data(creador_id="3", usuario_id="3"))
        self.assertEqual(response.status_code, 302)
        task_id = int(response.location.rsplit("/", 1)[1])
        task = self.read_task(task_id)
        self.assertEqual((task["creador_id"], task["usuario_id"], task["prioridad"]), (1, 2, "alta"))
        self.assertEqual(task["materia_id"], self.subject_id)
        self.assertEqual(task["fecha_creacion"], task["fecha_actualizacion"])
        self.assertEqual(datetime.fromisoformat(task["fecha_creacion"]).tzinfo, timezone.utc)
        for path in (response.location, "/tasks/", f"/tasks/{task_id}/edit"):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn("Nueva tarea", page.get_data(as_text=True))
        detail = self.client.get(response.location).get_data(as_text=True)
        self.assertIn("Usuario asignado", detail)
        self.assertIn("Creado por", detail)
        edited = self.post(f"/tasks/{task_id}/edit", self.task_data(
            titulo="Editada", usuario_asignado_id="3", estado="en_progreso",
            prioridad="baja", creador_id="3"))
        self.assertEqual(edited.status_code, 302)
        updated = self.read_task(task_id)
        self.assertEqual((updated["titulo"], updated["usuario_id"], updated["creador_id"]),
                         ("Editada", 3, 1))
        self.assertEqual(updated["fecha_creacion"], task["fecha_creacion"])
        self.assertGreater(updated["fecha_actualizacion"], task["fecha_actualizacion"])
        self.assertEqual(self.client.get(f"/tasks/{task_id}/delete").status_code, 405)
        self.assertEqual(self.post(f"/tasks/{task_id}/delete").status_code, 302)
        self.assertEqual(self.client.get(f"/tasks/{task_id}").status_code, 404)

    def test_assignment_and_subject_are_optional(self):
        self.authenticate()
        response = self.post("/tasks/new", self.task_data(usuario_asignado_id="", materia_id="",
                                                         fecha_vencimiento=""))
        task = self.read_task(int(response.location.rsplit("/", 1)[1]))
        self.assertIsNone(task["usuario_id"])
        self.assertIsNone(task["materia_id"])
        self.assertIsNone(task["fecha_vencimiento"])
        detail = self.client.get(response.location).get_data(as_text=True)
        self.assertIn("Sin asignar", detail)
        self.assertIn("Sin materia", detail)
        self.assertEqual(self.post(f"/tasks/{self.task_id}/edit", self.task_data(
            usuario_asignado_id="")).status_code, 302)
        self.assertIsNone(self.read_task()["usuario_id"])

    def test_member_lists_and_reads_only_assigned_tasks(self):
        self.authenticate(2)
        page = self.client.get("/tasks/")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Tarea de Ana", html)
        self.assertNotIn("Tarea de Luis", html)
        self.assertNotIn("Sin asignación", html)
        self.assertNotIn("Crear tarea", html)
        self.assertEqual(self.client.get(f"/tasks/{self.task_id}").status_code, 200)
        for task_id in (self.other_id, self.unassigned_id):
            self.assertEqual(self.client.get(f"/tasks/{task_id}").status_code, 403)
            self.assertEqual(self.client.get(f"/tasks/{task_id}/edit").status_code, 403)
            self.assertEqual(self.post(f"/tasks/{task_id}/edit", {"estado": "completada"}).status_code, 403)

    def test_member_changes_only_state_even_with_forged_fields(self):
        self.authenticate(2)
        original = self.read_task()
        self.assertEqual(self.client.get(f"/tasks/{self.task_id}/edit").status_code, 200)
        response = self.post(f"/tasks/{self.task_id}/edit", self.task_data(
            titulo="Ataque", descripcion="Ataque", usuario_asignado_id="3", usuario_id="3",
            creador_id="2", estado="completada", prioridad="baja", materia_id=""))
        self.assertEqual(response.status_code, 302)
        updated = self.read_task()
        self.assertEqual(updated["estado"], "completada")
        self.assertGreater(updated["fecha_actualizacion"], original["fecha_actualizacion"])
        for key in ("titulo", "descripcion", "usuario_id", "creador_id", "prioridad",
                    "materia_id", "fecha_vencimiento", "fecha_creacion"):
            self.assertEqual(updated[key], original[key])
        for state in ("pendiente", "en_progreso", "cancelada"):
            self.assertEqual(self.post(f"/tasks/{self.task_id}/edit", {"estado": state}).status_code, 302)
        before_invalid = self.read_task()
        for state in ("hecha", "", "<script>"):
            response = self.post(f"/tasks/{self.task_id}/edit", {"estado": state})
            self.assertEqual(response.status_code, 400)
            self.assertIn("Selecciona un estado válido", response.get_data(as_text=True))
        self.assertEqual(self.read_task(), before_invalid)

    def test_member_cannot_create_or_delete(self):
        self.authenticate(2)
        self.assertEqual(self.client.get("/tasks/new").status_code, 403)
        self.assertEqual(self.post("/tasks/new", self.task_data()).status_code, 403)
        self.assertEqual(self.post(f"/tasks/{self.task_id}/delete").status_code, 403)
        self.assertIsNotNone(self.read_task())

    def test_assignment_permissions_refresh_and_inactive_sessions_are_rejected(self):
        self.authenticate(2)
        with self.app.app_context():
            crud.update_task(self.task_id, "Reasignada", None, None, "pendiente", 3, None)
            # La comprobación SQL también impide un cambio con una asignación obsoleta.
            self.assertEqual(crud.update_task_status(self.task_id, 2, "completada"), 0)
        self.assertEqual(self.client.get(f"/tasks/{self.task_id}").status_code, 403)
        self.assertEqual(self.post(f"/tasks/{self.task_id}/edit", {"estado": "completada"}).status_code, 403)
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Usuarios SET activo = 0 WHERE id = ?", (2,))
        self.assertEqual(self.client.get("/tasks/").status_code, 302)
        self.authenticate(1)
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Usuarios SET rol = 'member' WHERE id = ?", (1,))
        self.assertEqual(self.post("/tasks/new", self.task_data()).status_code, 403)

    def test_server_validation_and_relations_do_not_change_data(self):
        self.authenticate()
        cases = [dict(titulo=" "), dict(titulo="x" * 201), dict(descripcion="x" * 5001),
                 dict(estado="inexistente"), dict(prioridad="urgente"),
                 dict(fecha_vencimiento="2026-02-30"), dict(fecha_vencimiento="20261201"),
                 dict(fecha_vencimiento="2026-12-01T12:00:00"),
                 dict(usuario_asignado_id="999"), dict(usuario_asignado_id="4"),
                 dict(usuario_asignado_id="-1"), dict(usuario_asignado_id="1 OR 1=1"),
                 dict(usuario_asignado_id="9" * 100), dict(materia_id="999"),
                 dict(materia_id="0"), dict(materia_id="abc")]
        original = self.read_task()
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.post("/tasks/new", self.task_data(**changes)).status_code, 400)
                self.assertEqual(self.post(f"/tasks/{self.task_id}/edit", self.task_data(**changes)).status_code, 400)
        self.assertEqual(self.read_task(), original)
        with self.app.app_context():
            self.assertEqual(len(crud.get_all_tasks()), 3)

    def test_inactive_assignment_is_visible_but_requires_reassignment_on_edit(self):
        self.authenticate()
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Usuarios SET activo = 0 WHERE id = ?", (2,))
        page = self.client.get(f"/tasks/{self.task_id}/edit")
        self.assertIn("inactivo; selecciona otro usuario", page.get_data(as_text=True))
        self.assertEqual(self.post(f"/tasks/{self.task_id}/edit", self.task_data()).status_code, 400)
        self.assertEqual(self.post(f"/tasks/{self.task_id}/edit", self.task_data(
            usuario_asignado_id="")).status_code, 302)

    def test_csrf_anonymous_access_and_missing_records(self):
        for path in ("/tasks/", "/tasks/new", f"/tasks/{self.task_id}",
                     f"/tasks/{self.task_id}/edit"):
            self.assertEqual(self.client.get(path).status_code, 302)
        self.authenticate()
        for path in ("/tasks/new", f"/tasks/{self.task_id}/edit", f"/tasks/{self.task_id}/delete"):
            self.assertEqual(self.client.post(path, data=self.task_data()).status_code, 400)
            self.assertEqual(self.post(path, {"csrf_token": "incorrecto"}).status_code, 400)
        for path in ("/tasks/999", "/tasks/999/edit"):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.post("/tasks/999/edit", self.task_data()).status_code, 404)
        self.assertEqual(self.post("/tasks/999/delete").status_code, 404)
        self.assertIsNotNone(self.read_task())

    def test_html_is_escaped_and_sql_is_data(self):
        self.authenticate()
        title = "<script>alert(1)</script>"
        description = "'); DROP TABLE Usuarios; --"
        response = self.post("/tasks/new", self.task_data(titulo=title, descripcion=description))
        page = self.client.get(response.location).get_data(as_text=True)
        self.assertNotIn(title, page)
        self.assertIn("&lt;script&gt;", page)
        task = self.read_task(int(response.location.rsplit("/", 1)[1]))
        self.assertEqual(task["descripcion"], description)
        with self.app.app_context():
            password_hash = crud.get_user_for_auth_by_email("admin@example.test")["contrasena"]
            self.assertEqual(len(crud.get_all_users()), 4)
        for path in ("/tasks/", response.location, "/tasks/new"):
            self.assertNotIn(password_hash, self.client.get(path).get_data(as_text=True))

    def test_task_payment_deletion_guard_without_inventing_legacy_relationships(self):
        self.authenticate()
        with self.app.app_context():
            # Conserva un pago histórico sin tarea o moneda identificadas.
            with get_connection() as connection:
                legacy_payment_id = connection.execute(
                    "INSERT INTO Pagos (usuario_id, monto, monto_original) VALUES (?, ?, ?)",
                    (2, 1250, "12.50"),
                ).lastrowid
            crud.create_payment(2, 2500, self.task_id, "DOP", "efectivo")
        page = self.post(f"/tasks/{self.task_id}/delete", follow_redirects=True)
        self.assertIn("No se puede eliminar", page.get_data(as_text=True))
        self.assertIsNotNone(self.read_task())
        self.assertEqual(self.post(f"/tasks/{self.other_id}/delete").status_code, 302)
        with self.app.app_context():
            self.assertEqual(crud.get_payment_by_id(legacy_payment_id)["monto"], 1250)
            self.assertEqual(len(crud.get_all_payments()), 2)

    def test_foreign_keys_states_priorities_and_creator_user_deletion(self):
        with self.app.app_context():
            for changes in (dict(creador_id=999), dict(prioridad="urgente"), dict(estado="hecha")):
                args = dict(titulo="Inválida", descripcion=None, fecha_vencimiento=None,
                            estado="pendiente", usuario_id=None, materia_id=None, creador_id=1)
                args.update(changes)
                with self.assertRaises(sqlite3.IntegrityError):
                    crud.create_task(**args)
            with self.assertRaises(sqlite3.IntegrityError):
                crud.delete_user(1)
            self.assertIsNotNone(crud.get_user_by_id(1))


class TaskMigrationTests(TaskTestCase):
    def make_legacy(self):
        with self.app.app_context(), get_connection() as connection:
            # La etapa 4 partía de pagos sin referencia a tareas.
            connection.execute("DROP TABLE Pagos")
            connection.execute("""CREATE TABLE Pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL,
                monto REAL NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES Usuarios(id)
            )""")
            connection.execute("DROP TABLE Tareas")
            connection.execute(LEGACY_TASK_SQL)
            connection.execute(
                "INSERT INTO Tareas (id, titulo, descripcion, fecha_creacion, "
                "fecha_vencimiento, estado, usuario_id, materia_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (8, "Histórica", "Conservar", "2025-01-02 03:04:05", "2025-03-04 12:00:00",
                 "en_progreso", 2, self.subject_id),
            )
            connection.execute(
                "INSERT INTO Tareas (id, titulo, estado, usuario_id) VALUES (?, ?, ?, ?)",
                (70, "Borrada", "pendiente", 3),
            )
            connection.execute("DELETE FROM Tareas WHERE id = ?", (70,))
            connection.execute("INSERT INTO Pagos (usuario_id, monto) VALUES (?, ?)", (2, "12.50"))
            connection.execute("INSERT INTO Asistencias (usuario_id) VALUES (?)", (2,))

    def test_migration_backup_preservation_unknown_history_sequence_and_idempotence(self):
        self.make_legacy()
        with closing(sqlite3.connect(self.path)) as connection:
            original_dump = list(connection.iterdump())
            original_task = connection.execute("SELECT * FROM Tareas").fetchone()
        result = self.app.test_cli_runner().invoke(args=["migrate-tasks"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("información pendiente (ID): 8", result.output)
        backups = list(self.path.parent.glob("*.backup-tasks-*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(list(connection.iterdump()), original_dump)
        with closing(sqlite3.connect(self.path)) as connection:
            updated_task = connection.execute("SELECT * FROM Tareas").fetchone()
            self.assertEqual(updated_task[:8], original_task)
            self.assertEqual(updated_task[8:], (None, None, None))
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table in ("Usuarios", "Materias", "Pagos", "Asistencias"):
                with closing(sqlite3.connect(backups[0])) as original:
                    # table viene de esta lista fija, no de entrada del navegador.
                    self.assertEqual(connection.execute(f"SELECT * FROM {table}").fetchall(),
                                     original.execute(f"SELECT * FROM {table}").fetchall())
        self.assertIsNone(migrate(self.path))
        self.assertEqual(len(list(self.path.parent.glob("*.backup-tasks-*.db"))), 1)
        self.authenticate()
        detail = self.client.get("/tasks/8").get_data(as_text=True)
        self.assertIn("No consta (tarea histórica)", detail)
        self.assertIn("Sin especificar", detail)
        response = self.post("/tasks/8/edit", self.task_data())
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.read_task(8)["creador_id"])
        response = self.post("/tasks/new", self.task_data(usuario_asignado_id=""))
        self.assertGreater(int(response.location.rsplit("/", 1)[1]), 70)

    def test_migration_rejects_invalid_states_and_relations_without_changing_data(self):
        for invalid in ("state", "relation"):
            with self.subTest(invalid=invalid):
                self.make_legacy()
                with closing(sqlite3.connect(self.path)) as connection:
                    if invalid == "state":
                        connection.execute("UPDATE Tareas SET estado = ?", ("histórico-inválido",))
                    else:
                        connection.execute("UPDATE Tareas SET usuario_id = ?", (999,))
                    connection.commit()
                    original = list(connection.iterdump())
                with self.assertRaises(ValueError):
                    migrate(self.path)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(list(connection.iterdump()), original)

    def test_migration_rejects_unknown_schema_indexes_and_inbound_relations(self):
        for sql in ("ALTER TABLE Tareas ADD COLUMN otro TEXT",
                    "CREATE INDEX custom_task_index ON Tareas(titulo)",
                    "CREATE TABLE Referencias (tarea_id INTEGER REFERENCES Tareas(id))"):
            self.make_legacy()
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute(sql)
                connection.commit()
                original = list(connection.iterdump())
            with self.assertRaises(ValueError):
                migrate(self.path)
            with closing(sqlite3.connect(self.path)) as connection:
                self.assertEqual(list(connection.iterdump()), original)

    def test_migration_missing_database_not_created_and_new_schema_is_noop(self):
        missing = self.path.with_name("missing.db")
        with self.assertRaises(sqlite3.OperationalError):
            migrate(missing)
        self.assertFalse(missing.exists())
        self.assertIsNone(migrate(self.path))

    def test_failure_after_table_replacement_rolls_back_and_preserves_backup(self):
        self.make_legacy()
        with closing(sqlite3.connect(self.path)) as connection:
            original = list(connection.iterdump())
        calls = 0

        def fail_final_check(connection):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise ValueError("Fallo simulado después del reemplazo.")
            check_integrity(connection)

        with patch("migrations.add_task_fields.check_integrity", side_effect=fail_final_check):
            with self.assertRaisesRegex(ValueError, "Fallo simulado"):
                migrate(self.path)
        self.assertEqual(calls, 3)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(list(connection.iterdump()), original)
        backups = list(self.path.parent.glob("*.backup-tasks-*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(list(connection.iterdump()), original)


if __name__ == "__main__":
    unittest.main()
