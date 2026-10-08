"""Recorridos completos con login real, formularios y SQLite temporal."""

from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from flask import Flask

from app.routes import register_routes
from app.utils.data import CRUD as crud
from app.utils.data.database import get_connection


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("name") == "csrf_token":
            self.token = values.get("value")
        if tag == "a" and values.get("href", "").startswith("/"):
            self.links.append(values["href"])


class FinalFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "final.db"
        self.app = Flask(__name__, template_folder=str(Path("app/templates").resolve()))
        self.app.config.update(TESTING=True, SECRET_KEY="solo-pruebas",
                               DATABASE_PATH=str(self.path))
        register_routes(self.app)
        self.client = self.app.test_client()
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        result = runner.invoke(args=["create-admin", "--name", "Admin",
                                     "--email", "admin@example.test"],
                               input="clave-flujo\nclave-flujo\n")
        self.assertEqual(result.exit_code, 0, result.output)

    def token(self):
        response = self.client.get("/auth/login", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        parser = FormParser()
        parser.feed(response.get_data(as_text=True))
        self.assertTrue(parser.token)
        return parser.token

    def submit(self, path, data=None, **kwargs):
        return self.client.post(path, data={"csrf_token": self.token(), **(data or {})},
                                **kwargs)

    def login(self, email="admin@example.test"):
        response = self.submit("/auth/login", {"correo": email, "contrasena": "clave-flujo"})
        self.assertEqual(response.status_code, 302)

    def create_record(self, path, data):
        response = self.submit(path, data)
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return response.location, int(response.location.rsplit("/", 1)[1])

    def test_complete_admin_member_payment_and_deactivation_flow(self):
        self.login()
        user_url, user_id = self.create_record("/users/new", {
            "nombre": "Compañero", "correo": "member@example.test",
            "contrasena": "clave-flujo", "rol": "member", "activo": "1",
        })
        task_data = {"titulo": "Ejercicio final", "descripcion": "Prueba del curso",
                     "estado": "pendiente", "prioridad": "alta",
                     "usuario_asignado_id": str(user_id)}
        task_url, task_id = self.create_record("/tasks/new", task_data)
        self.assertEqual(self.submit(task_url + "/edit", {
            **task_data, "descripcion": "Descripción corregida"
        }).status_code, 302)
        pay_url, payment_id = self.create_record("/payments/new", {
            "tarea_id": str(task_id), "usuario_id": str(user_id), "monto": "12.50",
            "moneda": "DOP", "metodo": "otro", "estado": "pendiente", "notas": "Clase",
        })
        for result in ("rechazado", "cancelado"):
            self.assertEqual(self.submit(pay_url + "/simulate", {"resultado": result}).status_code, 302)
            with self.app.app_context():
                self.assertEqual(crud.get_payment_by_id(payment_id)["estado"], "pendiente")
        self.assertEqual(self.submit(pay_url + "/simulate", {"resultado": "aprobado"}).status_code, 302)
        with self.app.app_context():
            paid = crud.get_payment_by_id(payment_id)
            self.assertEqual(paid["monto"], 1250)
            self.assertIn("Sin cobro real", paid["notas"])
            self.assertEqual(crud.get_task_by_id(task_id)["estado"], "pendiente")
        self.assertIn("DOP 12.50", self.client.get("/").get_data(as_text=True))
        self.assertIn("Ejercicio final", self.client.get("/tasks/?q=Ejercicio&prioridad=alta").get_data(as_text=True))
        self.assertIn("DOP 12.50", self.client.get("/payments/?estado=pagado&moneda=DOP").get_data(as_text=True))

        self.submit("/auth/logout")
        self.login("member@example.test")
        self.assertEqual(self.client.get(task_url).status_code, 200)
        self.assertEqual(self.client.get(pay_url).status_code, 403)
        self.assertEqual(self.submit(pay_url + "/simulate", {"resultado": "aprobado"}).status_code, 403)
        self.assertEqual(self.submit(task_url + "/edit", {
            "estado": "completada", "titulo": "Manipulado"
        }).status_code, 302)
        self.assertNotIn("Resumen de pagos", self.client.get("/").get_data(as_text=True))
        self.submit("/auth/logout")
        self.login()
        blocked = self.submit(task_url + "/delete", follow_redirects=True)
        self.assertIn("No se puede eliminar", blocked.get_data(as_text=True))
        self.assertEqual(self.submit(pay_url + "/delete").status_code, 302)
        with self.app.app_context():
            annulled = crud.get_payment_by_id(payment_id)
            self.assertEqual(annulled["estado"], "anulado")
            self.assertEqual(annulled["fecha_pago"], paid["fecha_pago"])
            self.assertEqual(crud.get_task_by_id(task_id)["titulo"], "Ejercicio final")
        response = self.submit(user_url + "/delete", follow_redirects=True)
        self.assertIn("registros asociados", response.get_data(as_text=True))
        self.assertEqual(self.submit(user_url + "/edit", {
            "nombre": "Compañero", "correo": "member@example.test",
            "contrasena": "", "rol": "member", "activo": "0",
        }).status_code, 302)
        self.submit("/auth/logout")
        self.assertEqual(self.submit("/auth/login", {
            "correo": "member@example.test", "contrasena": "clave-flujo"
        }).status_code, 400)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_unassociated_records_can_be_deleted_and_navigation_works(self):
        self.login()
        user_url, _ = self.create_record("/users/new", {
            "nombre": "Temporal", "correo": "temp@example.test",
            "contrasena": "clave-flujo", "rol": "member", "activo": "1",
        })
        task_url, _ = self.create_record("/tasks/new", {
            "titulo": "Temporal", "estado": "pendiente", "prioridad": "baja",
        })
        for path in ("/", "/users/", "/users/new", user_url, user_url + "/edit",
                     "/tasks/", "/tasks/new", task_url, task_url + "/edit",
                     "/payments/", "/payments/new"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            parser = FormParser()
            parser.feed(response.get_data(as_text=True))
            for link in parser.links:
                self.assertEqual(self.client.get(link).status_code, 200, (path, link))
        self.assertEqual(self.submit(task_url + "/delete").status_code, 302)
        self.assertEqual(self.submit(user_url + "/delete").status_code, 302)
        self.assertEqual(self.client.get(task_url).status_code, 404)
        self.assertEqual(self.client.get(user_url).status_code, 404)

    def test_invalid_posts_keep_database_and_passwords_private(self):
        self.login()
        with self.app.app_context(), get_connection() as connection:
            before = list(connection.iterdump())
        response = self.submit("/users/new", {
            "nombre": "Conservar este nombre", "correo": "incorrecto",
            "contrasena": "clave-que-no-debe-volver", "rol": "inventado", "activo": "1",
        })
        self.assertEqual(response.status_code, 400)
        html = response.get_data(as_text=True)
        self.assertIn("Conservar este nombre", html)
        self.assertNotIn("clave-que-no-debe-volver", html)
        self.assertEqual(self.client.post("/tasks/new", data={"titulo": "Sin token"}).status_code, 400)
        self.assertEqual(self.client.get("/auth/logout").status_code, 405)
        self.assertEqual(self.client.get("/ruta-inexistente").status_code, 404)
        with self.app.app_context(), get_connection() as connection:
            self.assertEqual(list(connection.iterdump()), before)
        self.assertEqual(self.submit("/auth/logout").status_code, 302)
        self.assertEqual(self.client.get("/tasks/").status_code, 302)
