from datetime import datetime, timezone
import uuid

from app.core.odm import Boolean, Column, DateTime, ForeignKey, String, Text, Unique
from app.core.db import Base


class Notificacion(Base):
    """Aviso dentro de la web para un usuario (RQ-01). Se guardan 90 dias."""

    __tablename__ = "notificaciones"
    # Un mismo hecho (alerta, recordatorio) avisa una sola vez a cada usuario.
    __unique__ = (Unique("usuarioId", "tipo", "referencia"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuarioId = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(40), nullable=False)
    titulo = Column(String(200), nullable=False)
    mensaje = Column(Text, nullable=True)
    enlace = Column(String(200), nullable=True)  # ruta de la web a la que lleva el aviso
    referencia = Column(String(120), nullable=True)
    leida = Column(Boolean, nullable=False, default=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
