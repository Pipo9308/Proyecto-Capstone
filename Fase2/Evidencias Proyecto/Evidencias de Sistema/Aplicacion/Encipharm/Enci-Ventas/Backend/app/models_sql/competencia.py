from datetime import date, datetime, timezone
import uuid

from app.core.odm import Boolean, Column, Date, DateTime, ForeignKey, Numeric, String, Text
from app.core.db import Base


def _now():
    return datetime.now(timezone.utc)


class ProductoEncipharm(Base):
    """Catalogo minimo de productos Encipharm (D5): base de las equivalencias y la comparativa."""

    __tablename__ = "productos_encipharm"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre = Column(String(200), nullable=False)
    sku = Column(String(60), nullable=True, unique=True)
    principiosActivos = Column(String(500), nullable=False, default="")  # separados por ";"
    concentracion = Column(String(100), nullable=True)
    presentacion = Column(String(120), nullable=True)
    unidadMedida = Column(String(10), nullable=False)  # ml | g | dosis
    cantidadPresentacion = Column(Numeric(14, 4), nullable=False)  # unidades de medida por envase
    precioLista = Column(Numeric(14, 2), nullable=True)
    moneda = Column(String(3), nullable=False, default="CLP")
    categoria = Column(String(100), nullable=True, index=True)
    especie = Column(String(100), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    createdAt = Column(DateTime, default=_now, nullable=False)
    updatedAt = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class ProductoCompetencia(Base):
    __tablename__ = "productos_competencia"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    competidor = Column(String(160), nullable=False)
    nombre = Column(String(200), nullable=False)
    principiosActivos = Column(String(500), nullable=False, default="")  # separados por ";"
    concentracion = Column(String(100), nullable=True)
    presentacion = Column(String(120), nullable=True)
    unidadMedida = Column(String(10), nullable=False)  # ml | g | dosis
    cantidadPresentacion = Column(Numeric(14, 4), nullable=False)
    categoria = Column(String(100), nullable=True, index=True)
    especie = Column(String(100), nullable=True)
    registroSag = Column(String(60), nullable=True)
    creadoPor = Column(String(36), ForeignKey("users.id"), nullable=True)
    createdAt = Column(DateTime, default=_now, nullable=False)
    updatedAt = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class EquivalenciaProducto(Base):
    """Producto de la competencia <-> producto Encipharm equivalente. El id es "<competencia>:<encipharm>"."""

    __tablename__ = "equivalencias_producto"

    id = Column(String(80), primary_key=True)
    productoCompetenciaId = Column(String(36), nullable=False, index=True)
    productoEncipharmId = Column(String(36), nullable=False, index=True)


class PrecioCompetencia(Base):
    """Cada reporte de precio es un registro nuevo: el historial nunca se pisa."""

    __tablename__ = "precios_competencia"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    productoId = Column(String(36), ForeignKey("productos_competencia.id", ondelete="CASCADE"), nullable=False, index=True)
    precio = Column(Numeric(14, 2), nullable=False)
    moneda = Column(String(3), nullable=False, default="CLP")
    fuente = Column(String(240), nullable=True)
    fechaPrecio = Column(Date, nullable=False, default=date.today)
    zona = Column(String(120), nullable=True)
    clienteId = Column(String(36), ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True)
    nota = Column(Text, nullable=True)
    estado = Column(String(12), nullable=False, default="pendiente", index=True)  # pendiente | aprobado | descartado
    reportadoPor = Column(String(36), ForeignKey("users.id"), nullable=False)
    revisadoPor = Column(String(36), ForeignKey("users.id"), nullable=True)
    revisadoAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, default=_now, nullable=False)
