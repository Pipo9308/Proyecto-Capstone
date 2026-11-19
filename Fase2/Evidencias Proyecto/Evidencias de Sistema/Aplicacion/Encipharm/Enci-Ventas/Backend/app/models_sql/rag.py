from datetime import datetime, timezone
import uuid

from app.core.odm import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Vector
from app.core.db import Base

class RagDocument(Base):
    __tablename__ = "rag_documentos"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre = Column(String(255), nullable=False)
    nombreOriginal = Column(String(255), nullable=True)
    descripcion = Column(String(1000), nullable=True)
    gcsPath = Column(String(500), nullable=True)
    chunks_count = Column(Integer, default=0)
    subidoPor = Column(String(36), nullable=True)
    subidoPorEmail = Column(String(255), nullable=True)
    tamano_bytes = Column(Integer, default=0)
    activo = Column(Boolean, default=True)
    # subido -> procesando -> listo | error (con el motivo en errorMensaje).
    estado = Column(String(20), default="listo", nullable=False)
    errorMensaje = Column(String(500), nullable=True)
    # SHA-256 del contenido: detecta el mismo archivo subido dos veces aunque cambie el nombre.
    contentHash = Column(String(64), nullable=True)

    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

class RagConversation(Base):
    __tablename__ = "rag_conversaciones"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuarioId = Column(String(36), ForeignKey("users.id"), nullable=False)
    usuarioEmail = Column(String(255), nullable=True)
    rol = Column(String(50), nullable=False)
    titulo = Column(String(255), nullable=True)
    mensajes = Column(JSON, default=list)
    
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    

class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    documentoId = Column(String(36), ForeignKey("rag_documentos.id", ondelete="CASCADE"), nullable=False)
    documentoNombre = Column(String(255), nullable=False)
    pagina = Column(Integer, nullable=True)
    texto = Column(String, nullable=False)
    embedding = Column(Vector(384))
    
