import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from run import app
from app.utils.data.database import (
    DB_PATH,
    PROJECT_ROOT,
    get_connection,
    get_database_path,
)


class StageOneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "prueba con espacios.db"
        self.original_config = app.config.copy()
        app.config.update(TESTING=True, DATABASE_PATH=str(self.database_path))

    def tearDown(self):
        app.config.clear()
        app.config.update(self.original_config)
        self.directory.cleanup()

    def initialize(self):
        result = app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_imports_and_home_do_not_create_database(self):
        environment = os.environ.copy()
        environment.update(DATABASE_PATH=str(self.database_path), FLASK_DEBUG="0")
        result = subprocess.run(
            [sys.executable, "-B", "-c",
             "import run; import app.utils.data.CRUD; "
             "assert not run.app.debug; "
             "assert run.app.test_client().get('/').status_code == 200"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.database_path.exists())

    def test_home_renders_spanish_template_without_database(self):
        response = app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('lang="es"', response.get_data(as_text=True))
        self.assertIn("Sala de Tareas", response.get_data(as_text=True))
        self.assertFalse(self.database_path.exists())

    def test_missing_database_is_not_created_by_connection(self):
        with app.app_context():
            with self.assertRaises(sqlite3.OperationalError):
                with get_connection():
                    pass
        self.assertFalse(self.database_path.exists())

    def test_explicit_initialization_preserves_existing_records(self):
        self.initialize()
        with app.app_context(), get_connection() as connection:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(
                {"Usuarios", "Tareas", "Pagos", "Materias", "Asistencias"}
                <= tables
            )
            connection.execute(
                "INSERT INTO Materias (nombre) VALUES (?)", ("Prueba",)
            )
        self.initialize()
        with app.app_context(), get_connection() as connection:
            self.assertEqual(
                connection.execute("SELECT nombre FROM Materias").fetchone()[0],
                "Prueba",
            )

    def test_foreign_keys_and_rollback(self):
        self.initialize()
        with app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                with get_connection() as connection:
                    self.assertEqual(
                        connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
                    )
                    connection.execute(
                        "INSERT INTO Materias (nombre) VALUES (?)", ("Temporal",)
                    )
                    connection.execute(
                        "INSERT INTO Asistencias (usuario_id) VALUES (?)", (999,)
                    )
            with get_connection() as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM Materias").fetchone()[0],
                    0,
                )

    def test_relative_database_path_is_resolved_from_project_root(self):
        app.config["DATABASE_PATH"] = "tests/otra.db"
        with app.app_context():
            self.assertEqual(
                get_database_path(), PROJECT_ROOT / "tests" / "otra.db"
            )
        self.assertEqual(DB_PATH, PROJECT_ROOT / "saladetareas.db")

    def test_environment_config_and_sessions(self):
        environment = os.environ.copy()
        environment.update(
            DATABASE_PATH=str(self.database_path),
            SECRET_KEY="clave-exclusiva-de-pruebas",
            FLASK_DEBUG="1",
            SESSION_COOKIE_SECURE="1",
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c",
             "from run import app; "
             "assert app.debug; "
             "assert app.config['SESSION_COOKIE_SECURE']; "
             "client = app.test_client(); "
             "context = client.session_transaction(); "
             "session = context.__enter__(); session['test'] = True; "
             "context.__exit__(None, None, None)"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.database_path.exists())


if __name__ == "__main__":
    unittest.main()
