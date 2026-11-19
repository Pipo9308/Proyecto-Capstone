import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool

from app.api.auth import require_admin
from app.api.rate_limiter import check_and_increment
from app.api import cache as _cache
from app.rag import engine
from app.rag.loader import DOCS_DIR

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
GCS_DOCS_PREFIX = "docs/"


def _get_azure_container():
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not conn_str:
        return None
    from azure.storage.blob import BlobServiceClient
    try:
        blob_service_client = BlobServiceClient.from_connection_string(conn_str)
        container_client = blob_service_client.get_container_client("rag-store")
        if not container_client.exists():
            container_client.create_container()
        return container_client
    except Exception as e:
        print(f"Failed to connect to Azure Storage: {e}")
        return None


@router.get("/")
def list_documents(current_user=Depends(require_admin)):
    cached = _cache.get("documents")
    if cached:
        return cached

    indexed = {d["filename"]: d["chunks"] for d in engine.list_documents()}
    files = []

    container = _get_azure_container()
    if container:
        for blob in container.list_blobs(name_starts_with=GCS_DOCS_PREFIX):
            name = blob.name[len(GCS_DOCS_PREFIX):]
            if not name or Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            meta = engine._doc_metadata.get(name, {})
            files.append({
                "filename": name,
                "title": meta.get("title", name),
                "category": meta.get("category", "DOC"),
                "size_kb": round(blob.size / 1024, 1),
                "chunks": indexed.get(name, 0),
                "indexed": name in indexed,
            })
    else:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        for path in sorted(DOCS_DIR.glob("*")):
            if path.suffix.lower() in ALLOWED_EXTENSIONS:
                meta = engine._doc_metadata.get(path.name, {})
                files.append({
                    "filename": path.name,
                    "title": meta.get("title", path.name),
                    "category": meta.get("category", "DOC"),
                    "size_kb": round(path.stat().st_size / 1024, 1),
                    "chunks": indexed.get(path.name, 0),
                    "indexed": path.name in indexed,
                })

    result = {"success": True, "data": files}
    _cache.set("documents", result, ttl=60)
    return result


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("DOC"),
    current_user=Depends(require_admin),
):
    if not check_and_increment(f"upload:{current_user['sub']}", limit=20, window="day"):
        raise HTTPException(status_code=429, detail="Límite de subidas alcanzado (20/día).")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF o TXT.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Archivo demasiado grande (máx 50 MB).")

    safe_name = Path(file.filename).name

    # Index from a temp dir (works in Cloud Run where DOCS_DIR may be read-only)
    extracted_text = ""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / safe_name
        tmp_path.write_bytes(content)
        try:
            # index_file es sincrono y lento (embeddings): en un hilo aparte para
            # no bloquear el event loop de todo el backend.
            result = await run_in_threadpool(engine.index_file, tmp_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al indexar: {e}")
        # Extract text for AI metadata generation
        try:
            from app.rag.loader import _load_pdf, _load_txt
            docs = _load_pdf(tmp_path) if suffix == ".pdf" else _load_txt(tmp_path)
            extracted_text = " ".join(d["text"] for d in docs[:5])
        except Exception:
            extracted_text = ""

    # Persist file to GCS or local docs dir
    container = _get_azure_container()
    if container:
        blob_client = container.get_blob_client(f"{GCS_DOCS_PREFIX}{safe_name}")
        blob_client.upload_blob(content, overwrite=True)
    else:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        (DOCS_DIR / safe_name).write_bytes(content)

    # Generate metadata with AI if not provided manually
    if title.strip():
        friendly_title = title.strip()
        friendly_category = category.strip() or "DOC"
    elif extracted_text:
        ai_meta = await run_in_threadpool(engine.generate_doc_metadata, extracted_text)
        friendly_title = ai_meta.get("title") or safe_name
        friendly_category = ai_meta.get("category", "DOC")
    else:
        friendly_title = safe_name
        friendly_category = "DOC"

    await engine.set_doc_metadata(safe_name, friendly_title, friendly_category)
    _cache.invalidate("documents")

    return {
        "success": True,
        "data": {
            "filename": safe_name,
            "new_chunks": result["new_chunks"],
            "total_chunks": engine._store.count if engine._store else 0,
            "is_veterinary": result["is_veterinary"],
        },
    }


@router.delete("/{filename}")
async def delete_document(filename: str, current_user=Depends(require_admin)):
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido.")

    container = _get_azure_container()
    if container:
        blob_client = container.get_blob_client(f"{GCS_DOCS_PREFIX}{safe_name}")
        if not blob_client.exists():
            raise HTTPException(status_code=404, detail="Archivo no encontrado.")
        blob_client.delete_blob()
    else:
        path = DOCS_DIR / safe_name
        if not path.exists():
            raise HTTPException(status_code=404, detail="Archivo no encontrado.")
        path.unlink()

    removed_chunks = engine.remove_file(safe_name)
    await engine.delete_doc_metadata(safe_name)
    _cache.invalidate("documents")
    return {
        "success": True,
        "data": {
            "filename": safe_name,
            "chunks_removed": removed_chunks,
            "total_chunks": engine._store.count if engine._store else 0,
        },
    }
