"""Almacen vectorial del RAG de Intel sobre Firestore Vector Search (antes Qdrant).

Misma interfaz que tenia (is_indexed, add, save, search, remove_by_source, chunk_count_by_filename, count).
Cada fragmento es un documento de la coleccion con sus campos y un campo `embedding` (Vector de 2048).

REQUISITO: la coleccion necesita un indice vectorial (scripts/create_vector_index.py). Sin el, search() devuelve
[] y lo avisa en el log, igual que cuando Qdrant no respondia.
shortcut: el filtro por especie se aplica despues de la busqueda (se piden mas vecinos de los necesarios) para no
exigir un indice compuesto especie+vector; si hay muchos documentos de otras especies, subir OVERSAMPLE o crear ese indice.
"""
import os
import uuid

from app.firestore_db import clean_project_id, credentials_from_env  # tambien limpia FIRESTORE_EMULATOR_HOST vacio
from google.cloud import firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

COLLECTION_NAME = os.getenv("RAG_COLLECTION", "intel_docs")
EMBEDDING_SIZE = 2048  # size of nvidia/nemotron-3-embed-1b (via API, ver engine.py)
OVERSAMPLE = 10
_BATCH = 400


def _es_de_la_especie(data: dict, species: str) -> bool:
    """El cargador guarda una lista de especies por fragmento (["Bovino", "Porcino"]); un fragmento sin especie
    detectada es general (p. ej. el listado WOAH de antibioticos) y tambien sirve para cualquier especie."""
    valor = data.get("species")
    especies = valor if isinstance(valor, list) else ([valor] if valor else [])
    return not especies or species.lower() in {str(e).lower() for e in especies}


class VectorStore:
    def __init__(self):
        if os.getenv("FIREBASE_CREDENTIALS_PATH"):
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", os.environ["FIREBASE_CREDENTIALS_PATH"])
        self.client = firestore.Client(project=clean_project_id(os.environ.get("FIREBASE_PROJECT_ID")), credentials=credentials_from_env())
        self.col = self.client.collection(COLLECTION_NAME)

    @staticmethod
    def _doc_id(doc_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))  # ids con "/" no valen en Firestore

    def is_indexed(self, doc_id: str) -> bool:
        try:
            return self.col.document(self._doc_id(doc_id)).get().exists
        except Exception:
            return False

    def add(self, document: dict, embedding: list[float]):
        try:
            self.col.document(self._doc_id(document["id"])).set({**document, "embedding": Vector(embedding)})
        except Exception as e:
            print(f"[RAG] Failed to add document: {e}")

    def save(self):
        pass

    def search(
        self,
        query_embedding: list[float],
        n: int = 5,
        species: str | None = None,
        threshold: float = 0.50,
    ) -> list[dict]:
        try:
            query = self.col.find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_embedding),
                distance_measure=DistanceMeasure.COSINE,
                limit=min(n * OVERSAMPLE if species else n, 1000),
                distance_result_field="_distance",
            )
            hits = []
            for snap in query.get():
                data = snap.to_dict()
                score = 1 - data.pop("_distance")  # similitud coseno, como el score de Qdrant
                data.pop("embedding", None)
                if score >= threshold and (not species or _es_de_la_especie(data, species)):
                    hits.append({**data, "score": score})
            return sorted(hits, key=lambda h: -h["score"])[:n]
        except Exception as e:
            print(f"[RAG] Search failed: {e}")
            return []

    def remove_by_source(self, filename: str) -> int:
        try:
            snaps = list(self.col.where(filter=firestore.FieldFilter("source", "==", filename)).stream())
            for start in range(0, len(snaps), _BATCH):
                batch = self.client.batch()
                for snap in snaps[start:start + _BATCH]:
                    batch.delete(snap.reference)
                batch.commit()
            return len(snaps)
        except Exception as e:
            print(f"[RAG] Remove failed: {e}")
            return 0

    def chunk_count_by_filename(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        try:
            for snap in self.col.select(["source"]).stream():  # solo ese campo: no baja los vectores
                source = snap.to_dict().get("source")
                if source:
                    counts[source] = counts.get(source, 0) + 1
        except Exception as e:
            print(f"[RAG] Chunk count failed: {e}")
        return counts

    @property
    def count(self) -> int:
        try:
            return self.col.count().get()[0][0].value
        except Exception:
            return 0
