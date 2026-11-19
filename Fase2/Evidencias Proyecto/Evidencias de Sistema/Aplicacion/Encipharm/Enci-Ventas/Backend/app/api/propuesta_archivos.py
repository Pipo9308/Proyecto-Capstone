from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.odm import Session
from datetime import datetime

from app.core.auth import require_role
from app.core.db import get_db
from app.services import propuesta_archivos as service
from app.services.storage_service import iter_blob_chunks

router = APIRouter(tags=["Adjuntos de propuestas"])


class AttachmentResponse(BaseModel):
    id: str
    propuestaId: str
    nombre: str
    tamanoBytes: int
    subidoPor: str
    subidoPorNombre: str | None = None
    createdAt: datetime | None = None


class DownloadLink(BaseModel):
    url: str
    expiraEn: datetime


@router.post(
    "/propuestas/{propuesta_id}/archivos", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED
)
async def upload_attachment(
    propuesta_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
):
    """Adjunta un PDF (hasta 20 MB, maximo 10 por propuesta)."""
    proposal = service.get_visible_proposal(db, propuesta_id, user)
    content = await file.read()
    return await run_in_threadpool(service.add_attachment, db, proposal, file.filename or "adjunto.pdf", content, user)


@router.get("/propuestas/{propuesta_id}/archivos", response_model=list[AttachmentResponse])
async def list_attachments(
    propuesta_id: str, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)
):
    return service.list_attachments(db, service.get_visible_proposal(db, propuesta_id, user))


@router.get("/propuestas/{propuesta_id}/archivos/{archivo_id}/enlace", response_model=DownloadLink)
async def attachment_link(
    propuesta_id: str, archivo_id: str, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)
):
    """Enlace firmado de descarga: vence a los pocos minutos y se abre sin enviar el token de sesion."""
    return service.create_download_link(db, service.get_visible_proposal(db, propuesta_id, user), archivo_id)


@router.delete("/propuestas/{propuesta_id}/archivos/{archivo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(
    propuesta_id: str, archivo_id: str, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)
):
    await run_in_threadpool(
        service.delete_attachment, db, service.get_visible_proposal(db, propuesta_id, user), archivo_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/propuestas/archivos/descarga")
async def download_attachment(token: str = Query(min_length=10, max_length=2000), db: Session = Depends(get_db)):
    """Descarga el PDF con un enlace firmado (el enlace es la credencial)."""
    attachment = service.resolve_download_token(db, token)
    return StreamingResponse(
        iter_blob_chunks(attachment.ruta),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.nombre)}",
            "Cache-Control": "no-store",
        },
    )
