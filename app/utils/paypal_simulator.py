"""Resultados ficticios de un pago, sin conexiones externas."""

from app.models import MAX_PAYMENT_CENTS, PAYMENT_CURRENCIES


def simulate_payment(payment_id: int, amount_cents: int, currency: str,
                     outcome: str) -> dict[str, str]:
    
    """Valida los datos y devuelve el resultado elegido para el ejercicio."""

    if type(payment_id) is not int or payment_id < 1:
        raise ValueError("El identificador del pago no es válido.")
    
    if type(amount_cents) is not int or not 1 <= amount_cents <= MAX_PAYMENT_CENTS:
        raise ValueError("El importe debe ser positivo y estar en centavos.")
    
    if currency not in PAYMENT_CURRENCIES:
        raise ValueError("Selecciona USD o DOP para la simulación.")
    
    messages = {
        "aprobado": "Pago simulado aprobado. No se realizó ningún cobro.",
        "rechazado": "Pago simulado rechazado. El registro sigue pendiente.",
        "cancelado": "Simulación cancelada. El registro sigue pendiente.",
    }
    
    if outcome not in messages:
        raise ValueError("Selecciona aprobar, rechazar o cancelar.")
    return {"resultado": outcome, "mensaje": messages[outcome],
            "referencia": f"SIM-PAGO-{payment_id}"}
