from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, Float, ForeignKey, Integer, String
from app.core.db import Base

class Opportunity(Base):
    __tablename__ = "oportunidades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clienteId = Column(String(36), ForeignKey("clientes.id"), nullable=False)
    titulo = Column(String(160), nullable=False)
    etapa = Column(String(50), default="nuevo", nullable=False)
    valorEstimado = Column(Float, default=0, nullable=False)
    probabilidad = Column(Integer, default=0, nullable=False)
    descripcion = Column(String(1000), nullable=True)
    vendedorUid = Column(String(36), ForeignKey("users.id"), nullable=False)

    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Interaction(Base):
    __tablename__ = "interacciones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clienteId = Column(String(36), ForeignKey("clientes.id"), nullable=False)
    tipo = Column(String(50), nullable=False)
    fecha = Column(DateTime, nullable=False)
    resumen = Column(String(1000), nullable=False)
    resultado = Column(String(500), nullable=True)
    proximaAccion = Column(String(500), nullable=True)
    vendedorUid = Column(String(36), ForeignKey("users.id"), nullable=False)

    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Proposal(Base):
    __tablename__ = "propuestas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clienteId = Column(String(36), ForeignKey("clientes.id"), nullable=False)
    oportunidadId = Column(String(36), ForeignKey("oportunidades.id"), nullable=False)
    titulo = Column(String(160), nullable=False)
    montoNeto = Column(Float, nullable=False)
    descuentoPct = Column(Float, default=0, nullable=False)
    estado = Column(String(50), default="borrador", nullable=False)
    notas = Column(String(1000), nullable=True)
    vendedorUid = Column(String(36), ForeignKey("users.id"), nullable=False)

    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


    @property
    def montoDescuento(self):
        return self.montoNeto * (self.descuentoPct / 100)

    @property
    def montoTotal(self):
        return self.montoNeto - self.montoDescuento
