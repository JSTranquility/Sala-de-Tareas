import click
from flask import Flask, render_template

from app.utils.data.database import get_database_path, initialize_database


def register_routes(app: Flask) -> None:
    """Conecta rutas y comandos sin imports circulares ni cambios de datos."""
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.cli.command("init-db")
    def init_db_command():
        """Inicializa SQLite explícitamente; no migra tablas existentes."""
        initialize_database()
        click.echo(f"Base de datos inicializada: {get_database_path()}")
