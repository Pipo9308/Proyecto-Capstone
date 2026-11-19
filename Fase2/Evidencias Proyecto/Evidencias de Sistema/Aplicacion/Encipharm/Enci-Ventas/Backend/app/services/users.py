from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from app.core.odm import Session
from app.models_sql.user import User
from app.core.security import get_password_hash

from app.models.user import (
    normalize_display_name,
    normalize_user_language,
    normalize_user_rank,
    normalize_user_role,
    normalize_user_theme,
    normalize_user_zone,
)


MAX_USERS_RESPONSE = 500

def user_state(user: User) -> str:
    """desactivado > invitado (aun sin contrasena) > activo."""
    if not user.activo:
        return "desactivado"
    return "invitado" if not user.password_hash else "activo"


def _user_model_to_dict(user: User) -> dict[str, Any]:
    return {
        "uid": user.id,
        "email": user.email,
        "nombre": user.nombre,
        "rol": user.rol,
        "cargo": user.cargo,
        "rango": user.rango,
        "zona": user.zona,
        "appMovil": user.appMovil,
        "webApp": user.webApp,
        "accesoInteligencia": bool(user.accesoInteligencia),
        "theme": user.theme,
        "language": user.language,
        "activo": user.activo,
        "estado": user_state(user),
        "restablecimientoSolicitado": user.passwordResetRequestedAt is not None,
        "createdAt": user.createdAt,
        "updatedAt": user.updatedAt,
    }


def normalize_user(uid: str, data: dict[str, Any]) -> dict[str, Any]:
    role = normalize_user_role(data.get("rol"))
    rank = normalize_user_rank(data.get("rango") or data.get("cargo"), role)
    default_access = role != "sin_acceso"
    return {
        "uid": data.get("uid", uid),
        "email": data.get("email"),
        "nombre": normalize_display_name(data.get("nombre"), data.get("email")),
        "rol": role,
        "cargo": data.get("cargo") or rank,
        "rango": rank,
        "zona": normalize_user_zone(data.get("zona")),
        "appMovil": data.get("appMovil", default_access),
        "webApp": data.get("webApp", default_access),
        "accesoInteligencia": bool(data.get("accesoInteligencia", False)) and default_access,
        "theme": normalize_user_theme(data.get("theme")),
        "language": normalize_user_language(data.get("language")),
        "activo": data.get("activo", True),
        "createdAt": data.get("createdAt"),
        "updatedAt": data.get("updatedAt"),
    }


def list_users(
    db: Session,
    activo: bool | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    if limit is not None:
        limit = min(max(limit, 1), MAX_USERS_RESPONSE)

    query = db.query(User)
    if activo is not None:
        query = query.filter(User.activo == activo)
        
    users = query.limit(limit).all()
    
    return [_user_model_to_dict(u) for u in users]


def get_user_or_404(db: Session, uid: str) -> dict[str, Any]:
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return _user_model_to_dict(user)


def update_user(db: Session, uid: str, changes: dict[str, Any]) -> dict[str, Any]:
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    clean_changes = {
        key: value
        for key, value in changes.items()
        if value is not None and key != "lookupEmail"
    }
    
    if "nombre" in clean_changes:
        user.nombre = normalize_display_name(clean_changes["nombre"])
    if "rol" in clean_changes:
        user.rol = normalize_user_role(clean_changes["rol"])

    final_role = user.rol
    if final_role == "sin_acceso":
        user.appMovil = False
        user.webApp = False
        user.accesoInteligencia = False
        user.rango = "Sin acceso"
        user.cargo = "Sin acceso"
    else:
        if "accesoInteligencia" in clean_changes:
            user.accesoInteligencia = bool(clean_changes["accesoInteligencia"])
        if "rol" in clean_changes or "rango" in clean_changes:
            user.rango = normalize_user_rank(clean_changes.get("rango", user.rango), final_role)
            user.cargo = clean_changes.get("cargo", user.rango)
        if "rol" in clean_changes:
            # Al salir de sin_acceso se restaura el acceso por defecto (quedaba
            # forzado en False para siempre); se puede sobreescribir en la
            # misma request con appMovil/webApp explicitos.
            user.appMovil = clean_changes.get("appMovil", True)
            user.webApp = clean_changes.get("webApp", True)
        else:
            if "appMovil" in clean_changes:
                user.appMovil = bool(clean_changes["appMovil"])
            if "webApp" in clean_changes:
                user.webApp = bool(clean_changes["webApp"])

    for key, value in clean_changes.items():
        if hasattr(user, key) and key not in ["nombre", "rol", "rango", "cargo", "appMovil", "webApp", "accesoInteligencia"]:
            setattr(user, key, value)

    user.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    
    return _user_model_to_dict(user)


def set_user_password(db: Session, uid: str, password: str) -> dict[str, Any]:
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    user.password_hash = get_password_hash(password)
    user.updatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _user_model_to_dict(user)


def create_user(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    existing = db.query(User).filter(User.email == data["email"]).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya esta en uso",
        )

    new_user = User(
        email=data["email"],
        nombre=normalize_display_name(data.get("nombre")),
        rol=normalize_user_role(data.get("rol")),
        # Sin contrasena la cuenta queda invitada: el usuario la crea con un enlace.
        password_hash=get_password_hash(data["password"]) if data.get("password") else None,
    )
    
    final_role = new_user.rol
    if final_role == "sin_acceso":
        new_user.appMovil = False
        new_user.webApp = False
        new_user.accesoInteligencia = False
        new_user.rango = "Sin acceso"
        new_user.cargo = "Sin acceso"
    else:
        new_user.accesoInteligencia = bool(data.get("accesoInteligencia", False))
        new_user.rango = normalize_user_rank(data.get("rango", data.get("cargo")), final_role)
        new_user.cargo = data.get("cargo", new_user.rango)
        new_user.appMovil = data.get("appMovil", True)
        new_user.webApp = data.get("webApp", True)
        
    for key in ["zona", "theme", "language", "activo"]:
        if key in data:
            setattr(new_user, key, data[key])
            
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return _user_model_to_dict(new_user)
