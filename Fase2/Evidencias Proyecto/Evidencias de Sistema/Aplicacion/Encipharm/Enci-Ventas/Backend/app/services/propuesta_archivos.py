"""PDF adjuntos de propuestas (RQ-07): subir, listar, descargar con enlace firmado y borrar.

Permisos: el dueño de la propuesta, un supervisor o un admin. La descarga usa un enlace firmado
que vence (no hace falta enviar el token de sesion al abrirlo en el navegador).
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from app.core.odm import Session

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.models_sql.comercial import Proposal
from app.models_sql.propuesta_archivo import PropuestaArchivo
from app.models_sql.user import User
from app.services.storage_service import delete_document_blob, upload_blob_bytes

DOWNLOAD_TOKEN_TYPE = "descarga_adjunto"


def _error(http_status: int, message: str, code: str | None = None) -> HTTPException:
    if code is None:
        return HTTPException(status_code=http_status, detail=message)
    return HTTPException(status_code=http_status, detail={"error": message, "codigo": code, "detalles": None})


def get_visible_proposal(db: Session, proposal_id: str, user: dict) -> Proposal:
    """La propuesta, si el usuario puede verla: su dueño, un supervisor o un admin."""
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if proposal is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Propuesta no encontrada")
    if user["rol"] == "vendedor" and proposal.vendedorUid != user["uid"]:
        raise _error(status.HTTP_403_FORBIDDEN, "No tienes permisos para esta propuesta")
    return proposal


def _display_name(file_name: str) -> str:
    """Nombre legible del archivo, sin rutas ni caracteres de control."""
    name = re.split(r"[\\/]", file_name or "")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "adjunto.pdf")[:200]


def validate_pdf(file_name: str, content: bytes) -> None:
    settings = get_settings()
    if not content:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Archivo vacio")
    if len(content) > settings.PROPUESTA_MAX_ARCHIVO_BYTES:
        raise _error(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"El archivo supera el maximo de {settings.PROPUESTA_MAX_ARCHIVO_BYTES // (1024 * 1024)} MB",
        )
    if not (file_name or "").lower().endswith(".pdf") or not content.startswith(b"%PDF"):
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Solo se permiten archivos PDF")


def _to_dict(attachment: PropuestaArchivo, uploader: str | None) -> dict:
    return {
        "id": attachment.id,
        "propuestaId": attachment.propuestaId,
        "nombre": attachment.nombre,
        "tamanoBytes": attachment.tamanoBytes,
        "subidoPor": attachment.subidoPor,
        "subidoPorNombre": uploader,
        "createdAt": attachment.createdAt,
    }


def add_attachment(db: Session, proposal: Proposal, file_name: str, content: bytes, user: dict) -> dict:
    validate_pdf(file_name, content)
    settings = get_settings()
    count = db.query(PropuestaArchivo).filter(PropuestaArchivo.propuestaId == proposal.id).count()
    if count >= settings.PROPUESTA_MAX_ARCHIVOS:
        raise _error(
            status.HTTP_409_CONFLICT,
            f"Una propuesta admite hasta {settings.PROPUESTA_MAX_ARCHIVOS} archivos",
            "ERR_LIMITE_ADJUNTOS",
        )
    attachment_id = str(uuid.uuid4())
    path = upload_blob_bytes(f"propuestas/{proposal.id}/{attachment_id}.pdf", content, "application/pdf")
    attachment = PropuestaArchivo(
        id=attachment_id, propuestaId=proposal.id, nombre=_display_name(file_name), tamanoBytes=len(content),
        contentType="application/pdf", ruta=path, subidoPor=user["uid"],
    )
    db.add(attachment)
    db.commit()
    return _to_dict(attachment, user.get("nombre"))


def list_attachments(db: Session, proposal: Proposal) -> list[dict]:
    attachments = (
        db.query(PropuestaArchivo)
        .filter(PropuestaArchivo.propuestaId == proposal.id)
        .order_by(PropuestaArchivo.createdAt.asc())
        .all()
    )
    names = {u.id: u.nombre for u in db.query(User).filter(User.id.in_({a.subidoPor for a in attachments})).all()} if attachments else {}
    return [_to_dict(attachment, names.get(attachment.subidoPor)) for attachment in attachments]


def _get_attachment(db: Session, proposal: Proposal, attachment_id: str) -> PropuestaArchivo:
    attachment = (
        db.query(PropuestaArchivo)
        .filter(PropuestaArchivo.id == attachment_id, PropuestaArchivo.propuestaId == proposal.id)
        .first()
    )
    if attachment is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Archivo no encontrado")
    return attachment


def delete_attachment(db: Session, proposal: Proposal, attachment_id: str) -> None:
    attachment = _get_attachment(db, proposal, attachment_id)
    path = attachment.ruta
    db.delete(attachment)
    db.commit()
    try:
        delete_document_blob(path)
    except Exception:
        # El adjunto ya no existe para el sistema; un blob huerfano no debe fallar el borrado.
        pass


def create_download_link(db: Session, proposal: Proposal, attachment_id: str) -> dict:
    """Enlace firmado que vence a los DOWNLOAD_LINK_MINUTES; se pide con la sesion y se abre sin ella."""
    attachment = _get_attachment(db, proposal, attachment_id)
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.DOWNLOAD_LINK_MINUTES)
    token = jwt.encode(
        {"typ": DOWNLOAD_TOKEN_TYPE, "aid": attachment.id, "exp": expires}, settings.JWT_SECRET, algorithm=ALGORITHM
    )
    return {"url": f"/propuestas/archivos/descarga?token={token}", "expiraEn": expires}


def resolve_download_token(db: Session, token: str) -> PropuestaArchivo:
    """Valida un enlace de descarga (firma, tipo y vencimiento) y devuelve el adjunto."""
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        raise _error(status.HTTP_410_GONE, "El enlace de descarga vencio. Genera uno nuevo.", "ERR_ENLACE_EXPIRADO") from error
    except jwt.PyJWTError as error:
        raise _error(status.HTTP_403_FORBIDDEN, "Enlace de descarga invalido", "ERR_ENLACE_INVALIDO") from error
    if payload.get("typ") != DOWNLOAD_TOKEN_TYPE:
        # Un token de sesion no sirve como enlace de descarga.
        raise _error(status.HTTP_403_FORBIDDEN, "Enlace de descarga invalido", "ERR_ENLACE_INVALIDO")
    attachment = db.query(PropuestaArchivo).filter(PropuestaArchivo.id == payload.get("aid")).first()
    if attachment is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Archivo no encontrado")
    return attachment
