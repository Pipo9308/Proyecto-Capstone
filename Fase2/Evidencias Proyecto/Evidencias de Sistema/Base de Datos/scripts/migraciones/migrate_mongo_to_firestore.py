"""Copia las colecciones de Enci-Intel de MongoDB a Firestore (Fase 5 de la migracion).

Es idempotente (cada documento se escribe con su _id, asi que repetirlo no duplica) y NO borra nada en Mongo.
Por defecto es un dry-run: cuenta lo que copiaria. Con --apply escribe.

    pip install pymongo google-cloud-firestore
    MONGODB_URL=mongodb://localhost:27017 FIREBASE_PROJECT_ID=mi-proyecto \
      [FIREBASE_CREDENTIALS_PATH=firebase-credentials.json | FIRESTORE_EMULATOR_HOST=localhost:8085] \
      python scripts/migrate_mongo_to_firestore.py [--apply] [--collections users,alerts]

Conversion: ObjectId -> str (tambien dentro de documentos), Decimal128 -> float, fechas ingenuas -> UTC.
Los _id con "/" no son validos como id en Firestore: se reportan y se omiten.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.firestore_db import create_async_database  # noqa: E402

BATCH = 400


def convert(value):
    """Tipos BSON -> tipos que Firestore acepta."""
    name = type(value).__name__
    if name == "ObjectId":
        return str(value)
    if name == "Decimal128":
        return float(value.to_decimal())
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, dict):
        return {str(k): convert(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [convert(v) for v in value]
    return value


async def migrate(mongo_db, fs_db, names: list[str] | None, apply: bool) -> dict[str, tuple[int, int]]:
    summary = {}
    for name in names or sorted(mongo_db.list_collection_names()):
        copied = skipped = 0
        batch, in_batch = fs_db.client.batch(), 0
        for doc in mongo_db[name].find():
            doc_id = str(doc.pop("_id"))
            if "/" in doc_id or not doc_id:
                skipped += 1
                print(f"  omitido {name}/{doc_id!r}: id invalido en Firestore")
                continue
            if apply:
                batch.set(fs_db[name]._col.document(doc_id), convert(doc))
                in_batch += 1
                if in_batch >= BATCH:
                    await batch.commit()
                    batch, in_batch = fs_db.client.batch(), 0
            copied += 1
        if apply and in_batch:
            await batch.commit()
        summary[name] = (copied, skipped)
        print(f"{name}: {copied} documentos{' copiados' if apply else ' (dry-run)'}, {skipped} omitidos")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--collections", help="lista separada por comas; por defecto, todas")
    args = parser.parse_args()
    from pymongo import MongoClient

    mongo = MongoClient(os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
    if os.environ.get("FIREBASE_CREDENTIALS_PATH"):
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", os.environ["FIREBASE_CREDENTIALS_PATH"])
    fs = create_async_database(os.environ.get("FIREBASE_PROJECT_ID"))
    names = args.collections.split(",") if args.collections else None
    asyncio.run(migrate(mongo.enci_intel, fs, names, args.apply))


if __name__ == "__main__":
    main()
