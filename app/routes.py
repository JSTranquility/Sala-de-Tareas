"""Rutas web, comprobaciones de acceso y comandos de administración."""

from functools import wraps
import secrets
import sqlite3

import click
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from app.forms import (
    PAYMENT_CURRENCIES,
    PAYMENT_METHODS,
    PAYMENT_STATES,
    TASK_PRIORITIES,
    TASK_STATES,
    validate_task_form,
    validate_subject_form,
    validate_task_status,
    validate_user_form,
    validate_payment_form,
    validate_payment_notes,
)
from app.models import format_amount
from app.utils.paypal_simulator import simulate_payment
from app.utils.data import CRUD as crud
from app.utils.data.database import get_database_path, initialize_database
from migrations.add_task_fields import migrate as migrate_tasks
from migrations.add_user_active import migrate as migrate_users
from migrations.add_payment_fields import migrate as migrate_payments


# Comprobaciones compartidas por el login y las peticiones de la aplicación.


def is_active_user(user: dict | None) -> bool:
    """Comprueba que la cuenta exista, esté activa y tenga un rol permitido."""
    if user is None:
        return False
    if user["activo"] != 1:
        return False
    return user["rol"] in {"admin", "member"}


def password_matches(user: dict | None, password: str) -> bool:
    """Verifica la contraseña únicamente para una cuenta que puede acceder."""
    if not is_active_user(user) or len(password) > 128:
        return False
    try:
        return check_password_hash(user["contrasena"], password)
    except (ValueError, TypeError):
        # Una credencial histórica inválida no debe interrumpir el login.
        return False


def csrf_token() -> str:
    """Genera un token vinculado a la sesión."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def check_csrf() -> None:
    """Rechaza operaciones cuyo token no corresponda a la sesión actual."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return

    expected_token = session.get("csrf_token")
    submitted_token = request.form.get("csrf_token", "")
    error_message = (
        "El formulario venció o no es válido. Vuelve a cargar la página."
    )
    if not isinstance(expected_token, str) or not submitted_token:
        abort(400, description=error_message)

    # Se comparan bytes para admitir también entradas con caracteres acentuados.
    tokens_match = secrets.compare_digest(
        expected_token.encode(), submitted_token.encode()
    )
    if not tokens_match:
        abort(400, description=error_message)


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


def list_context(entity: str, filter_options: dict) -> dict:
    """Valida filtros GET y conserva sus valores al cambiar de página."""
    query = request.args.get("q", "").strip()
    if len(query) > 100:
        abort(400, description="La búsqueda admite hasta 100 caracteres.")
    filters = {name: request.args.get(name, "") for name in filter_options}
    for name, value in filters.items():
        if value and value not in filter_options[name][1]:
            abort(400, description="Selecciona un filtro válido.")
    page_text = request.args.get("page", "1")
    if (not page_text.isascii() or not page_text.isdigit()
            or len(page_text) > 9 or int(page_text) < 1):
        abort(400, description="La página debe ser un entero positivo.")
    assigned = (g.user["id"]
                if entity == "tasks" and g.user["rol"] != "admin" else None)
    pagination = crud.get_filtered_page(entity, query, filters, int(page_text), assigned)
    params = {"q": query, **filters}
    return {entity: pagination["items"], "pagination": pagination,
            "query": query, "filters": filters, "filter_options": filter_options,
            "previous_url": url_for(request.endpoint, **params, page=pagination["page"] - 1)
            if pagination["page"] > 1 else None,
            "next_url": url_for(request.endpoint, **params, page=pagination["page"] + 1)
            if pagination["page"] < pagination["pages"] else None}


