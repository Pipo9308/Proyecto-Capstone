from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.password_policy import validate_password_strength


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class SetPasswordRequest(BaseModel):
    """Crear o restablecer la contrasena con un enlace de invitacion."""

    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_password_strength(value)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class InvitationInfo(BaseModel):
    """Enlace que el admin comparte con el usuario (todavia no se envia por correo)."""

    enlace: str
    expiraEn: datetime
    tipo: str


class InvitationPreview(BaseModel):
    email: str
    nombre: str
    tipo: str
    expiraEn: datetime
