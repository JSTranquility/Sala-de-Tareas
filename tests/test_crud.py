from pathlib import Path
import sqlite3
import tempfile
import unittest

from flask import Flask
from werkzeug.security import check_password_hash

from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection, initialize_database


class CrudTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config["DATABASE_PATH"] = str(
            Path(self.directory.name) / "crud.db"
        )
        self.context = self.app.app_context()
        self.context.push()
        initialize_database()

    def tearDown(self):
        self.context.pop()
        self.directory.cleanup()

    def create_user(self, email="ana@example.test"):
        return crud.create_user("Ana", email, "clave-de-prueba", None, "member")

    def test_user_crud_returns_data_without_credentials(self):
        self.assertEqual(crud.get_all_users(), [])
        user_id = self.create_user()
        self.assertIsInstance(user_id, int)
        user = crud.get_user_by_id(user_id)
        self.assertEqual(user["nombre"], "Ana")
        self.assertEqual(crud.get_all_users(), [user])
        self.assertEqual(crud.get_user_by_email("ana@example.test"), user)
        self.assertNotIn("contrasena", user)
        self.assertEqual(
            crud.update_user(user_id, "Ana María", "ana@example.test",
                             None, "123", "admin"), 1
        )
        self.assertEqual(crud.get_user_by_id(user_id)["nombre"], "Ana María")
        self.assertEqual(crud.delete_user(user_id), 1)
        self.assertIsNone(crud.get_user_by_id(user_id))

    def test_password_hash_is_preserved_or_replaced_explicitly(self):
        user_id = self.create_user()
        original = crud.get_user_for_auth_by_email("ana@example.test")["contrasena"]
        self.assertNotEqual(original, "clave-de-prueba")
        self.assertTrue(check_password_hash(original, "clave-de-prueba"))
        crud.update_user(user_id, "Ana", "ana@example.test", None, None, "member")
        self.assertEqual(
            crud.get_user_for_auth_by_email("ana@example.test")["contrasena"],
            original,
        )
        crud.update_user(user_id, "Ana", "ana@example.test", "otra-clave",
                         None, "member")
        updated = crud.get_user_for_auth_by_email("ana@example.test")["contrasena"]
        self.assertTrue(check_password_hash(updated, "otra-clave"))
        self.assertFalse(check_password_hash(updated, "clave-de-prueba"))

    def test_missing_records_have_clear_results(self):
        for read in (crud.get_user_by_id, crud.get_task_by_id,
                     crud.get_payment_by_id):
            self.assertIsNone(read(999))
        self.assertIsNone(crud.get_user_by_email("missing@example.test"))
        self.assertIsNone(crud.get_user_for_auth_by_email("missing@example.test"))
        self.assertEqual(crud.update_user(999, "Ana", "x@example.test",
                                         None, None, "member"), 0)
        self.assertEqual(crud.update_task(999, "Tarea", None, None,
                                         "pendiente", 999, None), 0)
        self.assertEqual(crud.update_attendance(999, 999), 0)
        for delete in (crud.delete_user, crud.delete_task, crud.delete_attendance):
            self.assertEqual(delete(999), 0)

    def test_duplicate_email_rolls_back_create_and_update(self):
        user_id = self.create_user()
        other_id = self.create_user("other@example.test")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create_user()
        with self.assertRaises(sqlite3.IntegrityError):
            crud.update_user(other_id, "Cambio", "ana@example.test",
                             None, None, "member")
        self.assertEqual(len(crud.get_all_users()), 2)
        self.assertEqual(crud.get_user_by_id(other_id)["correo"], "other@example.test")
        self.assertEqual(crud.get_user_by_id(user_id)["nombre"], "Ana")

    def test_task_crud_and_user_filter(self):
        user_id = self.create_user()
        other_id = self.create_user("other@example.test")
        subject_id = crud.create_subject("Matemáticas", None)
        self.assertEqual(crud.get_all_tasks(), [])
        task_id = crud.create_task("Ejercicio", None, "2026-11-01",
                                   "pendiente", user_id, subject_id)
        other_task_id = crud.create_task("Otra", None, None,
                                         "pendiente", other_id, None)
        self.assertEqual(len(crud.get_all_tasks()), 2)
        self.assertEqual([task["id"] for task in crud.get_tasks_by_user(user_id)],
                         [task_id])
        self.assertEqual(crud.update_task(task_id, "Resuelto", "Descripción",
                                         None, "completada", user_id, subject_id), 1)
        self.assertEqual(crud.get_task_by_id(task_id)["estado"], "completada")
        self.assertEqual(crud.delete_task(task_id), 1)
        self.assertIsNone(crud.get_task_by_id(task_id))
        self.assertIsNotNone(crud.get_task_by_id(other_task_id))

    def test_foreign_key_errors_do_not_appear_as_success(self):
        with self.assertRaises(sqlite3.IntegrityError):
            crud.create_task("Tarea", None, None, "pendiente", 999, None)
        with self.assertRaises(sqlite3.IntegrityError):
            crud.create_attendance(999)
        user_id = self.create_user()
        task_id = crud.create_task("Tarea", None, None, "pendiente", user_id, None)
        with self.assertRaises(sqlite3.IntegrityError):
            crud.update_task(task_id, "Cambio", None, None, "pendiente", 999, None)
        self.assertEqual(crud.get_task_by_id(task_id)["titulo"], "Tarea")
        with self.assertRaises(sqlite3.IntegrityError):
            crud.delete_user(user_id)
        self.assertIsNotNone(crud.get_user_by_id(user_id))

    def test_payment_reads_use_cents_and_block_user_deletion(self):
        user_id = self.create_user()
        other_id = self.create_user("other@example.test")
        # Los pagos nuevos usan centavos y una moneda explícita.
        task_id = crud.create_task("Tarea pagada", None, None, "pendiente", user_id, None)
        payment_id = crud.create_payment(user_id, 1250, task_id, "USD", "efectivo")
        self.assertIsInstance(payment_id, int)
        payment = crud.get_payment_by_id(payment_id)
        self.assertEqual(payment["monto"], 1250)
        self.assertEqual(crud.get_all_payments(), [payment])
        self.assertEqual(crud.get_payments_by_user(user_id), [payment])
        self.assertEqual(crud.get_payments_by_user(other_id), [])
        with self.assertRaises(sqlite3.IntegrityError):
            crud.delete_user(user_id)
        self.assertEqual(crud.get_payment_by_id(payment_id), payment)

    def test_attendance_operations_return_ids_and_row_counts(self):
        user_id = self.create_user()
        other_id = self.create_user("other@example.test")
        attendance_id = crud.create_attendance(user_id)
        self.assertIsInstance(attendance_id, int)
        self.assertEqual(crud.update_attendance(attendance_id, other_id), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            crud.update_attendance(attendance_id, 999)
        with get_connection() as connection:
            row = connection.execute(
                "SELECT usuario_id FROM Asistencias WHERE id = ?", (attendance_id,)
            ).fetchone()
            self.assertEqual(row[0], other_id)
        self.assertEqual(crud.delete_attendance(attendance_id), 1)

    def test_sql_input_is_treated_as_data(self):
        name = "Ana'); DROP TABLE Usuarios; --"
        user_id = crud.create_user(name, "sql@example.test", "clave", None, "member")
        self.assertEqual(crud.get_user_by_id(user_id)["nombre"], name)
        self.assertIsNone(crud.get_user_by_email("' OR 1=1 --"))
        self.assertEqual(len(crud.get_all_users()), 1)

    def test_database_failure_is_logged_without_sensitive_details(self):
        self.app.config["DATABASE_PATH"] = str(Path(self.directory.name) / "missing.db")
        with self.assertLogs("app.utils.data.database", level="ERROR") as logs:
            with self.assertRaises(sqlite3.OperationalError):
                crud.get_all_users()
        self.assertNotIn(self.directory.name, " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
