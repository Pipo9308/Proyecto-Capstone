from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, ForeignKey, String, Unique
from app.core.db import Base

class Cliente(Base):
    __tablename__ = "clientes"
    # Un RUT identifica a un solo cliente activo; los dados de baja no bloquean uno nuevo.
    __unique__ = (Unique("rut", where=lambda d: bool(d.get("rut")) and d.get("estado") != "Eliminado"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre = Column(String(120), nullable=False)
    empresa = Column(String(160), nullable=False)
    rut = Column(String(16), nullable=True)
    email = Column(String(255), nullable=True)
    telefono = Column(String(32), nullable=True)
    rubro = Column(String(120), nullable=True)
    region = Column(String(80), nullable=True)
    estado = Column(String(50), default="En proceso", nullable=False)
    
    vendedorUid = Column(String(36), ForeignKey("users.id"), nullable=True)
    ownerUid = Column(String(36), ForeignKey("users.id"), nullable=True)

    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

