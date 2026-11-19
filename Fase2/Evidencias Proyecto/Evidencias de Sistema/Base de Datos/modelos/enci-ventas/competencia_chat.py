from datetime import date, datetime, timezone
import uuid

from app.core.odm import Column, Date, DateTime, ForeignKey, Integer, JSON, String, Unique
from app.core.db import Base


class CompetenciaConversacion(Base):
    """Conversacion del chat de competencia; cada usuario ve solo las suyas."""

    __tablename__ = "competencia_conversaciones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuarioId = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(String(255), nullable=True)
    mensajes = Column(JSON, default=list)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CompetenciaUso(Base):
    """Uso diario por usuario: sirve para el tope de preguntas y el reporte de costo."""

    __tablename__ = "competencia_uso"
    __unique__ = (Unique("usuarioId", "dia"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuarioId = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    dia = Column(Date, default=date.today, nullable=False)
    preguntas = Column(Integer, default=0, nullable=False)
    tokensEntrada = Column(Integer, default=0, nullable=False)
    tokensSalida = Column(Integer, default=0, nullable=False)
