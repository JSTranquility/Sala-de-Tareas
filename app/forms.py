import re
from collections.abc import Mapping


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
    if (len(values["correo"]) > 120 or
            not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["correo"])):
        errors["correo"] = "Introduce un correo válido de hasta 120 caracteres."
    if values["telefono"] and not re.fullmatch(r"[0-9+() .-]{3,30}", values["telefono"]):
        errors["telefono"] = "Introduce un teléfono válido de hasta 30 caracteres."
    if values["rol"] not in {"admin", "member"}:
        errors["rol"] = "Selecciona un rol válido."
    if values["activo"] not in {"0", "1"}:
        errors["activo"] = "Selecciona un estado válido."
    password = data.get("contrasena", "")
    if (not editing or password) and not 8 <= len(password) <= 128:
        errors["contrasena"] = "La contraseña debe tener entre 8 y 128 caracteres."
    return values, errors
