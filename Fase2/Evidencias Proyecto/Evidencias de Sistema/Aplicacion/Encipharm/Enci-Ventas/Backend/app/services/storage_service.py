from collections.abc import Iterator
from pathlib import Path
from fastapi import HTTPException, status
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

from app.core.config import get_settings

def _get_container_client():
    settings = get_settings()
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage connection string no configurada",
        )

    try:
        blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
        if not container_client.exists():
            container_client.create_container()
        return container_client
    except AzureError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Storage de documentos no disponible: {e}",
        )


def upload_document_bytes(file_name: str, content: bytes, content_type: str) -> str:
    blob_name = f"rag/{file_name}"
    return upload_blob_bytes(blob_name, content, content_type)


def upload_blob_bytes(blob_name: str, content: bytes, content_type: str) -> str:
    """Guarda un archivo en la ruta indicada del contenedor y devuelve esa ruta."""
    container_client = _get_container_client()
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(content, overwrite=True) # type: ignore
    return blob_name


def download_document_bytes(azure_path: str) -> bytes:

    container_client = _get_container_client()
    blob_client = container_client.get_blob_client(azure_path)
    if not blob_client.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento no encontrado en storage",
        )
    return blob_client.download_blob().readall()


def iter_blob_chunks(azure_path: str) -> Iterator[bytes]:
    """Lee un archivo por trozos (para enviarlo sin cargarlo entero en memoria)."""
    container_client = _get_container_client()
    blob_client = container_client.get_blob_client(azure_path)
    if not blob_client.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado en storage")
    yield from blob_client.download_blob().chunks()


def delete_document_blob(azure_path: str) -> None:
    """Borra un archivo del contenedor; si ya no existe no es un error."""
    container_client = _get_container_client()
    blob_client = container_client.get_blob_client(azure_path)
    if blob_client.exists():
        blob_client.delete_blob()


def get_extension(file_name: str) -> str:
    return Path(file_name or "").suffix.lower()
