from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, require_role
from app.models.user import (
    AdminUserCreate,
    UserPasswordUpdate,
    UserCreateResponse,
    UserPreferencesUpdate,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUpdate,
)
from app.core.db import get_db
from app.core.odm import Session
from app.models.auth import InvitationInfo
from app.models_sql.user import User
from app.services.account_tokens import build_link, issue_token
from app.services.users import get_user_or_404, list_users, update_user, create_user, set_user_password


router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get("/", response_model=list[UserResponse])
async def get_users(
    activo: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db)
):
    return list_users(db, activo=activo, limit=limit)


def _invitation_for(db: Session, user: User) -> InvitationInfo:
    kind = "invitacion" if not user.password_hash else "reset"
    raw, expires = issue_token(db, user, kind)
    return InvitationInfo(enlace=build_link(raw), expiraEn=expires, tipo=kind)


@router.post("/", response_model=UserCreateResponse)
async def post_user(
    payload: AdminUserCreate,
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    created = create_user(db, payload.model_dump(exclude_unset=True))
    if payload.password:
        return created
    # Sin contrasena inicial: se genera el enlace de invitacion que el admin comparte.
    user = db.query(User).filter(User.id == created["uid"]).first()
    return {**created, "invitacion": _invitation_for(db, user)}


@router.post("/{uid}/invitacion", response_model=InvitationInfo)
async def post_invitation(
    uid: str,
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Genera un enlace nuevo: invitacion si el usuario aun no tiene contrasena, o restablecimiento.
    Los enlaces anteriores sin usar dejan de valer."""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if not user.activo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario esta desactivado")
    return _invitation_for(db, user)


@router.get("/me", response_model=UserResponse)
async def get_own_profile(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_or_404(db, user["uid"])


@router.get("/{uid}", response_model=UserResponse)
async def get_user(
    uid: str,
    _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db)
):
    return get_user_or_404(db, uid)


@router.patch("/me/preferences", response_model=UserResponse)
async def patch_own_preferences(
    payload: UserPreferencesUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return update_user(db, user["uid"], payload.model_dump(exclude_unset=True))


@router.patch("/{uid}", response_model=UserResponse)
async def patch_user(
    uid: str,
    payload: UserUpdate,
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    return update_user(db, uid, payload.model_dump(exclude_unset=True))


@router.patch("/{uid}/password", response_model=UserResponse)
async def patch_user_password(
    uid: str,
    payload: UserPasswordUpdate,
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    return set_user_password(db, uid, payload.password)


@router.patch("/{uid}/role", response_model=UserResponse)
async def patch_user_role(
    uid: str,
    payload: UserRoleUpdate,
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    return update_user(db, uid, {"rol": payload.rol})


@router.patch("/{uid}/status", response_model=UserResponse)
async def patch_user_status(
    uid: str,
    payload: UserStatusUpdate,
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    return update_user(db, uid, {"activo": payload.activo})
