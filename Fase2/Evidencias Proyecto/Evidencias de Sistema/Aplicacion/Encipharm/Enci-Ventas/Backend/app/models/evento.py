from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TipoEvento = Literal["presencial", "virtual", "llamada"]
EstadoEvento = Literal["planificada", "realizada", "cancelada"]
MAX_DURACION = timedelta(hours=12)


def _to_utc(value: datetime) -> datetime:
    """Las horas se guardan en UTC sin zona; una hora sin zona se toma como UTC."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


class EventoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clienteId: str = Field(min_length=1, max_length=36)
    oportunidadId: Optional[str] = Field(default=None, max_length=36)
    tipo: TipoEvento
    inicio: datetime
    fin: datetime
    lugar: Optional[str] = Field(default=None, max_length=200)
    notas: Optional[str] = Field(default=None, max_length=2000)
    # Solo supervisor y admin pueden agendar para otro vendedor.
    vendedorUid: Optional[str] = Field(default=None, max_length=36)

    @field_validator("inicio", "fin")
    @classmethod
    def _utc(cls, value):
        return _to_utc(value)

    @model_validator(mode="after")
    def _range(self):
        if self.fin <= self.inicio:
            raise ValueError("El fin debe ser posterior al inicio")
        if self.fin - self.inicio > MAX_DURACION:
            raise ValueError("Un evento no puede durar mas de 12 horas")
        return self


class EventoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oportunidadId: Optional[str] = Field(default=None, max_length=36)
    tipo: Optional[TipoEvento] = None
    inicio: Optional[datetime] = None
    fin: Optional[datetime] = None
    lugar: Optional[str] = Field(default=None, max_length=200)
    notas: Optional[str] = Field(default=None, max_length=2000)
    estado: Optional[EstadoEvento] = None

    @field_validator("inicio", "fin")
    @classmethod
    def _utc(cls, value):
        return None if value is None else _to_utc(value)


class EventoResponse(BaseModel):
    id: str
    clienteId: str
    clienteNombre: Optional[str] = None
    oportunidadId: Optional[str] = None
    vendedorUid: str
    vendedorNombre: Optional[str] = None
    tipo: TipoEvento
    inicio: datetime
    fin: datetime
    lugar: Optional[str] = None
    notas: Optional[str] = None
    estado: EstadoEvento
    interaccionId: Optional[str] = None
