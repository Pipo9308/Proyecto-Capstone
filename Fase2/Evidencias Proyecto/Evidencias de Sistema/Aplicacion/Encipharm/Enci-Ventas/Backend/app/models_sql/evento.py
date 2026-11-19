from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, ForeignKey, String, Text
from app.core.db import Base


class Evento(Base):
    """Visita, reunion o llamada planificada con un cliente (RQ-02). Las horas se guardan en UTC."""

    __tablename__ = "eventos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clienteId = Column(String(36), ForeignKey("clientes.id"), nullable=False, index=True)
    oportunidadId = Column(String(36), ForeignKey("oportunidades.id", ondelete="SET NULL"), nullable=True)
    vendedorUid = Column(String(36), ForeignKey("users.id"), nullable=False)
    tipo = Column(String(12), nullable=False)  # presencial | virtual | llamada
    inicio = Column(DateTime, nullable=False)
    fin = Column(DateTime, nullable=False)
    lugar = Column(String(200), nullable=True)
    notas = Column(Text, nullable=True)
    estado = Column(String(12), nullable=False, default="planificada")  # planificada | realizada | cancelada
    interaccionId = Column(String(36), ForeignKey("interacciones.id", ondelete="SET NULL"), nullable=True)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
