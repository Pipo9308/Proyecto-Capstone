"""Busqueda vectorial de la capa de datos contra Firestore REAL (el emulador no soporta vectores). Se omite sin
credenciales. Requiere GOOGLE_APPLICATION_CREDENTIALS y REAL_FIREBASE_PROJECT_ID, y el indice vectorial de la coleccion
de prueba (python scripts/create_vector_index.py ventas_rag_chunks_test 384)."""
import os
import random

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or not os.environ.get("REAL_FIREBASE_PROJECT_ID"),
    reason="sin credenciales de Firestore real",
)

from app.core.db import Base  # noqa: E402
from app.core.odm import Column, Integer, String, Vector  # noqa: E402


class ChunkTest(Base):
    __tablename__ = "rag_chunks_test"  # el prefijo ventas_ lo agrega la capa de datos
    id = Column(String(36), primary_key=True)
    texto = Column(String)
    pagina = Column(Integer)
    embedding = Column(Vector(384))


def vec(seed):
    rnd = random.Random(seed)
    return [rnd.random() for _ in range(384)]


@pytest.fixture
def real_session(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)  # el cliente real no debe ir al emulador
    from google.cloud import firestore
    from app.core.odm import Session
    session = Session(firestore.Client(project=os.environ["REAL_FIREBASE_PROJECT_ID"]))
    session.query(ChunkTest).delete()
    yield session
    session.query(ChunkTest).delete()


def test_nearest_devuelve_el_mas_cercano_con_su_distancia(real_session):
    for i in (1, 2, 3):
        real_session.add(ChunkTest(id=f"c{i}", texto=f"texto {i}", pagina=i, embedding=vec(i)))
    real_session.commit()

    hits = real_session.nearest(ChunkTest, "embedding", vec(2), 2)

    best, distance = hits[0]
    assert best.texto == "texto 2" and best.pagina == 2 and distance < 1e-6
    assert len(hits) == 2 and hits[1][1] > distance
    assert len(best.embedding) == 384
