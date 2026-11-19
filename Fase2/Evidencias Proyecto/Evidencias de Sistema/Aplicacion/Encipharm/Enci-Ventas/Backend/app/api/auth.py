from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from app.core.odm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.auth import (
    ForgotPasswordRequest,
    InvitationPreview,
    LoginRequest,
    SetPasswordRequest,
    Token,
)
from app.models_sql.user import User
from app.core.security import verify_password, get_password_hash, create_access_token
from app.services import audit
from app.services.account_tokens import consume_token, inspect_token, request_password_reset
from app.services.users import user_state

router = APIRouter(prefix="/auth", tags=["Autenticacion"])


def _user_payload(user: User) -> dict:
    """Datos del usuario que recibe el cliente al iniciar sesion."""
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
        "createdAt": user.createdAt,
        "updatedAt": user.updatedAt,
    }


def _issue_session(user: User) -> Token:
    access_token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return Token(access_token=access_token, token_type="bearer", user=_user_payload(user))


@router.post("/login", response_model=Token)
def login_user(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    audit.annotate(request, user=user, email=login_data.email)
    # verify_password devuelve False (no lanza) con contrasenas demasiado largas para bcrypt.
    if not user or not user.password_hash or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    return _issue_session(user)


@router.get("/invitacion", response_model=InvitationPreview)
def get_invitation(token: str = Query(min_length=10, max_length=200), db: Session = Depends(get_db)):
    """Datos de un enlace de invitacion o restablecimiento, sin consumirlo."""
    return inspect_token(db, token)


@router.post("/set-password", response_model=Token)
def set_password(body: SetPasswordRequest, db: Session = Depends(get_db)):
    """Crea (invitacion) o restablece la contrasena con un enlace de un solo uso y abre la sesion."""
    return _issue_session(consume_token(db, body.token, body.password))


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Avisa al admin que el usuario quiere restablecer su contrasena.

    Todavia no hay envio de correos: el admin ve la solicitud en Configuracion y le comparte
    un enlace. La respuesta es la misma exista o no la cuenta.
    """
    audit.annotate(request, email=body.email)
    request_password_reset(db, body.email)
    return {
        "mensaje": "Si la cuenta existe, tu administrador recibio la solicitud y te enviara "
                   "un enlace para crear una contraseña nueva."
    }


@router.post("/register", response_model=Token)
def register_user(login_data: LoginRequest, db: Session = Depends(get_db)):
    # Las cuentas se crean por invitacion (RF-05.07): el registro publico esta cerrado.
    if not get_settings().ALLOW_SELF_REGISTER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro esta deshabilitado. Pide a un administrador que te invite.",
        )
    user = db.query(User).filter(User.email == login_data.email).first()
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado"
        )

    new_user = User(
        email=login_data.email,
        password_hash=get_password_hash(login_data.password),
        nombre=login_data.email.split("@")[0], # default name
        rol="sin_acceso",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return _issue_session(new_user)
