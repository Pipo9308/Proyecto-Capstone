"""Invitaciones y restablecimiento de contrasena por enlace de un solo uso (RQ-05).

Todavia no hay un servicio de correo: el admin recibe el enlace al invitar y lo comparte
(D4 del plan). Cuando exista, bastara con enviar `build_link(...)` por correo.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from app.core.odm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models_sql.account_token import AccountToken
from app.models_sql.user import User


def _now() -> datetime:
    """UTC sin zona: asi se guardan y comparan las fechas de estas tablas."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_link(raw_token: str) -> str:
    return f"{get_settings().FRONTEND_URL.rstrip('/')}/activar?token={raw_token}"


def _invalid(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": message, "codigo": code, "detalles": None},
    )


def issue_token(db: Session, user: User, kind: str) -> tuple[str, datetime]:
    """Crea un enlace nuevo; los anteriores sin usar de ese usuario dejan de valer."""
    now = _now()
    for previous in db.query(AccountToken).filter(AccountToken.usuarioId == user.id, AccountToken.usedAt.is_(None)).all():
        previous.usedAt = now
    raw = secrets.token_urlsafe(32)
    expires = now + timedelta(hours=get_settings().INVITATION_TTL_HOURS)
    db.add(AccountToken(usuarioId=user.id, tokenHash=_hash(raw), tipo=kind, expiresAt=expires))
    user.passwordResetRequestedAt = None
    db.commit()
    return raw, expires


def _load(db: Session, raw_token: str) -> tuple[AccountToken, User]:
    token = db.query(AccountToken).filter(AccountToken.tokenHash == _hash(raw_token or "")).first()
    if token is None or token.usedAt is not None:
        raise _invalid("ERR_ENLACE_INVALIDO", "El enlace no es valido o ya fue usado. Pide uno nuevo a tu administrador.")
    if token.expiresAt <= _now():
        raise _invalid("ERR_ENLACE_EXPIRADO", "El enlace vencio. Pide uno nuevo a tu administrador.")
    user = db.query(User).filter(User.id == token.usuarioId).first()
    if user is None:
        raise _invalid("ERR_ENLACE_INVALIDO", "El enlace no es valido o ya fue usado. Pide uno nuevo a tu administrador.")
    return token, user


def inspect_token(db: Session, raw_token: str) -> dict:
    """Datos para mostrar en la pantalla de activacion, sin consumir el enlace."""
    token, user = _load(db, raw_token)
    return {"email": user.email, "nombre": user.nombre, "tipo": token.tipo, "expiraEn": token.expiresAt}


def consume_token(db: Session, raw_token: str, new_password: str) -> User:
    token, user = _load(db, raw_token)
    if not user.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo")
    user.password_hash = get_password_hash(new_password)
    user.passwordResetRequestedAt = None
    token.usedAt = _now()
    db.commit()
    db.refresh(user)
    return user


def request_password_reset(db: Session, email: str) -> None:
    """Marca que el usuario pidio restablecer su contrasena para que un admin le envie un enlace.

    Responde igual exista o no la cuenta (no se revela quien tiene cuenta).
    """
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user and user.activo and user.password_hash:
        user.passwordResetRequestedAt = _now()
        db.commit()
