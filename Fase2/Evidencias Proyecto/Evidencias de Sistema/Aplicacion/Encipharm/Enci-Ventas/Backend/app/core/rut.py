"""RUT chileno: normalizacion y validacion del digito verificador (modulo 11)."""
import re

_SEPARATORS = re.compile(r"[.\s-]")
_SHAPE = re.compile(r"\d{7,8}[\dK]")


def compute_dv(body: str) -> str:
    """Digito verificador del cuerpo numerico del RUT."""
    total, factor = 0, 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = factor + 1 if factor < 7 else 2
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def normalize_rut(value: str) -> str:
    """Devuelve el RUT canonico `12345678-5` (sin puntos, K en mayuscula).

    Acepta `12.345.678-5`, `12345678-5`, `123456785` y variantes con espacios.
    Lanza ValueError con un mensaje claro si el formato o el digito verificador no son validos.
    """
    cleaned = _SEPARATORS.sub("", str(value or "")).upper()
    if not _SHAPE.fullmatch(cleaned):
        raise ValueError("El RUT debe tener 7 u 8 digitos y un digito verificador (ej. 12.345.678-5)")
    body, dv = cleaned[:-1], cleaned[-1]
    if compute_dv(body) != dv:
        raise ValueError("El digito verificador del RUT no coincide")
    return f"{int(body)}-{dv}"


def is_valid_rut(value: str) -> bool:
    try:
        normalize_rut(value)
    except ValueError:
        return False
    return True
