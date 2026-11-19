from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, ForeignKey, String
from app.core.db import Base


class AccountToken(Base):
    """Enlace de un solo uso para crear o restablecer una contrasena.

    Solo se guarda el hash del token: el valor real viaja unicamente en el enlace.
    Las fechas se guardan en UTC sin zona, como el resto de las columnas.
    """

    __tablename__ = "account_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    usuarioId = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tokenHash = Column(String(64), nullable=False, unique=True)
    tipo = Column(String(20), nullable=False)  # "invitacion" o "reset"
    expiresAt = Column(DateTime, nullable=False)
    usedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
