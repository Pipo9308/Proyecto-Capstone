from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Unidad = Literal["ml", "g", "dosis"]
EstadoPrecio = Literal["pendiente", "aprobado", "descartado"]


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def _clean_list(values: list[str]) -> list[str]:
    cleaned = [c for c in (_clean(v) for v in values) if c]
    if any(";" in c for c in cleaned):
        raise ValueError("Un principio activo no puede contener ';'")
    return cleaned


class _ProductoBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nombre: str = Field(min_length=1, max_length=200)
    principiosActivos: list[str] = Field(default_factory=list, max_length=10)
    concentracion: Optional[str] = Field(default=None, max_length=100)
    presentacion: Optional[str] = Field(default=None, max_length=120)
    unidadMedida: Unidad
    cantidadPresentacion: float = Field(gt=0, le=1_000_000)
    categoria: Optional[str] = Field(default=None, max_length=100)
    especie: Optional[str] = Field(default=None, max_length=100)

    @field_validator("nombre", "concentracion", "presentacion", "categoria", "especie", mode="before")
    @classmethod
    def _strip(cls, value):
        return _clean(value) if isinstance(value, str) else value

    @field_validator("nombre")
    @classmethod
    def _nombre_required(cls, value):
        if not value:
            raise ValueError("El nombre es obligatorio")
        return value

    @field_validator("principiosActivos")
    @classmethod
    def _principios(cls, value):
        return _clean_list(value)


class ProductoEncipharmCreate(_ProductoBase):
    sku: Optional[str] = Field(default=None, max_length=60)
    precioLista: Optional[float] = Field(default=None, ge=0)
    moneda: str = Field(default="CLP", pattern="^[A-Za-z]{3}$")
    activo: bool = True

    @field_validator("moneda")
    @classmethod
    def _upper(cls, value):
        return value.upper()

    @field_validator("sku", mode="before")
    @classmethod
    def _sku(cls, value):
        return _clean(value) if isinstance(value, str) else value


class ProductoEncipharmUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sku: Optional[str] = Field(default=None, max_length=60)
    principiosActivos: Optional[list[str]] = Field(default=None, max_length=10)
    concentracion: Optional[str] = Field(default=None, max_length=100)
    presentacion: Optional[str] = Field(default=None, max_length=120)
    unidadMedida: Optional[Unidad] = None
    cantidadPresentacion: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    precioLista: Optional[float] = Field(default=None, ge=0)
    moneda: Optional[str] = Field(default=None, pattern="^[A-Za-z]{3}$")
    categoria: Optional[str] = Field(default=None, max_length=100)
    especie: Optional[str] = Field(default=None, max_length=100)
    activo: Optional[bool] = None

    @field_validator("principiosActivos")
    @classmethod
    def _principios(cls, value):
        return None if value is None else _clean_list(value)


class ProductoEncipharmResponse(BaseModel):
    id: str
    nombre: str
    sku: Optional[str] = None
    principiosActivos: list[str]
    concentracion: Optional[str] = None
    presentacion: Optional[str] = None
    unidadMedida: Unidad
    cantidadPresentacion: float
    precioLista: Optional[float] = None
    precioPorUnidad: Optional[float] = None
    moneda: str
    categoria: Optional[str] = None
    especie: Optional[str] = None
    activo: bool


class ProductoCompetenciaCreate(_ProductoBase):
    competidor: str = Field(min_length=1, max_length=160)
    registroSag: Optional[str] = Field(default=None, max_length=60)

    @field_validator("competidor", "registroSag", mode="before")
    @classmethod
    def _strip2(cls, value):
        return _clean(value) if isinstance(value, str) else value

    @field_validator("competidor")
    @classmethod
    def _competidor_required(cls, value):
        if not value:
            raise ValueError("El competidor es obligatorio")
        return value


class ProductoCompetenciaUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    competidor: Optional[str] = Field(default=None, min_length=1, max_length=160)
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    principiosActivos: Optional[list[str]] = Field(default=None, max_length=10)
    concentracion: Optional[str] = Field(default=None, max_length=100)
    presentacion: Optional[str] = Field(default=None, max_length=120)
    unidadMedida: Optional[Unidad] = None
    cantidadPresentacion: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    categoria: Optional[str] = Field(default=None, max_length=100)
    especie: Optional[str] = Field(default=None, max_length=100)
    registroSag: Optional[str] = Field(default=None, max_length=60)

    @field_validator("principiosActivos")
    @classmethod
    def _principios(cls, value):
        return None if value is None else _clean_list(value)


