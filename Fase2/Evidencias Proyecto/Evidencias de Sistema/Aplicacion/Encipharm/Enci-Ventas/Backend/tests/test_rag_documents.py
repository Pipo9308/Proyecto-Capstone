"""Documentos del RAG (RQ-07): estados, indexacion en segundo plano, duplicados, borrado y limite de tamano."""
from contextlib import nullcontext
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api import rag as rag_api
from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models_sql.rag import RagChunk, RagDocument
from app.models_sql.user import User
from app.services import rag_service

TEXT = b"Protocolo de vacunacion para aves de postura. " * 30


class FakeEmbeddings:
    def embed(self, chunks):
        return [[0.0] * 384 for _ in chunks]


@pytest.fixture
def storage(monkeypatch):
    """Almacenamiento y modelo de embeddings en memoria."""
    blobs: dict[str, bytes] = {}
    deleted: list[str] = []

    def upload(name, content, content_type):
        blobs[f"rag/{name}"] = content
        return f"rag/{name}"

    monkeypatch.setattr(rag_api, "upload_document_bytes", upload)
    monkeypatch.setattr(rag_service, "delete_document_blob", lambda path: deleted.append(path) or blobs.pop(path, None))
    monkeypatch.setattr(rag_service, "_load_embedding_model", lambda: FakeEmbeddings())
    return blobs, deleted


