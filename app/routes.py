from functools import wraps
import secrets
import sqlite3

import click
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from app.forms import validate_user_form
from app.utils.data import CRUD as crud
from app.utils.data.database import get_database_path, initialize_database
from migrations.add_user_active import migrate


def csrf_token() -> str:
    """Genera un token vinculado a la sesión."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def login_required(view):
    """Exige una cuenta activa comprobada en esta petición."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """Exige administrador, sin confiar en roles enviados por el navegador."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["rol"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def register_routes(app: Flask) -> None:
    """Registra rutas y comandos; no inicializa ni actualiza datos al importar."""
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        if not app.secret_key:
            return render_template("error.html", message="El acceso no está configurado."), 503
        user_id = session.get("user_id")
        if type(user_id) is int:
            user = crud.get_user_by_id(user_id)
            if user and user["activo"] == 1 and user["rol"] in {"admin", "member"}:
                g.user = user
            else:
                session.clear()
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            expected = session.get("csrf_token")
            supplied = request.form.get("csrf_token", "")
            if (not isinstance(expected, str) or not supplied or
                    not secrets.compare_digest(expected.encode(), supplied.encode())):
                abort(400, description="El formulario venció o no es válido. Vuelve a cargar la página.")

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        return render_template("error.html", message="No se pudo acceder a los datos. Inténtalo más tarde."), 503

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def request_error(error):
        messages = {403: "No tienes permiso para realizar esta acción.",
                    404: "No se encontró el registro solicitado."}
        return render_template("error.html", message=messages.get(error.code, error.description)), error.code

    @app.get("/")
    @login_required
    def index():
        return render_template("index.html")

    @app.route("/auth/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("index"))
        error = None
        email = request.form.get("correo", "").strip().lower()
        if request.method == "POST":
            password = request.form.get("contrasena", "")
            user = crud.get_user_for_auth_by_email(email) if len(email) <= 120 else None
            valid = False
            if user and user["activo"] == 1 and user["rol"] in {"admin", "member"} and len(password) <= 128:
                try:
                    valid = check_password_hash(user["contrasena"], password)
                except (ValueError, TypeError):
                    valid = False
            if valid:
                session.clear()
                session["user_id"] = user["id"]
                csrf_token()
                return redirect(url_for("index"))
            error = "Correo o contraseña incorrectos, o cuenta inactiva."
        return render_template("auth/login.html", error=error, email=email), (400 if error else 200)

    @app.post("/auth/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/users/")
    @admin_required
    def users_list():
        return render_template("users/list.html", users=crud.get_all_users())

    def user_or_404(user_id):
        user = crud.get_user_by_id(user_id)
        if user is None:
            abort(404)
        return user

    def save_user(user=None):
        editing = user is not None
        values = dict(user) if editing else {"rol": "member", "activo": "1"}
        errors = {}
        if request.method == "POST":
            values, errors = validate_user_form(request.form, editing=editing)
            existing = crud.get_user_by_email(values["correo"])
            if existing and (not editing or existing["id"] != user["id"]):
                errors["correo"] = "Ese correo ya pertenece a otro usuario."
            if editing and user["id"] == g.user["id"]:
                if values["rol"] != "admin" or values["activo"] != "1":
                    errors["rol"] = "No puedes quitarte el rol de administrador ni desactivar tu propia cuenta."
            if not errors:
                try:
                    arguments = (values["nombre"], values["correo"],
                                 request.form.get("contrasena") or None,
                                 values["telefono"] or None, values["rol"])
                    if editing:
                        affected = crud.update_user(user["id"], *arguments,
                                                    activo=int(values["activo"]))
                        if not affected:
                            abort(404)
                        user_id = user["id"]
                    else:
                        user_id = crud.create_user(*arguments, activo=int(values["activo"]))
                except sqlite3.IntegrityError:
                    errors["correo"] = "No se pudo guardar. Revisa el correo y los datos."
                else:
                    flash("Usuario actualizado." if editing else "Usuario creado.")
                    return redirect(url_for("user_detail", user_id=user_id))
        return render_template("users/form.html", values=values, errors=errors,
                               editing=editing), (400 if errors else 200)

    @app.route("/users/new", methods=["GET", "POST"])
    @admin_required
    def user_create():
        return save_user()

    @app.get("/users/<int:user_id>")
    @admin_required
    def user_detail(user_id):
        return render_template("users/detail.html", user=user_or_404(user_id))

    @app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
    @admin_required
    def user_edit(user_id):
        return save_user(user_or_404(user_id))

    @app.post("/users/<int:user_id>/delete")
    @admin_required
    def user_delete(user_id):
        user_or_404(user_id)
        if user_id == g.user["id"]:
            flash("No puedes eliminar tu propia cuenta.")
        else:
            try:
                crud.delete_user(user_id)
            except sqlite3.IntegrityError:
                flash("Este usuario tiene registros asociados. Desactívalo desde Editar para conservarlos.")
            else:
                flash("Usuario eliminado.")
                return redirect(url_for("users_list"))
        return redirect(url_for("user_detail", user_id=user_id))

    @app.cli.command("init-db")
    def init_db_command():
        """Inicializa SQLite explícitamente; no migra tablas existentes."""
        initialize_database()
        click.echo(f"Base de datos inicializada: {get_database_path()}")

    @app.cli.command("migrate-users")
    def migrate_users_command():
        """Añade activo con respaldo previo y sin cambiar contraseñas."""
        backup = migrate(get_database_path())
        click.echo(f"Actualización terminada. Respaldo: {backup}" if backup
                   else "La columna activo ya existe; no se realizaron cambios.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Nombre")
    @click.option("--email", prompt="Correo")
    @click.password_option(prompt="Contraseña", confirmation_prompt=True)
    def create_admin_command(name, email, password):
        """Crea el primer administrador; la contraseña se solicita sin mostrarla."""
        values, errors = validate_user_form({"nombre": name, "correo": email,
                                             "contrasena": password, "rol": "admin"})
        if errors:
            raise click.ClickException(" ".join(errors.values()))
        try:
            crud.create_first_admin(values["nombre"], values["correo"], password)
        except (ValueError, sqlite3.IntegrityError) as error:
            raise click.ClickException("No se pudo crear el administrador: revisa si ya existe un administrador o el correo está ocupado.") from error
        click.echo("Administrador creado. Ya puedes iniciar sesión.")

    @app.cli.command("reset-password")
    @click.option("--email", prompt="Correo")
    @click.password_option(prompt="Nueva contraseña", confirmation_prompt=True)
    def reset_password_command(email, password):
        """Restablece explícitamente una clave sin convertir contraseñas históricas."""
        if not 8 <= len(password) <= 128:
            raise click.ClickException("La contraseña debe tener entre 8 y 128 caracteres.")
        user = crud.get_user_by_email(email.strip().lower())
        if user is None:
            raise click.ClickException("No existe un usuario con ese correo.")
        crud.update_user(user["id"], user["nombre"], user["correo"], password,
                         user["telefono"], user["rol"], activo=user["activo"])
        click.echo("Contraseña actualizada; el estado de la cuenta se conserva.")
