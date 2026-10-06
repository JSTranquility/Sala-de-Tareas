"""Opciones de pago y conversión de importes con Decimal, sin un ORM."""

from decimal import Decimal
import re


MAX_PAYMENT_CENTS = 9223372036854775807  # Límite de INTEGER en SQLite.

PAYMENT_STATES = {
    "pendiente": "Pendiente",
    "pagado": "Pagado",
    "anulado": "Anulado",
}
PAYMENT_CURRENCIES = {
    "USD": "Dólares estadounidenses (USD)",
    "DOP": "Pesos dominicanos (DOP)",
}
PAYMENT_METHODS = {
    "efectivo": "Efectivo",
    "transferencia": "Transferencia",
    "tarjeta": "Tarjeta",
    "otro": "Otro",
}


def amount_to_cents(value: str) -> int:
    """Convierte un importe positivo con hasta dos decimales a centavos."""
    value = value.strip()
    if not re.fullmatch(r"[0-9]{1,17}(\.[0-9]{1,2})?", value):
        raise ValueError("Introduce un monto positivo con hasta dos decimales, usando punto.")

    cents = int(Decimal(value) * 100)
    if not 1 <= cents <= MAX_PAYMENT_CENTS:
        raise ValueError(
            "El monto debe ser mayor que cero y estar dentro del límite permitido."
        )
    return cents


def format_amount(cents: int) -> str:
    """Muestra dos decimales sin convertir el importe a float."""
    sign = "-" if cents < 0 else ""
    units, remainder = divmod(abs(cents), 100)
    return f"{sign}{units}.{remainder:02d}"
