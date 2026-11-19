"""VectorStore sobre Firestore REAL (los vectores no los soporta el emulador). Se omite sin credenciales.
Variables: GOOGLE_APPLICATION_CREDENTIALS y REAL_FIREBASE_PROJECT_ID (conftest fija FIREBASE_PROJECT_ID=enci-test).
Usa la coleccion fija intel_docs_test, que necesita su indice vectorial (scripts/create_vector_index.py intel_docs_test)."""
import os
import random

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or not os.environ.get("REAL_FIREBASE_PROJECT_ID") or os.environ.get("FIRESTORE_EMULATOR_HOST"),
    reason="sin credenciales de Firestore real",
)

os.environ["RAG_COLLECTION"] = "intel_docs_test"
from app.rag.store import EMBEDDING_SIZE, VectorStore  # noqa: E402


def vec(seed):
    rnd = random.Random(seed)
    return [rnd.random() for _ in range(EMBEDDING_SIZE)]


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", os.environ["REAL_FIREBASE_PROJECT_ID"])
    s = VectorStore()
    s.remove_by_source("t1.pdf"), s.remove_by_source("t2.pdf")
    yield s
    s.remove_by_source("t1.pdf"), s.remove_by_source("t2.pdf")


def test_agregar_buscar_filtrar_y_borrar(store):
    store.add({"id": "t1.pdf::0", "source": "t1.pdf", "species": "bovino", "text": "uno"}, vec(1))
    store.add({"id": "t1.pdf::1", "source": "t1.pdf", "species": "porcino", "text": "dos"}, vec(2))
    store.add({"id": "t2.pdf::0", "source": "t2.pdf", "species": "bovino", "text": "tres"}, vec(3))

    assert store.is_indexed("t1.pdf::0") and not store.is_indexed("nada::9")
    best = store.search(vec(2), n=1, threshold=0.0)[0]
    assert best["text"] == "dos" and best["score"] > 0.999 and "embedding" not in best
    only_bovine = store.search(vec(2), n=5, species="bovino", threshold=0.0)
    assert {h["text"] for h in only_bovine} == {"uno", "tres"}
    assert store.search(vec(2), n=5, threshold=0.9999)[0]["text"] == "dos"  # el umbral descarta los demas
    assert store.chunk_count_by_filename() == {"t1.pdf": 2, "t2.pdf": 1}
    assert store.remove_by_source("t1.pdf") == 2
    assert not store.is_indexed("t1.pdf::0")
