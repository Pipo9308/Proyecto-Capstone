from datetime import datetime, timezone
import uuid

from app.core.odm import Column, DateTime, Integer, JSON, String
from app.core.db import Base


class AuditLog(Base):
    """Registro de auditoria (RNF-03): quien hizo que, cuando, desde donde y como termino.

    Tabla aparte de los datos del dia a dia. La aplicacion solo inserta y consulta: no hay
    endpoints para editar ni borrar registros.
    """

    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    createdAt = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    userUid = Column(String(36), nullable=True)  # sin clave foranea: el registro sobrevive al usuario
    userRole = Column(String(20), nullable=True)
    method = Column(String(8), nullable=False)
    route = Column(String(200), nullable=False)  # plantilla, p. ej. /clientes/{cliente_id}
    resource = Column(String(60), nullable=False)
    resourceId = Column(String(120), nullable=True)
    statusCode = Column(Integer, nullable=False)
    result = Column(String(10), nullable=False)  # success | denied | failure | error
    ip = Column(String(64), nullable=True)
    userAgent = Column(String(300), nullable=True)
    client = Column(String(10), nullable=True)  # web | mobile
    details = Column(JSON, nullable=True)
