from datetime import datetime, timezone
import uuid

from app.core.odm import Boolean, Column, DateTime, String
from app.core.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    nombre = Column(String(255), nullable=False)
    rol = Column(String(50), default="sin_acceso", nullable=False)
    cargo = Column(String(80), default="Sin acceso", nullable=False)
    rango = Column(String(50), default="Sin acceso", nullable=False)
    zona = Column(String(50), default="Zona centro", nullable=False)
    appMovil = Column(Boolean, default=False, nullable=False)
    webApp = Column(Boolean, default=False, nullable=False)
    # Permiso por usuario para las pantallas y el chat de Enci-Intel (el admin siempre accede).
    accesoInteligencia = Column(Boolean, default=False, nullable=False)
    theme = Column(String(20), default="dark", nullable=False)
    language = Column(String(10), default="es", nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    # Cuando el usuario pidio restablecer su contrasena (un admin le genera un enlace).
    passwordResetRequestedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updatedAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
