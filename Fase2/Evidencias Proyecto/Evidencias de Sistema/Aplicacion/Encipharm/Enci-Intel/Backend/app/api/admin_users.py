import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import get_db
from app.api.auth import ROLES_CANONICOS, get_password_hash, normalize_role, require_admin

router = APIRouter()


class UpdateRoleRequest(BaseModel):
    email: str
    role: str

class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/", status_code=201)
async def create_user(request: CreateUserRequest, current_user=Depends(require_admin)):
    """El admin crea un usuario ya con su rol (el self-registro siempre nace "pendiente")."""
    email = request.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Correo no válido")
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres")
    if str(request.role).strip().lower() not in (*ROLES_CANONICOS, "administrador"):
        raise HTTPException(status_code=400, detail="Rol no válido")

    db = get_db()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese correo")
    role = normalize_role(request.role)
    result = await db.users.insert_one({
        "email": email,
        "hashed_password": get_password_hash(request.password),
        "rol": role,
        "estado": "activo",
    })
    return {"success": True, "data": {"id": str(result.inserted_id), "email": email, "rol": role, "estado": "activo",
                                       "created_by": current_user.get("email", "")}}


@router.get("/")
async def list_users(current_user=Depends(require_admin)):
    db = get_db()
    users = await db.users.find().to_list(length=None)
    data = []
    for u in users:
        data.append({
            "id": str(u["_id"]),
            "email": u.get("email", ""),
            "rol": normalize_role(u.get("rol")),
            "estado": u.get("estado", "activo")
        })
    return {"success": True, "data": data}


@router.patch("/role")
async def update_user_role(
    request: UpdateRoleRequest,
    current_user=Depends(require_admin)
):
    # Se aceptan los valores historicos ("Admin", "administrador"...) y se guarda el canonico.
    new_role = normalize_role(request.role)
    if str(request.role).strip().lower() not in (*ROLES_CANONICOS, "administrador"):
        raise HTTPException(status_code=400, detail="Rol no válido")

    try:
        db = get_db()
        user = await db.users.find_one({"email": request.email})
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        await db.users.update_one(
            {"email": request.email},
            {"$set": {"rol": new_role}}
        )

        return {
            "success": True,
            "message": "Rol actualizado correctamente",
            "data": {
                "email": request.email,
                "uid": str(user["_id"]),
                "role": new_role,
                "updated_by": current_user.get("email", ""),
            }
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo actualizar el rol: {str(error)}"
        )