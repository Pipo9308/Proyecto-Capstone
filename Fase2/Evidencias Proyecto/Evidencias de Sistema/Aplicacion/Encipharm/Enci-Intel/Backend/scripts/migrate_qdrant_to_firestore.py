"""Copia los vectores del RAG de Qdrant a Firestore (coleccion RAG_COLLECTION), sin recalcular embeddings.

Es idempotente (el id del documento sale del id del fragmento, igual que VectorStore) y NO modifica Qdrant.
Dry-run por defecto; con --apply escribe. Requiere el indice vectorial (scripts/create_vector_index.py).

    pip install qdrant-client google-cloud-firestore
    QDRANT_URL=... QDRANT_API_KEY=... FIREBASE_PROJECT_ID=... GOOGLE_APPLICATION_CREDENTIALS=... \
      python scripts/migrate_qdrant_to_firestore.py [--apply]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QDRANT_COLLECTION = "enci_intel_docs"
BATCH = 100  # cada fragmento lleva 2048 floats: lotes chicos


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from qdrant_client import QdrantClient

    from app.rag.store import VectorStore

    qdrant = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ.get("QDRANT_API_KEY") or None)
    store = VectorStore()
    total = qdrant.count(QDRANT_COLLECTION).count
    print(f"Qdrant {QDRANT_COLLECTION}: {total} fragmentos")

    copied, offset, batch = 0, None, store.client.batch()
    while True:
        points, offset = qdrant.scroll(QDRANT_COLLECTION, limit=BATCH, offset=offset, with_vectors=True, with_payload=True)
        for point in points:
            payload = point.payload or {}
            doc_id = payload.get("id")
            if not doc_id:
                print(f"  omitido {point.id}: sin 'id' en el payload")
                continue
            if args.apply:
                from google.cloud.firestore_v1.vector import Vector
                batch.set(store.col.document(store._doc_id(doc_id)), {**payload, "embedding": Vector(point.vector)})
            copied += 1
        if args.apply and points:
            batch.commit()
            batch = store.client.batch()
        if offset is None:
            break
    print(f"{copied} fragmentos {'copiados a' if args.apply else 'se copiarian a'} Firestore ({store.col.id})")


if __name__ == "__main__":
    main()
