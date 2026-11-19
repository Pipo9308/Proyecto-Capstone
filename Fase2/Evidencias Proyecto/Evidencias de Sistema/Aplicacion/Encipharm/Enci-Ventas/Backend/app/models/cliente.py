from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.rut import normalize_rut


ClienteEstado = Literal["En proceso", "Completado", "Inactivo"]
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _reject_formula_injection(value: str | None) -> str | None:
    if value and value.strip().startswith(FORMULA_PREFIXES):
        raise ValueError("El valor no puede iniciar con caracteres de formula")
    return value


def _normalize_chilean_mobile(value: str | None) -> str | None:
    if value is None:
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("569") and len(digits) >= 11:
        digits = digits[3:11]
    elif digits.startswith("9") and len(digits) >= 9:
        digits = digits[1:9]
    if len(digits) != 8:
        raise ValueError("El telefono debe tener 8 digitos despues de +569")
    return digits


class ClienteBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    empresa: str = Field(min_length=1, max_length=160)
    # RUT canonico (12345678-5). Opcional aqui porque hay clientes anteriores sin RUT;
    # las altas por API y CSV lo exigen (ClienteCreateRequest).
    rut: Optional[str] = Field(default=None, max_length=16)
    email: Optional[EmailStr] = None
    telefono: Optional[str] = Field(default=None, max_length=32)
    rubro: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=80)
    estado: ClienteEstado = "En proceso"
    vendedorUid: Optional[str] = Field(default=None, max_length=128)
    ownerUid: Optional[str] = Field(default=None, max_length=128)

    @field_validator("nombre", "empresa", "rubro", "region", "vendedorUid", "ownerUid")
    @classmethod
    def reject_formula_values(cls, value: str | None) -> str | None:
        return _reject_formula_injection(value)

    @field_validator("telefono")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _normalize_chilean_mobile(value)

    @field_validator("rut")
    @classmethod
    def validate_rut(cls, value: str | None) -> str | None:
        return normalize_rut(value) if value else None


class ClienteCreate(ClienteBase):
    model_config = ConfigDict(extra="forbid")


class ClienteCreateRequest(ClienteCreate):
    """Alta desde la API o el CSV: nombre del contacto, empresa, RUT e industria son obligatorios
    (email, telefono y region son opcionales). La web usa exactamente la misma regla."""

    rut: str = Field(max_length=16)
    rubro: str = Field(min_length=1, max_length=120)


class ClienteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Optional[str] = Field(default=None, min_length=1, max_length=120)
    empresa: Optional[str] = Field(default=None, min_length=1, max_length=160)
    rut: Optional[str] = Field(default=None, max_length=16)
    email: Optional[EmailStr] = None
    telefono: Optional[str] = Field(default=None, max_length=32)
    rubro: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=80)
    estado: Optional[ClienteEstado] = None
    vendedorUid: Optional[str] = Field(default=None, max_length=128)
    ownerUid: Optional[str] = Field(default=None, max_length=128)

    @field_validator("nombre", "empresa", "rubro", "region", "vendedorUid", "ownerUid")
    @classmethod
    def reject_formula_values(cls, value: str | None) -> str | None:
        return _reject_formula_injection(value)

    @field_validator("telefono")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _normalize_chilean_mobile(value)

    @field_validator("rut")
    @classmethod
    def validate_rut(cls, value: str | None) -> str | None:
        return normalize_rut(value) if value else None


class ClienteResponse(ClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


class CsvImportError(BaseModel):
    fila: int
    errores: list[str]


class CsvImportResult(BaseModel):
    totalFilas: int
    importados: int
    fallidos: int
    errores: list[CsvImportError]
