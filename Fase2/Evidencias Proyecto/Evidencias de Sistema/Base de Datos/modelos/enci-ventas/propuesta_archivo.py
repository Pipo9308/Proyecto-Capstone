from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, ForeignKey, Integer, String
from app.core.db import Base


class PropuestaArchivo(Base):
    """PDF adjunto a una propuesta (el archivo vive en el almacenamiento de blobs)."""

    __tablename__ = "propuesta_archivos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    propuestaId = Column(String(36), ForeignKey("propuestas.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    tamanoBytes = Column(Integer, nullable=False)
    contentType = Column(String(100), nullable=False, default="application/pdf")
    ruta = Column(String(500), nullable=False)
    subidoPor = Column(String(36), ForeignKey("users.id"), nullable=False)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
