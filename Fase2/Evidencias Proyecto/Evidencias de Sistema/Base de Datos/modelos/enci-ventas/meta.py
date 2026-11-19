from datetime import datetime, timezone

from app.core.odm import Column, DateTime, Float, ForeignKey, String
from app.core.db import Base


class MetaVenta(Base):
    """Meta mensual de ventas (CLP) de un vendedor. El id es "<vendedorUid>:<AAAA-MM>"."""

    __tablename__ = "metas_ventas"

    id = Column(String(60), primary_key=True)
    vendedorUid = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mes = Column(String(7), nullable=False)
    monto = Column(Float, nullable=False, default=0)
    fijadaPor = Column(String(36), nullable=True)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
