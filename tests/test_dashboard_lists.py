from datetime import datetime, timedelta, timezone
from html import unescape
import re

from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection
from test_tasks import TaskTestCase


class DashboardAndListsTests(TaskTestCase):
    def test_dashboard_dates_states_and_member_scope(self):
        today = datetime.now(timezone.utc).date()
        with self.app.app_context():
            with get_connection() as connection:
                connection.execute("UPDATE Tareas SET fecha_vencimiento = ? WHERE id = ?",
                                   ((today - timedelta(days=1)).isoformat(), self.task_id))
                connection.execute("UPDATE Tareas SET fecha_vencimiento = ? WHERE id = ?",
                                   ((today + timedelta(days=3)).isoformat(), self.other_id))
                connection.execute("UPDATE Tareas SET fecha_vencimiento = ?, estado = 'completada' WHERE id = ?",
                                   ((today - timedelta(days=5)).isoformat(), self.unassigned_id))
            summary = crud.get_dashboard()
            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["states"], {"pendiente": 2, "completada": 1})
            self.assertEqual((summary["overdue"], summary["upcoming"]), (1, 1))
            member = crud.get_dashboard(2)
            self.assertEqual(member["total"], 1)
            self.assertEqual((member["overdue"], member["upcoming"]), (1, 0))
            self.assertIsNone(member["payments"])
        self.authenticate()
        self.assertIn("Resumen de pagos", self.client.get("/").get_data(as_text=True))
        self.authenticate(2)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Resumen de mis tareas", html)
        self.assertNotIn("Resumen de pagos", html)
        self.assertNotIn("Luis", html)

    def test_dashboard_money_currencies_and_unknown_history(self):
        with self.app.app_context():
            crud.create_payment(2, 10, self.task_id, "USD", "otro")
            paid_id = crud.create_payment(2, 20, self.task_id, "USD", "otro")
            crud.mark_payment_paid(paid_id)
            crud.create_payment(3, 300, self.other_id, "DOP", "efectivo", "pagado")
            annulled = crud.create_payment(3, 999, self.other_id, "USD", "otro")
            crud.annul_payment(annulled)
            with get_connection() as connection:
                connection.execute(
                    "INSERT INTO Pagos (usuario_id, monto, monto_original, estado) "
                    "VALUES (?, ?, ?, ?)", (2, 888, "8.88", "pendiente")
                )
            summary = crud.get_dashboard()
            self.assertEqual(summary["payments"]["USD"]["pendiente"], {"count": 1, "amount": 10})
            self.assertEqual(summary["payments"]["USD"]["pagado"]["amount"], 20)
            self.assertEqual(summary["payments"]["DOP"]["pagado"]["amount"], 300)
            self.assertEqual(summary["incomplete_payments"], 1)
        self.authenticate()
        html = self.client.get("/").get_data(as_text=True)
        for text in ("USD 0.10", "USD 0.20", "DOP 3.00", "1 pagos con información pendiente"):
            self.assertIn(text, html)

    def test_due_today_last_day_and_cancelled_are_counted_correctly(self):
        today = datetime.now(timezone.utc).date()
        with self.app.app_context():
            with get_connection() as connection:
                connection.execute("UPDATE Tareas SET fecha_vencimiento = ? WHERE id = ?",
                                   (today.isoformat(), self.task_id))
                connection.execute("UPDATE Tareas SET fecha_vencimiento = ? WHERE id = ?",
                                   ((today + timedelta(days=4)).isoformat(), self.other_id))
                connection.execute("UPDATE Tareas SET fecha_vencimiento = ?, estado = 'cancelada' WHERE id = ?",
                                   ((today - timedelta(days=1)).isoformat(), self.unassigned_id))
            summary = crud.get_dashboard()
            self.assertEqual((summary["overdue"], summary["upcoming"]), (0, 1))

    def test_task_search_combined_filters_pagination_and_links(self):
        with self.app.app_context():
            for number in range(12):
                crud.create_task(f"Ejercicio {number:02}", "Buscar contenido", None,
                                 "pendiente", 2, None, prioridad="alta", creador_id=1)
        self.authenticate()
        response = self.client.get("/tasks/?q=Ejercicio&estado=pendiente&prioridad=alta")
        html = response.get_data(as_text=True)
        self.assertIn("12 resultados", html)
        self.assertEqual(html.count("Ejercicio "), 10)
        next_url = unescape(re.search(r'href="([^"]+)">Siguiente', html).group(1))
        for query in ("q=Ejercicio", "estado=pendiente", "prioridad=alta", "page=2"):
            self.assertIn(query, next_url)
        page_two = self.client.get(next_url).get_data(as_text=True)
        self.assertEqual(page_two.count("Ejercicio "), 2)
        self.assertIn("Página 2 de 2", page_two)
        last = self.client.get("/tasks/?q=Ejercicio&page=999").get_data(as_text=True)
        self.assertIn("Página 2 de 2", last)
        empty = self.client.get("/tasks/?q=Ejercicio&estado=completada").get_data(as_text=True)
        self.assertIn("0 resultados", empty)
        self.assertIn("Página 1 de 1", empty)

    def test_members_cannot_bypass_search_scope_or_access_other_lists(self):
        self.authenticate(2)
        for query in ("q=Luis", "q=Luis&usuario_id=3", "page=99&usuario_id=3"):
            html = self.client.get("/tasks/?" + query).get_data(as_text=True)
            self.assertNotIn("Tarea de Luis", html)
            self.assertNotIn("Sin asignación", html)
        for path in ("/users/?q=Admin", "/payments/?estado=pagado"):
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_user_and_payment_filters_search_and_pagination(self):
        with self.app.app_context(), get_connection() as connection:
            connection.executemany(
                "INSERT INTO Usuarios (nombre, correo, contrasena, rol) VALUES (?, ?, ?, ?)",
                [(f"Persona {n}", f"persona{n}@example.test", "hash-no-exponer", "member")
                 for n in range(12)],
            )
        with self.app.app_context():
            for number in range(12):
                crud.create_payment(2, 1250, self.task_id, "USD", "otro", notas="Ejemplo")
            crud.create_payment(3, 1500, self.other_id, "DOP", "efectivo", "pagado")
        self.authenticate()
        users = self.client.get("/users/?q=persona&rol=member&activo=1&page=2").get_data(as_text=True)
        self.assertIn("12 resultados", users)
        self.assertIn("Página 2 de 2", users)
        self.assertNotIn("hash-no-exponer", users)
        inactive = self.client.get("/users/?activo=0").get_data(as_text=True)
        self.assertIn("1 resultados", inactive)
        self.assertIn("Inactivo", inactive)
        payments = self.client.get("/payments/?q=Ana&estado=pendiente&moneda=USD&metodo=otro&page=2").get_data(as_text=True)
        self.assertIn("12 resultados", payments)
        self.assertEqual(payments.count("USD 12.50"), 2)
        self.assertNotIn("DOP 15.00", payments)
        self.assertIn("DOP 15.00", self.client.get("/payments/?q=Luis&moneda=DOP").get_data(as_text=True))

    def test_invalid_query_filters_and_literal_search(self):
        self.authenticate()
        for path in ("/tasks/?estado=inventado", "/tasks/?prioridad=urgente",
                     "/users/?rol=otro", "/users/?activo=2", "/payments/?moneda=EUR",
                     "/payments/?metodo=paypal", "/payments/?estado=fallido",
                     "/tasks/?page=0", "/tasks/?page=-1", "/tasks/?page=abc",
                     "/tasks/?page=1.5", "/tasks/?page=" + "9" * 100,
                     "/tasks/?q=" + "x" * 101):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 400)
        for query in ("%", "_", "' OR 1=1 --", "<script>alert(1)</script>"):
            html = self.client.get("/tasks/", query_string={"q": query}).get_data(as_text=True)
            self.assertIn("0 resultados", html)
            self.assertNotIn("<script>", html)

    def test_empty_dashboard(self):
        with self.app.app_context(), get_connection() as connection:
            connection.execute("DELETE FROM Tareas")
        self.authenticate()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("0 tareas en total", html)
        self.assertIn("USD 0.00", html)
