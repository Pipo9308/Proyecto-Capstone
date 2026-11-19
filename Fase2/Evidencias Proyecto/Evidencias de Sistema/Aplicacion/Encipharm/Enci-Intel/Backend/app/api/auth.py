import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
import jwt
import bcrypt
from app.db import get_db

router = APIRouter()

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
if len(SECRET_KEY) < 32 or SECRET_KEY.startswith("change_this"):
    raise RuntimeError(
        "JWT_SECRET_KEY no definido o inseguro: exige un valor aleatorio de al "
        "menos 32 caracteres (ver .env.example)."
    )
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

class UserLogin(BaseModel):
    email: str
    password: str

class UserCreate(BaseModel):
    email: str
    password: str

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire.timestamp()})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def require_auth(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no enviado")
    
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    rechazar_pendiente(payload)
    return payload

ROLES_CANONICOS = ("admin", "gerencia", "comercial", "pendiente")


def normalize_role(role) -> str:
    """Devuelve el rol canonico (minuscula). Acepta los valores historicos
    ("administrador", "Admin", "Comercial"...) y cae a "pendiente" si no se reconoce."""
    value = str(role or "").strip().lower()
    if value == "administrador":
        value = "admin"
    return value if value in ROLES_CANONICOS else "pendiente"


PENDIENTE_DETALLE = "Tu cuenta está pendiente de aprobación por un administrador."


def rechazar_pendiente(payload: dict) -> None:
    """Un usuario sin aprobar (registro público) no usa la API, aunque tenga un token emitido antes de este control."""
    if normalize_role(payload.get("rol")) == "pendiente":
        raise HTTPException(status_code=403, detail=PENDIENTE_DETALLE)


def require_admin(user: dict = Depends(require_auth)):
    if normalize_role(user.get("rol")) != "admin":
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador")
    return user


INTEL_SERVICE_API_KEY = os.environ.get("INTEL_SERVICE_API_KEY", "")


def require_user_or_service(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Permite acceso a un usuario logueado (JWT) o a un servicio de confianza
    (Enci-Ventas consumiendo esta API vía proxy) con una API key compartida."""
    if x_api_key is not None:
        if not INTEL_SERVICE_API_KEY or x_api_key != INTEL_SERVICE_API_KEY:
            raise HTTPException(status_code=401, detail="API key de servicio invalida")
        return {"service": True, "rol": "service"}
    return require_auth(authorization=authorization)

@router.post("/login")
async def login(user_data: UserLogin):
    db = get_db()
    user = await db.users.find_one({"email": user_data.email})
    
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    role = normalize_role(user.get("rol"))
    if role == "pendiente":
        raise HTTPException(status_code=403, detail=PENDIENTE_DETALLE)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user["_id"]), "email": user["email"], "rol": role},
        expires_delta=access_token_expires
    )
    return {
        "success": True,
        "data": {
            "token": access_token,
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "role": role
            }
        }
    }

@router.post("/register")
async def register(user_data: UserCreate):
    db = get_db()
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    new_user = {
        "email": user_data.email,
        "hashed_password": hashed_password,
        # El rol nunca viene del cliente: todo self-registro nace "pendiente"
        # y un admin lo promueve via PATCH /admin/users/role.
        "rol": "pendiente",
        "estado": "activo"
    }
    result = await db.users.insert_one(new_user)
    
    return {"success": True, "data": {"id": str(result.inserted_id)}}

@router.get("/me")
async def get_me(user: dict = Depends(require_auth)):
    return {
        "success": True,
        "data": {
            "id": user.get("sub"),
            "email": user.get("email"),
            "role": normalize_role(user.get("rol"))
        }
    }