def register_routes(app: Flask) -> None:
    """Registra rutas y comandos; no inicializa ni actualiza datos al importar."""
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["task_states"] = TASK_STATES
    app.jinja_env.globals["task_priorities"] = TASK_PRIORITIES
    app.jinja_env.globals["payment_states"] = PAYMENT_STATES
    app.jinja_env.globals["payment_currencies"] = PAYMENT_CURRENCIES
    app.jinja_env.globals["payment_methods"] = PAYMENT_METHODS
    app.jinja_env.filters["amount"] = format_amount

    # Antes de cada petición: cargar al usuario y comprobar el formulario.

    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        if not app.secret_key:
            return render_template(
                "error.html", message="El acceso no está configurado."
            ), 503

        user_id = session.get("user_id")
        if type(user_id) is int:
            user = crud.get_user_by_id(user_id)
            if is_active_user(user):
                g.user = user
            else:
                session.clear()
        check_csrf()

    # Errores que pueden aparecer en distintas rutas.

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        return render_template(
            "error.html",
            message="No se pudo acceder a los datos. Inténtalo más tarde.",
        ), 503

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def request_error(error):
        messages = {
            403: "No tienes permiso para realizar esta acción.",
            404: "No se encontró el registro solicitado.",
        }
        message = messages.get(error.code, error.description)
        return render_template("error.html", message=message), error.code

    # Inicio y acceso.

    @app.get("/")
    @login_required
    def index():
        assigned = g.user["id"] if g.user["rol"] != "admin" else None
        return render_template("index.html", dashboard=crud.get_dashboard(assigned))

    @app.route("/auth/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("index"))
        error = None
        email = request.form.get("correo", "").strip().lower()
        if request.method == "POST":
            password = request.form.get("contrasena", "")
            user = None
            if len(email) <= 120:
                user = crud.get_user_for_auth_by_email(email)

            if password_matches(user, password):
                session.clear()
                session["user_id"] = user["id"]
                csrf_token()
                return redirect(url_for("index"))
            error = "Correo o contraseña incorrectos, o cuenta inactiva."
        status_code = 400 if error else 200
        return render_template(
            "auth/login.html", error=error, email=email
        ), status_code

    @app.post("/auth/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # Usuarios: todas las rutas requieren un administrador.

    @app.get("/users/")
    @admin_required
    def users_list():
        return render_template("users/list.html", **list_context("users", {
            "rol": ("Rol", {"admin": "Administrador", "member": "Miembro"}),
            "activo": ("Estado", {"1": "Activo", "0": "Inactivo"}),
        }))

    def user_or_404(user_id):
        user = crud.get_user_by_id(user_id)
        if user is None:
            abort(404)
        return user

    def save_user(user=None):
        """Muestra el formulario o guarda un usuario después de validarlo."""
        editing = user is not None
        if editing:
            values = dict(user)
        else:
            values = {"rol": "member", "activo": "1"}
        errors = {}

        if request.method == "POST":
            values, errors = validate_user_form(request.form, editing=editing)
            existing = crud.get_user_by_email(values["correo"])
            if existing:
                same_user = editing and existing["id"] == user["id"]
                if not same_user:
                    errors["correo"] = "Ese correo ya pertenece a otro usuario."

            if editing and user["id"] == g.user["id"]:
                if values["rol"] != "admin" or values["activo"] != "1":
                    errors["rol"] = (
                        "No puedes quitarte el rol de administrador "
                        "ni desactivar tu propia cuenta."
                    )

            if not errors:
                try:
                    password = request.form.get("contrasena") or None
                    if editing:
                        affected = crud.update_user(
                            id=user["id"],
                            nombre=values["nombre"],
                            correo=values["correo"],
                            contrasena=password,
                            telefono=values["telefono"] or None,
                            rol=values["rol"],
                            activo=int(values["activo"]),
                        )
                        if not affected:
                            abort(404)
                        user_id = user["id"]
                    else:
                        user_id = crud.create_user(
                            nombre=values["nombre"],
                            correo=values["correo"],
                            contrasena=password,
                            telefono=values["telefono"] or None,
                            rol=values["rol"],
                            activo=int(values["activo"]),
                        )
                except sqlite3.IntegrityError:
                    errors["correo"] = (
                        "No se pudo guardar. Revisa el correo y los datos."
                    )
                else:
                    flash("Usuario actualizado." if editing else "Usuario creado.")
                    return redirect(url_for("user_detail", user_id=user_id))
        status_code = 400 if errors else 200
        return render_template(
            "users/form.html", values=values, errors=errors, editing=editing
        ), status_code

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
                flash(
                    "Este usuario tiene registros asociados. "
                    "Desactívalo desde Editar para conservarlos."
                )
            else:
                flash("Usuario eliminado.")
                return redirect(url_for("users_list"))
        return redirect(url_for("user_detail", user_id=user_id))

    # Materias: gestión reservada a administradores.

    def subject_or_404(subject_id):
        subject = crud.get_subject_by_id(subject_id)
        if subject is None:
            abort(404)
        return subject

    @app.get("/subjects/")
    @admin_required
    def subjects_list():
        return render_template("subjects/list.html", subjects=crud.get_all_subjects())

    def save_subject(subject=None):
        values = dict(subject) if subject else {}
        errors = {}
        if request.method == "POST":
            values, errors = validate_subject_form(request.form)
            if not errors:
                if subject:
                    if not crud.update_subject(subject["id"], values["nombre"],
                                               values["descripcion"] or None):
                        abort(404)
                    subject_id = subject["id"]
                else:
                    subject_id = crud.create_subject(values["nombre"],
                                                     values["descripcion"] or None)
                flash("Materia actualizada." if subject else "Materia creada.")
                return redirect(url_for("subject_detail", subject_id=subject_id))
        return render_template("subjects/form.html", values=values, errors=errors,
                               editing=subject is not None), 400 if errors else 200

    @app.route("/subjects/new", methods=["GET", "POST"])
    @admin_required
    def subject_create():
        return save_subject()

    @app.get("/subjects/<int:subject_id>")
    @admin_required
    def subject_detail(subject_id):
        return render_template("subjects/detail.html", subject=subject_or_404(subject_id))

    @app.route("/subjects/<int:subject_id>/edit", methods=["GET", "POST"])
    @admin_required
    def subject_edit(subject_id):
        return save_subject(subject_or_404(subject_id))

    @app.post("/subjects/<int:subject_id>/delete")
    @admin_required
    def subject_delete(subject_id):
        subject_or_404(subject_id)
        try:
            if not crud.delete_subject(subject_id):
                abort(404)
        except sqlite3.IntegrityError:
            flash("La materia tiene tareas asociadas. Reasígnalas antes de eliminarla.")
            return redirect(url_for("subject_detail", subject_id=subject_id))
        flash("Materia eliminada.")
        return redirect(url_for("subjects_list"))

    # Tareas: los miembros solo pueden consultar y cambiar su propio estado.

    @app.get("/tasks/")
    @login_required
    def tasks_list():
        return render_template("tasks/list.html", **list_context("tasks", {
            "estado": ("Estado", TASK_STATES),
            "prioridad": ("Prioridad", TASK_PRIORITIES),
        }))

    def task_or_404(task_id):
        """Busca la tarea y comprueba quién puede acceder a ese registro."""
        task = crud.get_task_by_id(task_id)
        if task is None:
            abort(404)
        if g.user["rol"] != "admin" and task["usuario_id"] != g.user["id"]:
            abort(403)
        return task

    def validate_task_relations(values, errors):
        """Comprueba los IDs válidos y añade errores si no se pueden usar."""
        assigned_user_id = None
        subject_id = None
        if values["usuario_asignado_id"] and "usuario_asignado_id" not in errors:
            assigned_user_id = int(values["usuario_asignado_id"])
            assigned_user = crud.get_user_by_id(assigned_user_id)
            if not assigned_user or assigned_user["activo"] != 1:
                errors["usuario_asignado_id"] = (
                    "Selecciona un usuario activo existente."
                )

        if values["materia_id"] and "materia_id" not in errors:
            subject_id = int(values["materia_id"])
            if crud.get_subject_by_id(subject_id) is None:
                errors["materia_id"] = "Selecciona una materia existente."

        return assigned_user_id, subject_id

    def save_task(task=None):
        """Muestra el formulario o guarda una tarea validada por el administrador."""
        editing = task is not None
        if editing:
            values = dict(task)
            values["usuario_asignado_id"] = task["usuario_id"]
            creator_name = task["creador_nombre"]
        else:
            values = {"estado": "pendiente", "prioridad": "media"}
            creator_name = g.user["nombre"]

        # Las fechas históricas se conservan hasta editar; el formulario usa días.
        if editing and values["fecha_vencimiento"]:
            values["fecha_vencimiento"] = values["fecha_vencimiento"][:10]
        errors = {}
        if request.method == "POST":
            values, errors = validate_task_form(request.form)
            assigned_user_id, subject_id = validate_task_relations(values, errors)
            if not errors:
                try:
                    if editing:
                        affected = crud.update_task(
                            id=task["id"],
                            titulo=values["titulo"],
                            descripcion=values["descripcion"] or None,
                            fecha_vencimiento=values["fecha_vencimiento"] or None,
                            estado=values["estado"],
                            usuario_id=assigned_user_id,
                            materia_id=subject_id,
                            prioridad=values["prioridad"],
                        )
                        if not affected:
                            abort(404)
                        task_id = task["id"]
                    else:
                        task_id = crud.create_task(
                            titulo=values["titulo"],
                            descripcion=values["descripcion"] or None,
                            fecha_vencimiento=values["fecha_vencimiento"] or None,
                            estado=values["estado"],
                            usuario_id=assigned_user_id,
                            materia_id=subject_id,
                            prioridad=values["prioridad"],
                            creador_id=g.user["id"],
                        )
                except sqlite3.IntegrityError:
                    errors["general"] = (
                        "No se pudo guardar. Revisa las relaciones de la tarea."
                    )
                else:
                    flash("Tarea actualizada." if editing else "Tarea creada.")
                    return redirect(url_for("task_detail", task_id=task_id))
        active_users = []
        for user in crud.get_all_users():
            if user["activo"] == 1:
                active_users.append(user)

        # Mostrar una asignación inactiva histórica sin ofrecerla para nuevas tareas.
        inactive_assigned = None
        if editing and task["usuario_id"]:
            assigned_user = crud.get_user_by_id(task["usuario_id"])
            if assigned_user and assigned_user["activo"] == 0:
                inactive_assigned = assigned_user

        status_code = 400 if errors else 200
        return render_template(
            "tasks/form.html",
            values=values,
            errors=errors,
            editing=editing,
            users=active_users,
            subjects=crud.get_all_subjects(),
            creator_name=creator_name,
            inactive_assigned=inactive_assigned,
        ), status_code

    @app.route("/tasks/new", methods=["GET", "POST"])
    @admin_required
    def task_create():
        return save_task()

    @app.get("/tasks/<int:task_id>")
    @login_required
    def task_detail(task_id):
        task = task_or_404(task_id)
        return render_template("tasks/detail.html", task=task, values=task, errors={})

    @app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @login_required
    def task_edit(task_id):
        task = task_or_404(task_id)
        if g.user["rol"] == "admin":
            return save_task(task)
        values = {"estado": task["estado"]}
        errors = {}
        if request.method == "POST":
            values, errors = validate_task_status(request.form)
            if not errors:
                affected = crud.update_task_status(
                    task_id, g.user["id"], values["estado"]
                )
                if not affected:
                    abort(404)
                flash("Estado de la tarea actualizado.")
                return redirect(url_for("task_detail", task_id=task_id))
        status_code = 400 if errors else 200
        return render_template(
            "tasks/detail.html", task=task, values=values, errors=errors
        ), status_code

    @app.post("/tasks/<int:task_id>/delete")
    @admin_required
    def task_delete(task_id):
        task_or_404(task_id)
        try:
            affected = crud.delete_task(task_id)
            if not affected:
                abort(404)
        except sqlite3.IntegrityError:
            flash(
                "La tarea tiene pagos o registros asociados. No se puede eliminar."
            )
            return redirect(url_for("task_detail", task_id=task_id))
        flash("Tarea eliminada.")
        return redirect(url_for("tasks_list"))

    # Pagos: solo administradores pueden consultar y modificar registros.

    @app.get("/payments/")
    @admin_required
    def payments_list():
        return render_template("payments/list.html", **list_context("payments", {
            "estado": ("Estado", PAYMENT_STATES),
            "moneda": ("Moneda", PAYMENT_CURRENCIES),
            "metodo": ("Método", PAYMENT_METHODS),
        }))

    def payment_or_404(payment_id):
        payment = crud.get_payment_by_id(payment_id)
        if payment is None:
            abort(404)
        return payment

    def validate_payment_relations(values, errors):
        if "tarea_id" not in errors:
            task = crud.get_task_by_id(int(values["tarea_id"]))
            if task is None or task["estado"] == "cancelada":
                errors["tarea_id"] = "Selecciona una tarea existente que no esté cancelada."
        if "usuario_id" not in errors:
            recipient = crud.get_user_by_id(int(values["usuario_id"]))
            if recipient is None or recipient["activo"] != 1:
                errors["usuario_id"] = "Selecciona un usuario receptor activo existente."

    def save_paid_payment_notes(payment):
        """Una vez pagado, el formulario solo permite cambiar las notas."""
        values = {"notas": payment["notas"] or ""}
        errors = {}
        if request.method == "POST":
            values, errors = validate_payment_notes(request.form)
            if not errors:
                affected = crud.update_payment_notes(
                    payment["id"], values["notas"] or None
                )
                if not affected:
                    abort(404)
                flash("Notas del pago actualizadas.")
                return redirect(url_for("payment_detail", payment_id=payment["id"]))
        status_code = 400 if errors else 200
        return render_template(
            "payments/form.html", values=values, errors=errors, editing=True,
            payment=payment, notes_only=True,
        ), status_code

    def save_payment(payment=None):
        """Valida, registra o completa un pago sin confiar en fechas del navegador."""
        editing = payment is not None
        if editing and payment["estado"] == "anulado":
            abort(403)
        if editing and payment["estado"] == "pagado":
            return save_paid_payment_notes(payment)
        if editing:
            values = dict(payment)
            values["monto"] = format_amount(payment["monto"])
        else:
            values = {"estado": "pendiente", "moneda": "", "metodo": ""}
        errors = {}

        if request.method == "POST":
            values, errors = validate_payment_form(request.form)
            validate_payment_relations(values, errors)
            if not errors:
                try:
                    if editing:
                        affected = crud.update_payment(
                            payment_id=payment["id"],
                            usuario_id=int(values["usuario_id"]),
                            monto_centavos=values["monto_centavos"],
                            tarea_id=int(values["tarea_id"]),
                            moneda=values["moneda"],
                            metodo=values["metodo"],
                            estado=values["estado"],
                            notas=values["notas"] or None,
                        )
                        if not affected:
                            abort(404)
                        payment_id = payment["id"]
                    else:
                        payment_id = crud.create_payment(
                            usuario_id=int(values["usuario_id"]),
                            monto_centavos=values["monto_centavos"],
                            tarea_id=int(values["tarea_id"]),
                            moneda=values["moneda"],
                            metodo=values["metodo"],
                            estado=values["estado"],
                            notas=values["notas"] or None,
                        )
                except ValueError as error:
                    errors["general"] = str(error)
                except sqlite3.IntegrityError:
                    errors["general"] = (
                        "No se pudo guardar. Revisa los datos y sus relaciones."
                    )
                else:
                    flash("Pago actualizado." if editing else "Pago registrado.")
                    return redirect(url_for("payment_detail", payment_id=payment_id))

        tasks = [task for task in crud.get_all_tasks() if task["estado"] != "cancelada"]
        users = [user for user in crud.get_all_users() if user["activo"] == 1]
        status_code = 400 if errors else 200
        return render_template(
            "payments/form.html", values=values, errors=errors, editing=editing,
            payment=payment, notes_only=False, tasks=tasks, users=users,
        ), status_code

    @app.route("/payments/new", methods=["GET", "POST"])
    @admin_required
    def payment_create():
        return save_payment()

    @app.get("/payments/<int:payment_id>")
    @admin_required
    def payment_detail(payment_id):
        return render_template("payments/detail.html", payment=payment_or_404(payment_id))

    @app.route("/payments/<int:payment_id>/simulate", methods=["GET", "POST"])
    @admin_required
    def payment_simulate(payment_id):
        payment = payment_or_404(payment_id)
        try:
            if payment["estado"] != "pendiente":
                raise ValueError("Solo se pueden simular pagos pendientes.")
            if payment["pendiente_completar"] or not payment["fecha_creacion"]:
                raise ValueError("Completa los datos históricos antes de simular el pago.")
            task = crud.get_task_by_id(payment["tarea_id"])
            recipient = crud.get_user_by_id(payment["usuario_id"])
            if task is None or task["estado"] == "cancelada":
                raise ValueError("La tarea no existe o está cancelada.")
            if not is_active_user(recipient):
                raise ValueError("El usuario receptor debe estar activo.")
            if request.method == "POST":
                result = simulate_payment(
                    payment_id, payment["monto"], payment["moneda"],
                    request.form.get("resultado", ""),
                )
                if result["resultado"] == "aprobado":
                    if not crud.mark_payment_paid(payment_id):
                        raise ValueError("El pago ya cambió. Vuelve a consultar su detalle.")
                flash(result["mensaje"])
                return redirect(url_for("payment_detail", payment_id=payment_id))
        except ValueError as error:
            flash(str(error))
            return render_template("payments/simulate.html", payment=payment,
                                   can_simulate=False), 400
        return render_template("payments/simulate.html", payment=payment,
                               can_simulate=True)

    @app.route("/payments/<int:payment_id>/edit", methods=["GET", "POST"])
    @admin_required
    def payment_edit(payment_id):
        return save_payment(payment_or_404(payment_id))

    @app.post("/payments/<int:payment_id>/delete")
    @admin_required
    def payment_delete(payment_id):
        payment_or_404(payment_id)
        if crud.annul_payment(payment_id):
            flash("Pago anulado. El registro y su fecha de pago se conservan.")
        else:
            flash("El pago ya estaba anulado.")
        return redirect(url_for("payment_detail", payment_id=payment_id))

    # Comandos de terminal: solo se ejecutan cuando se solicitan explícitamente.

    @app.cli.command("migrate-payments")
    def migrate_payments_command():
        """Convierte importes y añade relaciones con respaldo explícito."""
        try:
            backup = migrate_payments(get_database_path())
        except (ValueError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        if backup:
            click.echo(f"Actualización terminada. Respaldo: {backup}")
        else:
            click.echo("Pagos ya está actualizada; no se realizaron cambios.")
        pending_ids = []
        for payment in crud.get_all_payments():
            if payment["pendiente_completar"]:
                pending_ids.append(str(payment["id"]))
        if pending_ids:
            click.echo(
                "Pagos históricos con información pendiente (ID): "
                + ", ".join(pending_ids)
            )

    @app.cli.command("migrate-tasks")
    def migrate_tasks_command():
        """Actualiza tareas explícitamente con respaldo previo."""
        try:
            backup = migrate_tasks(get_database_path())
        except (ValueError, sqlite3.Error) as error:
            raise click.ClickException(str(error)) from error
        if backup:
            click.echo(f"Actualización terminada. Respaldo: {backup}")
        else:
            click.echo("Tareas ya está actualizada; no se realizaron cambios.")

        pending_ids = []
        for task in crud.get_all_tasks():
            if task["creador_id"] is None or task["prioridad"] is None:
                pending_ids.append(str(task["id"]))
        if pending_ids:
            click.echo(
                "Tareas históricas con información pendiente (ID): "
                + ", ".join(pending_ids)
            )

    @app.cli.command("init-db")
    def init_db_command():
        """Inicializa SQLite explícitamente; no migra tablas existentes."""
        initialize_database()
        click.echo(f"Base de datos inicializada: {get_database_path()}")

    @app.cli.command("migrate-users")
    def migrate_users_command():
        """Añade activo con respaldo previo y sin cambiar contraseñas."""
        backup = migrate_users(get_database_path())
        if backup:
            click.echo(f"Actualización terminada. Respaldo: {backup}")
        else:
            click.echo("La columna activo ya existe; no se realizaron cambios.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Nombre")
    @click.option("--email", prompt="Correo")
    @click.password_option(prompt="Contraseña", confirmation_prompt=True)
    def create_admin_command(name, email, password):
        """Crea el primer administrador; la contraseña se solicita sin mostrarla."""
        values, errors = validate_user_form({
            "nombre": name,
            "correo": email,
            "contrasena": password,
            "rol": "admin",
        })
        if errors:
            raise click.ClickException(" ".join(errors.values()))
        try:
            crud.create_first_admin(values["nombre"], values["correo"], password)
        except (ValueError, sqlite3.IntegrityError) as error:
            raise click.ClickException(
                "No se pudo crear el administrador: revisa si ya existe "
                "un administrador o el correo está ocupado."
            ) from error
        click.echo("Administrador creado. Ya puedes iniciar sesión.")

    @app.cli.command("reset-password")
    @click.option("--email", prompt="Correo")
    @click.password_option(prompt="Nueva contraseña", confirmation_prompt=True)
    def reset_password_command(email, password):
        """Restablece explícitamente una clave sin convertir contraseñas históricas."""
        if not 8 <= len(password) <= 128:
            raise click.ClickException(
                "La contraseña debe tener entre 8 y 128 caracteres."
            )
        user = crud.get_user_by_email(email.strip().lower())
        if user is None:
            raise click.ClickException("No existe un usuario con ese correo.")
        crud.update_user(
            id=user["id"],
            nombre=user["nombre"],
            correo=user["correo"],
            contrasena=password,
            telefono=user["telefono"],
            rol=user["rol"],
            activo=user["activo"],
        )
        click.echo("Contraseña actualizada; el estado de la cuenta se conserva.")
