from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import unittest
from unittest.mock import patch

from app.models import amount_to_cents, format_amount, MAX_PAYMENT_CENTS
from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection
from migrations.add_payment_fields import migrate, check_integrity
from test_tasks import TaskTestCase


LEGACY_PAYMENT_SQL = """CREATE TABLE Pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    monto REAL NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES Usuarios(id)
)"""


class MoneyTests(unittest.TestCase):
    def test_exact_conversion_and_formatting_for_both_currencies(self):
        for value, expected in (("0.01", 1), ("0.10", 10), ("12.50", 1250),
                                ("12", 1200), ("12.5", 1250), (" 2.67 ", 267),
                                ("92233720368547758.07", MAX_PAYMENT_CENTS)):
            with self.subTest(value=value):
                self.assertEqual(amount_to_cents(value), expected)
                self.assertEqual(amount_to_cents(format_amount(expected)), expected)
        self.assertEqual(format_amount(1), "0.01")
        self.assertEqual(format_amount(-1250), "-12.50")

    def test_invalid_excess_decimals_and_overflow_are_rejected(self):
        for value in ("0", "0.00", "-1", "1.001", "12.500", "1,50", "NaN",
                      "Infinity", "1e2", "+1", "", "abc", "1 000", ".5",
                      "92233720368547758.08", "9" * 5000):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    amount_to_cents(value)


