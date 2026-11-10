from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
THREE_DP = Decimal("0.001")

def parse_decimal(value, field_name: str, *, allow_zero: bool = True, places: Decimal = THREE_DP) -> Decimal:
    try:
        raw = str(value).strip().replace(",", ".")
        if not raw:
            raise ValueError(f"El campo {field_name} es obligatorio.")
        number = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"El campo {field_name} debe ser numérico.")
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"El campo {field_name} debe ser { 'mayor que cero' if not allow_zero else 'cero o positivo' }.")
    return number.quantize(places, rounding=ROUND_HALF_UP)

def parse_date(value: str, field_name: str = "fecha") -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except Exception:
        raise ValueError(f"El campo {field_name} debe tener una fecha válida.")

def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except InvalidOperation:
        return Decimal("0")