class EquivalenciasRequest(BaseModel):
    encipharmIds: list[str] = Field(default_factory=list, max_length=50)


class PrecioCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    precio: float = Field(gt=0, le=1_000_000_000)
    moneda: str = Field(default="CLP", pattern="^[A-Za-z]{3}$")
    fuente: Optional[str] = Field(default=None, max_length=240)
    fechaPrecio: Optional[date] = None
    zona: Optional[str] = Field(default=None, max_length=120)
    clienteId: Optional[str] = Field(default=None, max_length=36)
    nota: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("moneda")
    @classmethod
    def _upper(cls, value):
        return value.upper()

    @field_validator("fuente", "zona", "nota", mode="before")
    @classmethod
    def _strip(cls, value):
        return _clean(value) if isinstance(value, str) else value

    @field_validator("fechaPrecio")
    @classmethod
    def _not_future(cls, value):
        if value is not None and value > date.today():
            raise ValueError("La fecha del precio no puede ser futura")
        return value


class PrecioResponse(BaseModel):
    id: str
    productoId: str
    precio: float
    moneda: str
    precioPorUnidad: float
    unidadMedida: Unidad
    fuente: Optional[str] = None
    fechaPrecio: date
    zona: Optional[str] = None
    clienteId: Optional[str] = None
    nota: Optional[str] = None
    estado: EstadoPrecio
    reportadoPor: str
    reportadoPorNombre: Optional[str] = None
    revisadoPor: Optional[str] = None
    revisadoAt: Optional[datetime] = None
    createdAt: datetime
    # Solo en la cola de revision: a que producto pertenece el reporte.
    productoNombre: Optional[str] = None
    competidor: Optional[str] = None


class EquivalenteResponse(BaseModel):
    id: str
    nombre: str


class ProductoCompetenciaResponse(BaseModel):
    id: str
    competidor: str
    nombre: str
    principiosActivos: list[str]
    concentracion: Optional[str] = None
    presentacion: Optional[str] = None
    unidadMedida: Unidad
    cantidadPresentacion: float
    categoria: Optional[str] = None
    especie: Optional[str] = None
    registroSag: Optional[str] = None
    equivalentes: list[EquivalenteResponse]
    ultimoPrecio: Optional[PrecioResponse] = None
    createdAt: datetime
    updatedAt: datetime


class ProductoCompetenciaDetalle(ProductoCompetenciaResponse):
    historial: list[PrecioResponse]


class Pagina(BaseModel):
    total: int
    page: int
    pageSize: int


class ProductosCompetenciaPagina(Pagina):
    items: list[ProductoCompetenciaResponse]


class PreciosPagina(Pagina):
    items: list[PrecioResponse]


class ComparativaFila(BaseModel):
    productoCompetenciaId: str
    competidor: str
    nombre: str
    presentacion: Optional[str] = None
    principiosActivos: list[str] = Field(default_factory=list)
    concentracion: Optional[str] = None
    registroSag: Optional[str] = None
    precioPorUnidad: Optional[float] = None
    moneda: Optional[str] = None
    fechaPrecio: Optional[date] = None
    fuente: Optional[str] = None
    # (Encipharm - competidor) / competidor * 100: positivo = Encipharm mas caro.
    diferenciaPct: Optional[float] = None
    motivoSinDiferencia: Optional[str] = None


class Comparativa(BaseModel):
    productoEncipharm: ProductoEncipharmResponse
    equivalentes: list[ComparativaFila]


class ResumenFila(BaseModel):
    clave: str
    unidadMedida: Unidad
    moneda: str
    productos: int
    precioPromedioPorUnidad: float
    diferenciaPromedioPct: Optional[float] = None


class Resumen(BaseModel):
    porCategoria: list[ResumenFila]
    porCompetidor: list[ResumenFila]
    productosSinPrecio: int
