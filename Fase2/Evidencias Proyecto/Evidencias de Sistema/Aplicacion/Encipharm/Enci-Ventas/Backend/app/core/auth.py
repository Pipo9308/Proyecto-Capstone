from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from app.core.config import get_settings
from app.models.user import normalize_user_role
from app.core.security import ALGORITHM
from app.core.db import get_db
from app.models_sql.user import User
from app.core.odm import Session

security = HTTPBearer(auto_error=False)


def normalize_client_platform(value: str | None) -> str:
    normalized = str(value or "web").strip().lower()
    if normalized in {"mobile", "movil", "app", "app_movil", "app-movil"}:
        return "mobile"
    return "web"


def ensure_platform_access(user_data: dict, platform: str | None) -> None:
    normalized_platform = normalize_client_platform(platform)
    access_field = "appMovil" if normalized_platform == "mobile" else "webApp"
    access_label = "app movil" if normalized_platform == "mobile" else "web app"

    user_role = normalize_user_role(user_data.get("rol"))
    if user_role == "sin_acceso":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario sin rol habilitado en el sistema",
        )

    if not user_data.get(access_field, user_role != "sin_acceso"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Usuario sin acceso a {access_label}",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    x_enci_client: str | None = Header(default="web"),
    db: Session = Depends(get_db)
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        user_email: str = payload.get("sub")
        if user_email is None:
            raise ValueError("Token sin email")
    except Exception as error:
        detail = "Token invalido o expirado"
        if settings.APP_ENV == "development":
            detail = str(error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user = db.query(User).filter(User.email == user_email).first()
    
    decoded = {"email": user_email, "uid": payload.get("uid", "")}
    
    if user:
        if not user.activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo en el sistema",
            )
        # Ensure platform access
        ensure_platform_access(user.__dict__, x_enci_client)
        decoded["rol"] = normalize_user_role(user.rol)
        # El admin siempre accede a Inteligencia; el resto depende del permiso por usuario.
        decoded["accesoInteligencia"] = decoded["rol"] == "admin" or bool(user.accesoInteligencia)
        decoded["nombre"] = user.nombre
        decoded["uid"] = user.id
        decoded["activo"] = user.activo
    else:
        decoded["rol"] = "sin_acceso"
        
    return decoded


async def require_intel_access(user: dict = Depends(get_current_user)) -> dict:
    """Exige el permiso "Acceso a Inteligencia" (el admin siempre lo tiene)."""
    if not user.get("accesoInteligencia"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin acceso a Inteligencia de Mercado",
        )
    return user


def require_role(required_role: str):
    async def role_checker(
        user: dict = Depends(get_current_user),
        x_enci_client: str | None = Header(default="web"),
        db: Session = Depends(get_db)
    ) -> dict:
        user_obj = db.query(User).filter(User.id == user.get("uid")).first()
        
        if not user_obj:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario no registrado en el sistema",
            )
            
        if not user_obj.activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inactivo en el sistema",
            )
            
        ensure_platform_access(user_obj.__dict__, x_enci_client)
        roles_permitidos = {
            "admin": ["admin"],
            "supervisor": ["admin", "supervisor"],
            "vendedor": ["admin", "supervisor", "vendedor"],
        }
        user_role = normalize_user_role(user_obj.rol)
        if user_role not in roles_permitidos.get(required_role, []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta accion",
            )
        return {**user, **user_obj.__dict__, "rol": user_role}

    return role_checker
