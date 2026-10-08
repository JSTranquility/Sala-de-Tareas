"""Validaciones de formularios: devuelve los valores y los errores por campo."""

import re
from collections.abc import Mapping
from datetime import date

from app.models import (
    PAYMENT_CURRENCIES, PAYMENT_METHODS, PAYMENT_STATES, amount_to_cents,
)


TASK_STATES = {
    "pendiente": "Pendiente",
    "en_progreso": "En progreso",
    "completada": "Completada",
    "cancelada": "Cancelada",
}
TASK_PRIORITIES = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
}


def validate_subject_form(data: Mapping) -> tuple[dict, dict]:
    """Valida nombre obligatorio y descripción opcional de una materia."""
    values = {field: data.get(field, "").strip()
              for field in ("nombre", "descripcion")}
    errors = {}
    if not 1 <= len(values["nombre"]) <= 120:
        errors["nombre"] = "Introduce un nombre de hasta 120 caracteres."
    if len(values["descripcion"]) > 2000:
        errors["descripcion"] = "La descripción admite hasta 2000 caracteres."
    return values, errors

def validate_payment_notes(data: Mapping) -> tuple[dict, dict]:
    """Valida las notas, también cuando el importe ya no se puede editar."""
    values = {"notas": data.get("notas", "").strip()}
    errors = {}
    if len(values["notas"]) > 2000:
        errors["notas"] = "Las notas admiten hasta 2000 caracteres."
    return values, errors


def validate_payment_form(data: Mapping) -> tuple[dict, dict]:
    """Valida los campos públicos; la fecha de pago se calcula en el servidor."""
    values, errors = validate_payment_notes(data)
    for field in ("tarea_id", "usuario_id", "monto", "moneda", "estado", "metodo"):
        values[field] = data.get(field, "").strip()

    for field in ("tarea_id", "usuario_id"):
        value = values[field]
        if not re.fullmatch(r"[0-9]{1,18}", value) or int(value) < 1:
            errors[field] = "Selecciona un registro válido."

    try:
        values["monto_centavos"] = amount_to_cents(values["monto"])
    except ValueError as error:
        errors["monto"] = str(error)

    if values["moneda"] not in PAYMENT_CURRENCIES:
        errors["moneda"] = "Selecciona USD o pesos dominicanos (DOP)."
    if values["estado"] not in {"pendiente", "pagado"}:
        errors["estado"] = "Selecciona pendiente o pagado. Para anular, usa el detalle."
    if values["metodo"] not in PAYMENT_METHODS:
        errors["metodo"] = "Selecciona un método de pago válido."
    return values, errors


def validate_task_status(data: Mapping) -> tuple[dict, dict]:
    """Valida el único campo que puede cambiar un miembro."""
    values = {"estado": data.get("estado", "")}
    errors = {}

    if values["estado"] not in TASK_STATES:
        errors["estado"] = "Selecciona un estado válido."
    return values, errors


def validate_task_form(data: Mapping) -> tuple[dict, dict]:
    """Valida contenido, vencimiento y IDs opcionales de una tarea."""
    values, errors = validate_task_status(data)
    # Solo se leen los campos permitidos; el navegador no decide la autoría.
    values["titulo"] = data.get("titulo", "").strip()
    values["descripcion"] = data.get("descripcion", "").strip()
    values["fecha_vencimiento"] = data.get("fecha_vencimiento", "").strip()
    values["usuario_asignado_id"] = data.get("usuario_asignado_id", "").strip()
    values["materia_id"] = data.get("materia_id", "").strip()
    values["prioridad"] = data.get("prioridad", "").strip()

    if not 1 <= len(values["titulo"]) <= 200:
        errors["titulo"] = "Introduce un título de hasta 200 caracteres."
    if len(values["descripcion"]) > 5000:
        errors["descripcion"] = "La descripción admite hasta 5000 caracteres."
    if values["prioridad"] not in TASK_PRIORITIES:
        errors["prioridad"] = "Selecciona una prioridad válida."

    deadline = values["fecha_vencimiento"]
    if deadline:
        try:
            parsed_date = date.fromisoformat(deadline)
            # También rechaza formatos abreviados, como 20261201.
            if parsed_date.isoformat() != deadline:
                raise ValueError
        except ValueError:
            errors["fecha_vencimiento"] = (
                "Introduce una fecha válida con formato AAAA-MM-DD."
            )

    for field in ("usuario_asignado_id", "materia_id"):
        value = values[field]
        if not value:
            continue  # La asignación y la materia son opcionales.
        if not re.fullmatch(r"[0-9]{1,18}", value):
            errors[field] = "Selecciona un registro válido."
        elif int(value) < 1:
            errors[field] = "Selecciona un registro válido."

    return values, errors


def validate_user_form(data: Mapping, *, editing: bool = False) -> tuple[dict, dict]:
    """Normaliza campos públicos y devuelve errores sin conservar la contraseña."""
    values = {
        "nombre": data.get("nombre", "").strip(),
        "correo": data.get("correo", "").strip().lower(),
        "telefono": data.get("telefono", "").strip(),
        "rol": data.get("rol", "member"),
        "activo": data.get("activo", "1"),
    }
    errors = {}

    if not 1 <= len(values["nombre"]) <= 100:
        errors["nombre"] = "Introduce un nombre de hasta 100 caracteres."
    email = values["correo"]
    valid_email_format = re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
    if len(email) > 120 or not valid_email_format:
        errors["correo"] = "Introduce un correo válido de hasta 120 caracteres."

    phone = values["telefono"]
    if phone and not re.fullmatch(r"[0-9+() .-]{3,30}", phone):
        errors["telefono"] = "Introduce un teléfono válido de hasta 30 caracteres."

    if values["rol"] not in {"admin", "member"}:
        errors["rol"] = "Selecciona un rol válido."
    if values["activo"] not in {"0", "1"}:
        errors["activo"] = "Selecciona un estado válido."

    password = data.get("contrasena", "")
    must_validate_password = not editing or bool(password)
    if must_validate_password:
        if not 8 <= len(password) <= 128:
            errors["contrasena"] = (
                "La contraseña debe tener entre 8 y 128 caracteres."
            )

    return values, errors