@pytest.fixture
def admin(db_session):
    now = datetime.now(timezone.utc)
    user = User(
        id="admin-1", email="admin@test.cl", nombre="Admin", rol="admin", activo=True,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def env(client, db_session, storage):
    app.dependency_overrides[rag_api.get_rag_session_factory] = lambda: (lambda: nullcontext(db_session))
    return storage


def _headers(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


def upload(client, admin, name="manual.txt", content=TEXT):
    return client.post("/rag/documents/upload", files={"file": (name, content, "text/plain")}, headers=_headers(admin))


def documents(client, admin):
    return client.get("/rag/documents", headers=_headers(admin)).json()


# ── Estados ──────────────────────────────────────────────────────────────────

def test_upload_answers_202_and_the_document_ends_up_ready(client, env, admin, db_session):
    response = upload(client, admin)

    assert response.status_code == 202
    assert response.json()["estado"] == "subido" and response.json()["documento"] == "manual.txt"
    listed = documents(client, admin)
    assert len(listed) == 1
    assert listed[0]["estado"] == "listo" and listed[0]["chunks_count"] >= 1 and listed[0]["error"] is None
    assert db_session.query(RagChunk).count() == listed[0]["chunks_count"]


def test_the_document_is_registered_before_indexing_runs(client, env, admin, monkeypatch, db_session):
    """Mientras se procesa, la lista ya muestra el documento en estado `procesando`."""
    seen = {}
    original = rag_service.index_document_content

    def spy(db, *args, **kwargs):
        seen["estado"] = db.query(RagDocument).one().estado
        return original(db, *args, **kwargs)

    monkeypatch.setattr(rag_service, "index_document_content", spy)

    upload(client, admin)

    assert seen["estado"] == "procesando"


def test_a_failure_while_indexing_leaves_the_document_in_error_with_the_reason(client, env, admin, monkeypatch, db_session):
    def boom(*args, **kwargs):
        raise HTTPException(status_code=503, detail="El modelo de embeddings no esta disponible")

    monkeypatch.setattr(rag_service, "add_chunks_to_index", boom)

    assert upload(client, admin).status_code == 202

    doc = documents(client, admin)[0]
    assert doc["estado"] == "error" and "embeddings" in doc["error"] and doc["chunks_count"] == 0
    assert db_session.query(RagChunk).count() == 0


def test_a_document_without_extractable_text_is_flagged(client, env, admin):
    upload(client, admin, content=b"   \n  \n ")

    doc = documents(client, admin)[0]

    assert doc["estado"] == "error" and "extraer texto" in doc["error"]


# ── Duplicados ───────────────────────────────────────────────────────────────

def test_same_content_with_another_name_is_rejected(client, env, admin, db_session):
    upload(client, admin, "uno.txt")

    response = upload(client, admin, "otro-nombre.txt")

    assert response.status_code == 409
    body = response.json()
    assert body["codigo"] == "ERR_DOCUMENTO_DUPLICADO" and body["detalles"]["motivo"] == "contenido"
    assert "uno.txt" in body["error"]
    assert db_session.query(RagDocument).count() == 1


def test_same_name_with_different_content_is_rejected(client, env, admin):
    upload(client, admin, "uno.txt")

    response = upload(client, admin, "uno.txt", content=TEXT + b" version nueva")

    assert response.status_code == 409 and response.json()["detalles"]["motivo"] == "nombre"


def test_a_rejected_duplicate_is_not_stored(client, env, admin):
    blobs, _ = env
    upload(client, admin, "uno.txt")

    upload(client, admin, "dos.txt")

    assert list(blobs) == ["rag/uno.txt"]


# ── Borrado ──────────────────────────────────────────────────────────────────

def test_deleting_removes_the_document_its_chunks_and_the_file(client, env, admin, db_session):
    blobs, deleted = env
    upload(client, admin)
    doc_id = documents(client, admin)[0]["id"]

    response = client.delete(f"/rag/documents/{doc_id}", headers=_headers(admin))

    assert response.status_code == 204
    assert documents(client, admin) == []
    assert db_session.query(RagChunk).count() == 0
    assert deleted == ["rag/manual.txt"] and blobs == {}


def test_a_deleted_document_can_be_uploaded_again(client, env, admin):
    upload(client, admin)
    client.delete(f"/rag/documents/{documents(client, admin)[0]['id']}", headers=_headers(admin))

    assert upload(client, admin).status_code == 202


def test_deleting_works_even_if_the_file_is_already_gone(client, env, admin, monkeypatch):
    upload(client, admin)
    doc_id = documents(client, admin)[0]["id"]

    def broken(path):
        raise RuntimeError("storage caido")

    monkeypatch.setattr(rag_service, "delete_document_blob", broken)

    assert client.delete(f"/rag/documents/{doc_id}", headers=_headers(admin)).status_code == 204


def test_deleting_an_unknown_document_is_404(client, env, admin):
    assert client.delete("/rag/documents/no-existe", headers=_headers(admin)).status_code == 404


# ── Validaciones y permisos ──────────────────────────────────────────────────

def test_size_limit_is_25_mb_by_default():
    assert get_settings().RAG_MAX_UPLOAD_BYTES == 25 * 1024 * 1024


def test_files_over_the_limit_are_rejected_with_the_limit_in_the_message(client, env, admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "RAG_MAX_UPLOAD_BYTES", 2 * 1024 * 1024)

    response = upload(client, admin, content=b"a" * (2 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert "2 MB" in str(response.json())


def test_unsupported_formats_are_rejected(client, env, admin):
    response = client.post("/rag/documents/upload", files={"file": ("virus.exe", b"MZ", "application/octet-stream")}, headers=_headers(admin))

    assert response.status_code == 422


def test_only_admins_manage_documents(client, env, db_session):
    now = datetime.now(timezone.utc)
    vendedor = User(
        id="v-1", email="v1@test.cl", nombre="V", rol="vendedor", activo=True, password_hash=get_password_hash("ClaveInicial123"),
        webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db_session.add(vendedor)
    db_session.commit()

    assert upload(client, vendedor).status_code == 403
    assert client.get("/rag/documents", headers=_headers(vendedor)).status_code == 403
    assert client.delete("/rag/documents/x", headers=_headers(vendedor)).status_code == 403
    assert client.post("/rag/documents/upload", files={"file": ("a.txt", TEXT)}).status_code == 401


def test_los_admins_reciben_un_aviso_cuando_un_documento_queda_listo_o_falla(client, env, admin, db_session, monkeypatch):
    from app.models_sql.notificacion import Notificacion

    upload(client, admin)
    upload(client, admin, name="vacio.txt", content=b"   \n  \n ")

    titles = sorted(n.titulo for n in db_session.query(Notificacion).filter(Notificacion.usuarioId == admin.id).all())
    assert len(titles) == 2
    assert any(t.startswith("Documento listo") for t in titles)
    assert any(t.startswith("Falló la indexación") for t in titles)
