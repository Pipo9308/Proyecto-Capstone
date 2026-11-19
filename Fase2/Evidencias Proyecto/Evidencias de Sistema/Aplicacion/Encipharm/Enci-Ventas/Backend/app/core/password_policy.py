"""Politica de contrasenas (RF-05.05): al menos 10 caracteres, con letras y numeros."""

MIN_LENGTH = 10
# bcrypt solo usa los primeros 72 bytes y desde la version 5 rechaza contrasenas mas largas.
MAX_BYTES = 72


def validate_password_strength(password: str) -> str:
    """Devuelve la contrasena si cumple la politica; si no, ValueError con un mensaje claro."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"La contrasena debe tener al menos {MIN_LENGTH} caracteres")
    if len(password.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"La contrasena es demasiado larga (maximo {MAX_BYTES} bytes)")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("La contrasena debe incluir letras y numeros")
    return password
