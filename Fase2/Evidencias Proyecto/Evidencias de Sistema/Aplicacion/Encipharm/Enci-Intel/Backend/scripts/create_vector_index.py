"""Crea el indice vectorial de Firestore que necesita el RAG (una vez por coleccion y proyecto).

    FIREBASE_PROJECT_ID=... FIREBASE_CREDENTIALS_PATH=... python scripts/create_vector_index.py [coleccion] [dimension]

Requiere que la cuenta de servicio tenga el rol "Administrador de indices de Cloud Datastore". El indice tarda
unos minutos en quedar listo; mientras tanto la busqueda vectorial falla. Es idempotente: si ya existe, lo dice.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import firestore_admin_v1 as fa

    from app.rag.store import COLLECTION_NAME, EMBEDDING_SIZE

    collection = sys.argv[1] if len(sys.argv) > 1 else COLLECTION_NAME
    dimension = int(sys.argv[2]) if len(sys.argv) > 2 else EMBEDDING_SIZE
    if os.getenv("FIREBASE_CREDENTIALS_PATH"):
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", os.environ["FIREBASE_CREDENTIALS_PATH"])
    parent = f"projects/{os.environ['FIREBASE_PROJECT_ID']}/databases/(default)/collectionGroups/{collection}"
    vector = fa.Index.IndexField.VectorConfig
    index = fa.Index(
        query_scope=fa.Index.QueryScope.COLLECTION,
        fields=[fa.Index.IndexField(field_path="embedding", vector_config=vector(dimension=dimension, flat=vector.FlatIndex()))],
    )
    try:
        fa.FirestoreAdminClient().create_index(request={"parent": parent, "index": index})
        print(f"Indice vectorial pedido para {collection} ({dimension} dim). Tarda unos minutos en quedar listo.")
    except AlreadyExists:
        print(f"El indice vectorial de {collection} ya existe.")


if __name__ == "__main__":
    main()
