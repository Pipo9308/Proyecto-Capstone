from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, ForeignKey, String, Unique
from app.core.db import Base


class IntelLectura(Base):
    """Alertas de Enci-Intel que un usuario ya leyo (Intel no guarda lecturas por usuario de Ventas)."""

    __tablename__ = "intel_lecturas"
    __unique__ = (Unique("usuarioId", "alertId"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuarioId = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alertId = Column(String(120), nullable=False)
    leidaEn = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
