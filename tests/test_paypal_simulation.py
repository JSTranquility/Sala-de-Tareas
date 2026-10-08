from datetime import datetime, timezone
import unittest

from app.utils.paypal_simulator import simulate_payment
from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection
from test_tasks import TaskTestCase


class SimulatorTests(unittest.TestCase):
    def test_invalid_inputs(self):
        for args in ((0, 100, "USD", "aprobado"), (1, 0, "USD", "aprobado"),
                     (1, True, "USD", "aprobado"), (1, 1.5, "USD", "aprobado"),
                     (1, 100, "EUR", "aprobado"), (1, 100, "USD", "inventado")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                simulate_payment(*args)


class PaymentSimulationTests(TaskTestCase):
    def setUp(self):
        super().setUp()
        with self.app.app_context():
            self.payment_id = crud.create_payment(
                2, 1250, self.task_id, "DOP", "otro", notas="Ejercicio"
            )
        self.url = f"/payments/{self.payment_id}/simulate"
        self.authenticate()

    def read_payment(self):
        with self.app.app_context():
            return crud.get_payment_by_id(self.payment_id)

    def test_approve_preserves_amount_relations_task_and_repeated_date(self):
        before = self.read_payment()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.read_payment(), before)
        response = self.post(self.url, {"resultado": "aprobado", "monto": "0.01",
                                        "moneda": "USD", "usuario_id": "3"},
                             follow_redirects=True)
        self.assertIn("No se realizó ningún cobro", response.get_data(as_text=True))
        after = self.read_payment()
        self.assertEqual(after["estado"], "pagado")
        self.assertEqual(datetime.fromisoformat(after["fecha_pago"]).tzinfo, timezone.utc)
        self.assertIn("SIM-PAGO-", after["notas"])
        self.assertIn("Ejercicio", after["notas"])
        for field in ("monto", "moneda", "metodo", "usuario_id", "tarea_id", "fecha_creacion"):
            self.assertEqual(after[field], before[field])
        with self.app.app_context():
            self.assertEqual(crud.get_task_by_id(self.task_id)["estado"], "pendiente")
            self.assertEqual(crud.mark_payment_paid(self.payment_id), 0)
        self.assertEqual(self.post(self.url, {"resultado": "aprobado"}).status_code, 400)
        self.assertEqual(self.read_payment(), after)

    def test_reject_cancel_and_invalid_result_do_not_write(self):
        before = self.read_payment()
        for result in ("rechazado", "cancelado"):
            self.assertEqual(self.post(self.url, {"resultado": result}).status_code, 302)
            self.assertEqual(self.read_payment(), before)
        self.assertEqual(self.post(self.url, {"resultado": "inventado"}).status_code, 400)
        self.assertEqual(self.read_payment(), before)

    def test_permissions_csrf_and_missing_payment(self):
        self.assertEqual(self.client.post(self.url, data={"resultado": "aprobado"}).status_code, 400)
        self.assertEqual(self.post(self.url, {"csrf_token": "incorrecto"}).status_code, 400)
        self.assertEqual(self.client.get("/payments/999/simulate").status_code, 404)
        self.assertEqual(self.post("/payments/999/simulate").status_code, 404)
        self.authenticate(2)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.post(self.url, {"resultado": "aprobado"}).status_code, 403)
        self.authenticate(4)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.read_payment()["estado"], "pendiente")

    def test_cancelled_task_or_inactive_recipient_blocks_simulation(self):
        for sql, args in (("UPDATE Tareas SET estado = 'cancelada' WHERE id = ?", (self.task_id,)),
                          ("UPDATE Usuarios SET activo = 0 WHERE id = ?", (2,))):
            with self.app.app_context(), get_connection() as connection:
                connection.execute(sql, args)
            self.assertEqual(self.client.get(self.url).status_code, 400)
            self.assertEqual(self.post(self.url, {"resultado": "aprobado"}).status_code, 400)
            with self.app.app_context():
                with self.assertRaises(ValueError):
                    crud.mark_payment_paid(self.payment_id)
            self.assertEqual(self.read_payment()["estado"], "pendiente")
            with self.app.app_context(), get_connection() as connection:
                connection.execute("UPDATE Tareas SET estado = 'pendiente' WHERE id = ?", (self.task_id,))

    def test_incomplete_or_annulled_payment_is_rejected(self):
        with self.app.app_context(), get_connection() as connection:
            connection.execute(
                "UPDATE Pagos SET monto_original = '12.50', moneda = NULL WHERE id = ?",
                (self.payment_id,),
            )
        self.assertEqual(self.post(self.url, {"resultado": "aprobado"}).status_code, 400)
        with self.app.app_context():
            crud.annul_payment(self.payment_id)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_usd_and_long_notes(self):
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Pagos SET moneda = 'USD', notas = ? WHERE id = ?",
                               ("x" * 2000, self.payment_id))
        before = self.read_payment()
        self.assertEqual(self.post(self.url, {"resultado": "aprobado"}).status_code, 400)
        self.assertEqual(self.read_payment(), before)
        with self.app.app_context(), get_connection() as connection:
            connection.execute("UPDATE Pagos SET notas = NULL WHERE id = ?", (self.payment_id,))
        self.assertEqual(self.post(self.url, {"resultado": "aprobado"}).status_code, 302)
        self.assertEqual(self.read_payment()["moneda"], "USD")
