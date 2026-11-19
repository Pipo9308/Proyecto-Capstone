import pytest

from app.models_sql.rag import RagChunk, RagDocument
from app.services import rag_service


class _FakeEmbeddingModel:
    def embed(self, chunks):
        return [[0.0] * 384 for _ in chunks]


@pytest.fixture
def enforced_foreign_keys():
    """Firestore no tiene claves foraneas: el orden documento -> fragmentos ya no lo impone la base, solo se verifica
    que quede consistente (sin documentos ni fragmentos huerfanos)."""
    yield


@pytest.fixture
def stubbed_storage(monkeypatch):
    monkeypatch.setattr(rag_service, "upload_document_bytes", lambda name, content, content_type: f"rag/{name}")
    monkeypatch.setattr(rag_service, "_load_embedding_model", lambda: _FakeEmbeddingModel())


def test_upload_registers_document_before_its_chunks(db_session, enforced_foreign_keys, stubbed_storage):
    user = {"uid": "admin-1", "email": "admin@enci.cl", "rol": "admin"}

    result = rag_service.upload_and_index_document(
        db_session, "manual.txt", b"Protocolo de vacunacion para aves. " * 20, "text/plain", user
    )

    document = db_session.query(RagDocument).filter(RagDocument.nombre == "manual.txt").one()
    assert result["chunks_indexados"] >= 1
    assert document.chunks_count == result["chunks_indexados"]
    assert db_session.query(RagChunk).filter(RagChunk.documentoId == document.id).count() == document.chunks_count


def test_failed_indexing_leaves_no_orphan_document(db_session, enforced_foreign_keys, stubbed_storage, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("embeddings caidos")

    monkeypatch.setattr(rag_service, "add_chunks_to_index", boom)

    with pytest.raises(RuntimeError):
        rag_service.upload_and_index_document(
            db_session, "roto.txt", b"contenido suficiente para indexar", "text/plain", {"uid": "admin-1"}
        )

    assert db_session.query(RagDocument).count() == 0
    assert db_session.query(RagChunk).count() == 0