class PaymentsTests(TaskTestCase):
    def payment_data(self, **changes):
        values = dict(tarea_id=str(self.task_id), usuario_id="2", monto="12.50",
                      moneda="USD", estado="pendiente", metodo="transferencia", notas="Prueba")
        values.update(changes)
        return values

    def create_payment(self, **changes):
        response = self.post("/payments/new", self.payment_data(**changes))
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return int(response.location.rsplit("/", 1)[1])

    def read_payment(self, payment_id):
        with self.app.app_context():
            return crud.get_payment_by_id(payment_id)

    def test_admin_create_list_detail_edit_and_annul_in_both_currencies(self):
        self.authenticate()
        self.assertEqual(self.client.get("/payments/new").status_code, 200)
        usd_id = self.create_payment(fecha_pago="1999-01-01", monto_centavos="1")
        dop_id = self.create_payment(moneda="DOP", monto="125.01")
        payment = self.read_payment(usd_id)
        self.assertEqual((payment["monto"], payment["moneda"], payment["estado"]),
                         (1250, "USD", "pendiente"))
        self.assertIsNone(payment["fecha_pago"])
        self.assertIsNone(payment["monto_original"])
        self.assertEqual(datetime.fromisoformat(payment["fecha_creacion"]).tzinfo, timezone.utc)
        listed = self.client.get("/payments/").get_data(as_text=True)
        self.assertIn("USD 12.50", listed)
        self.assertIn("DOP 125.01", listed)
        for path in (f"/payments/{usd_id}", f"/payments/{usd_id}/edit"):
            self.assertEqual(self.client.get(path).status_code, 200)
        response = self.post(f"/payments/{usd_id}/edit", self.payment_data(
            monto="20.10", moneda="DOP", tarea_id=str(self.other_id), usuario_id="3", metodo="efectivo"))
        self.assertEqual(response.status_code, 302)
        updated = self.read_payment(usd_id)
        self.assertEqual((updated["monto"], updated["usuario_id"], updated["tarea_id"]),
                         (2010, 3, self.other_id))
        self.assertEqual(updated["fecha_creacion"], payment["fecha_creacion"])
        self.assertEqual(self.client.get(f"/payments/{usd_id}/delete").status_code, 405)
        self.assertEqual(self.post(f"/payments/{usd_id}/delete").status_code, 302)
        annulled = self.read_payment(usd_id)
        self.assertEqual(annulled["estado"], "anulado")
        self.assertEqual(annulled["monto"], 2010)
        self.assertEqual(self.client.get(f"/payments/{usd_id}").status_code, 200)
        self.assertIsNotNone(self.read_payment(dop_id))

    def test_paid_date_is_automatic_and_paid_amount_is_immutable(self):
        self.authenticate()
        payment_id = self.create_payment()
        response = self.post(f"/payments/{payment_id}/edit", self.payment_data(
            estado="pagado", fecha_pago="1999-01-01", fecha_creacion="1999-01-01"))
        self.assertEqual(response.status_code, 302)
        paid = self.read_payment(payment_id)
        self.assertEqual(datetime.fromisoformat(paid["fecha_pago"]).tzinfo, timezone.utc)
        self.assertNotIn("1999", paid["fecha_pago"])
        response = self.post(f"/payments/{payment_id}/edit", self.payment_data(
            monto="0.01", moneda="DOP", estado="pendiente", usuario_id="3", notas="Notas corregidas"))
        self.assertEqual(response.status_code, 302)
        updated = self.read_payment(payment_id)
        for field in ("monto", "moneda", "estado", "usuario_id", "tarea_id", "metodo",
                      "fecha_pago", "fecha_creacion", "fecha"):
            self.assertEqual(updated[field], paid[field])
        self.assertEqual(updated["notas"], "Notas corregidas")
        self.assertEqual(self.post(f"/payments/{payment_id}/edit", {"notas": "x" * 2001}).status_code, 400)
        self.post(f"/payments/{payment_id}/delete")
        annulled = self.read_payment(payment_id)
        self.assertEqual(annulled["fecha_pago"], paid["fecha_pago"])
        self.assertEqual(self.client.get(f"/payments/{payment_id}/edit").status_code, 403)
        self.assertEqual(self.post(f"/payments/{payment_id}/edit", self.payment_data()).status_code, 403)
        self.assertEqual(self.post(f"/payments/{payment_id}/delete").status_code, 302)
        self.assertEqual(self.read_payment(payment_id), annulled)

    def test_initial_paid_payment_has_date_and_no_user_credentials_are_exposed(self):
        self.authenticate()
        payment_id = self.create_payment(estado="pagado", notas="<script>alert(1)</script>")
        payment = self.read_payment(payment_id)
        self.assertEqual(payment["fecha_pago"], payment["fecha_creacion"])
        with self.app.app_context():
            password_hash = crud.get_user_for_auth_by_email("ana@example.test")["contrasena"]
        for path in ("/payments/", f"/payments/{payment_id}", f"/payments/{payment_id}/edit"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotIn(password_hash, html)
            self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", self.client.get(f"/payments/{payment_id}").get_data(as_text=True))

    def test_members_and_anonymous_users_cannot_access_any_payment_operation(self):
        self.authenticate()
        payment_id = self.create_payment()
        paths = ("/payments/", "/payments/new", f"/payments/{payment_id}", f"/payments/{payment_id}/edit")
        self.authenticate(2)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 403)
        for path in ("/payments/new", f"/payments/{payment_id}/edit", f"/payments/{payment_id}/delete"):
            self.assertEqual(self.post(path, self.payment_data(rol="admin")).status_code, 403)
        self.assertNotIn('href="/payments/"', self.client.get("/").get_data(as_text=True))
        with self.client.session_transaction() as session:
            session.clear()
            session["csrf_token"] = "token-de-pruebas"
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 302)
        self.assertEqual(self.post("/payments/new", self.payment_data()).status_code, 302)
        self.assertEqual(self.read_payment(payment_id)["estado"], "pendiente")

    def test_csrf_missing_records_and_server_validations(self):
        self.authenticate()
        payment_id = self.create_payment()
        for path in ("/payments/new", f"/payments/{payment_id}/edit", f"/payments/{payment_id}/delete"):
            self.assertEqual(self.client.post(path, data=self.payment_data()).status_code, 400)
            self.assertEqual(self.post(path, {"csrf_token": "incorrecto"}).status_code, 400)
        for path in ("/payments/999", "/payments/999/edit"):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.post("/payments/999/edit", self.payment_data()).status_code, 404)
        self.assertEqual(self.post("/payments/999/delete").status_code, 404)
        original = self.read_payment(payment_id)
        for changes in (dict(monto="0"), dict(monto="12.345"), dict(monto="1,50"),
                        dict(monto="NaN"), dict(moneda="EUR"), dict(moneda=""),
                        dict(estado="anulado"), dict(metodo="paypal-inventado"),
                        dict(notas="x" * 2001), dict(tarea_id="999"), dict(tarea_id=""),
                        dict(tarea_id="1 OR 1=1"), dict(usuario_id="4"), dict(usuario_id="999"),
                        dict(usuario_id="9" * 100)):
            with self.subTest(changes=changes):
                self.assertEqual(self.post("/payments/new", self.payment_data(**changes)).status_code, 400)
                self.assertEqual(self.post(f"/payments/{payment_id}/edit", self.payment_data(**changes)).status_code, 400)
        self.assertEqual(self.read_payment(payment_id), original)
        with self.app.app_context():
            self.assertEqual(len(crud.get_all_payments()), 1)

    def test_cancelled_tasks_and_inactive_recipients_rejected_but_annul_allowed(self):
        self.authenticate()
        payment_id = self.create_payment()
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Tareas SET estado = 'cancelada' WHERE id = ?", (self.task_id,))
            connection.execute("UPDATE Usuarios SET activo = 0 WHERE id = ?", (2,))
        self.assertEqual(self.post("/payments/new", self.payment_data()).status_code, 400)
        self.assertEqual(self.post(f"/payments/{payment_id}/edit", self.payment_data(estado="pagado")).status_code, 400)
        self.assertEqual(self.post(f"/payments/{payment_id}/delete").status_code, 302)
        self.assertEqual(self.read_payment(payment_id)["estado"], "anulado")

    def test_payments_block_task_and_user_deletion_even_after_annulment(self):
        self.authenticate()
        payment_id = self.create_payment()
        self.post(f"/payments/{payment_id}/delete")
        response = self.post(f"/tasks/{self.task_id}/delete", follow_redirects=True)
        self.assertIn("No se puede eliminar", response.get_data(as_text=True))
        self.assertIsNotNone(self.read_task())
        with self.app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                crud.delete_user(2)
            with get_connection() as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM Tareas WHERE id = ?", (self.task_id,))
        self.assertIsNotNone(self.read_payment(payment_id))

    def test_crud_guards_missing_rows_bad_amounts_and_terminal_states(self):
        with self.app.app_context():
            args = dict(usuario_id=2, monto_centavos=1250, tarea_id=self.task_id,
                        moneda="USD", metodo="efectivo", estado="pendiente")
            for changes in (dict(monto_centavos=12.5), dict(monto_centavos=True), dict(monto_centavos=0),
                            dict(moneda="EUR"), dict(metodo="no"), dict(estado="anulado"),
                            dict(usuario_id=4), dict(tarea_id=999)):
                with self.subTest(changes=changes):
                    with self.assertRaises(ValueError):
                        crud.create_payment(**{**args, **changes})
            self.assertEqual(crud.update_payment(999, **args), 0)
            self.assertEqual(crud.annul_payment(999), 0)
            paid_id = crud.create_payment(**{**args, "estado": "pagado"})
            with self.assertRaises(ValueError):
                crud.update_payment(paid_id, **args)
            crud.annul_payment(paid_id)
            self.assertEqual(crud.update_payment_notes(paid_id, "No cambiar"), 0)
            with self.assertRaises(ValueError):
                crud.update_payment(paid_id, **args)

    def test_schema_rejects_fractional_cents_incomplete_new_payments_and_missing_paid_date(self):
        sql = (
            "INSERT INTO Pagos (usuario_id, monto, tarea_id, moneda, metodo, estado, "
            "fecha_creacion, fecha_pago) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        created_at = "2026-10-06T12:00:00+00:00"
        with self.app.app_context(), get_connection() as connection:
            for row in ((2, 12.5, self.task_id, "USD", "efectivo", "pendiente", created_at, None),
                        (2, 1250, self.task_id, None, "efectivo", "pendiente", created_at, None),
                        (2, 1250, self.task_id, "USD", "efectivo", "pagado", created_at, None),
                        (2, 1250, 999, "USD", "efectivo", "pendiente", created_at, None)):
                with self.subTest(row=row):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(sql, row)
class PaymentMigrationTests(TaskTestCase):
    def make_legacy(self):
        with self.app.app_context(), get_connection() as connection:
            connection.execute("DROP TABLE Pagos")
            connection.execute(LEGACY_PAYMENT_SQL)
            connection.executemany(
                "INSERT INTO Pagos (id, usuario_id, monto, fecha) VALUES (?, ?, ?, ?)",
                [(8, 2, "12.345", "2025-01-02 03:04:05"),
                 (9, 3, "2.675", "2025-01-03 03:04:05"),
                 (10, 2, "0.001", "2025-01-04 03:04:05"),
                 (11, 3, "-1.235", "2025-01-05 03:04:05"),
                 (70, 2, "1.00", "2025-01-06 03:04:05")],
            )
            connection.execute("DELETE FROM Pagos WHERE id = ?", (70,))

    def test_backup_amount_rounding_preservation_unknown_currency_and_idempotence(self):
        self.make_legacy()
        with closing(sqlite3.connect(self.path)) as connection:
            original = list(connection.iterdump())
        result = self.app.test_cli_runner().invoke(args=["migrate-payments"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("información pendiente (ID): 8, 9, 10, 11", result.output)
        backups = list(self.path.parent.glob("*.backup-payments-*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as backup:
            self.assertEqual(list(backup.iterdump()), original)
            with closing(sqlite3.connect(self.path)) as current:
                for table in ("Usuarios", "Tareas", "Materias", "Asistencias"):
                    self.assertEqual(current.execute(f"SELECT * FROM {table}").fetchall(),
                                     backup.execute(f"SELECT * FROM {table}").fetchall())
                self.assertEqual(current.execute("SELECT id, monto FROM Pagos ORDER BY id").fetchall(),
                                 [(8, 1235), (9, 268), (10, 0), (11, -124)])
                self.assertEqual(current.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(current.execute("PRAGMA quick_check").fetchone()[0], "ok")
        with self.app.app_context():
            payment = crud.get_payment_by_id(8)
            self.assertEqual(payment["monto_original"], "12.345")
            self.assertEqual(payment["fecha"], "2025-01-02 03:04:05")
            self.assertEqual(payment["fecha_creacion"], payment["fecha"])
            for field in ("moneda", "estado", "tarea_id", "metodo", "fecha_pago"):
                self.assertIsNone(payment[field])
            self.assertEqual(payment["pendiente_completar"], 1)
            new_id = crud.create_payment(2, 1250, self.task_id, "DOP", "efectivo")
            self.assertGreater(new_id, 70)
        self.assertIsNone(migrate(self.path))
        self.assertEqual(len(list(self.path.parent.glob("*.backup-payments-*.db"))), 1)

    def test_historical_payment_can_be_completed_without_inventing_paid_date(self):
        self.make_legacy()
        migrate(self.path)
        self.authenticate()
        html = self.client.get("/payments/8").get_data(as_text=True)
        self.assertIn("Información histórica pendiente", html)
        self.assertIn("Moneda por identificar", html)
        with self.app.app_context():
            affected = crud.update_payment(8, 2, 1235, self.task_id, "DOP", "efectivo", "pendiente")
            self.assertEqual(affected, 1)
            payment = crud.get_payment_by_id(8)
            self.assertEqual(payment["pendiente_completar"], 0)
            self.assertIsNone(payment["fecha_pago"])
            self.assertEqual(payment["monto_original"], "12.345")
            crud.update_payment(8, 2, 1235, self.task_id, "DOP", "efectivo", "pagado")
            self.assertIsNotNone(crud.get_payment_by_id(8)["fecha_pago"])
            self.assertEqual(crud.annul_payment(9), 1)  # Permite anular un histórico incompleto.

    def test_rollback_after_replacement_keeps_original_and_backup(self):
        self.make_legacy()
        with closing(sqlite3.connect(self.path)) as connection:
            original = list(connection.iterdump())
        calls = 0

        def fail_final_check(connection):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise ValueError("Fallo simulado")
            check_integrity(connection)

        with patch("migrations.add_payment_fields.check_integrity", side_effect=fail_final_check):
            with self.assertRaisesRegex(ValueError, "Fallo simulado"):
                migrate(self.path)
        for path in (self.path, *self.path.parent.glob("*.backup-payments-*.db")):
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(list(connection.iterdump()), original)

    def test_invalid_amounts_relations_and_unknown_schema_do_not_modify_database(self):
        for sql, args in (("UPDATE Pagos SET monto = ?", ("invalido",)),
                          ("UPDATE Pagos SET monto = ?", ("1e300",)),
                          ("UPDATE Pagos SET usuario_id = ?", (999,)),
                          ("ALTER TABLE Pagos ADD COLUMN otro TEXT", ()),
                          ("CREATE INDEX extra ON Pagos(usuario_id)", ())):
            self.make_legacy()
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute(sql, args)
                connection.commit()
                original = list(connection.iterdump())
            with self.assertRaises(ValueError):
                migrate(self.path)
            with closing(sqlite3.connect(self.path)) as connection:
                self.assertEqual(list(connection.iterdump()), original)

    def test_missing_database_and_new_database_noop(self):
        missing = self.path.with_name("missing.db")
        with self.assertRaises(sqlite3.OperationalError):
            migrate(missing)
        self.assertFalse(missing.exists())
        self.assertIsNone(migrate(self.path))


if __name__ == "__main__":
    unittest.main()
