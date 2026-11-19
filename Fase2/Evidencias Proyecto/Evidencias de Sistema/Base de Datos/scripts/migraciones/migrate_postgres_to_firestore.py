"""Copia los datos de Ventas de PostgreSQL (Supabase) a Cloud Firestore, pasando por la misma capa de datos que usa
la aplicacion (asi tambien quedan creados los documentos guardia de unicidad: RUT, correo, etc.).

Es idempotente: un registro cuyo id ya existe en Firestore se omite. NO modifica ni borra nada en Postgres.
Dry-run por defecto (solo cuenta); con --apply escribe. Un registro que viole una regla de unicidad se informa y se
omite, no detiene la copia.

    pip install psycopg2-binary google-cloud-firestore      # solo para este script
    POSTGRES_URL=postgresql://... FIREBASE_PROJECT_ID=... \
      [FIREBASE_CREDENTIALS_JSON=... | GOOGLE_APPLICATION_CREDENTIALS=... | FIRESTORE_EMULATOR_HOST=localhost:8085] \
      python scripts/migrate_postgres_to_firestore.py [--apply] [--tables users,clientes]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Orden: primero lo que otros registros referencian (no hay claves foraneas, pero asi un corte a medias queda coherente).
ORDER = [
    "users", "clientes", "oportunidades", "interacciones", "propuestas", "propuesta_archivos", "account_tokens",
    "productos_encipharm", "productos_competencia", "equivalencias_producto", "precios_competencia",
    "eventos", "notificaciones", "intel_lecturas", "competencia_conversaciones", "competencia_uso",
    "rag_documentos", "rag_conversaciones", "rag_chunks", "audit_logs",
]


def row_to_kwargs(model, row: dict) -> dict:
    kwargs = {k: v for k, v in row.items() if k in model.__fields__}
    emb = kwargs.get("embedding")
    if isinstance(emb, str):  # pgvector llega como texto "[0.1,0.2,...]"
        kwargs["embedding"] = json.loads(emb)
    if model.__tablename__ == "equivalencias_producto":
        kwargs["id"] = f"{row['productoCompetenciaId']}:{row['productoEncipharmId']}"
    return kwargs


def migrate(pg_conn, session, tables: list[str], apply: bool) -> dict[str, dict[str, int]]:
    from app.core.odm import Document, IntegrityError
    import app.models_sql  # noqa: F401  (registra los modelos)

    models = {m.__tablename__: m for m in Document.__subclasses__()}
    summary = {}
    for table in tables:
        model = models.get(table)
        if model is None:
            print(f"{table}: sin modelo en Ventas, se omite")
            continue
        cur = pg_conn.cursor()
        cur.execute(f'SELECT * FROM "{table}"')
        columns = [c[0] for c in cur.description]
        stats = {"copiados": 0, "existentes": 0, "omitidos": 0}
        for values in cur:
            row = dict(zip(columns, values))
            kwargs = row_to_kwargs(model, row)
            pk = kwargs.get(model.__pk__)
            if session.get(model, pk) is not None:
                stats["existentes"] += 1
                continue
            if apply:
                session.add(model(**kwargs))
                try:
                    session.commit()
                except IntegrityError as error:
                    session.rollback()
                    stats["omitidos"] += 1
                    print(f"  omitido {table}/{pk}: {error}")
                    continue
            stats["copiados"] += 1
        summary[table] = stats
        print(f"{table}: {stats['copiados']} {'copiados' if apply else 'por copiar (dry-run)'}, "
              f"{stats['existentes']} ya estaban, {stats['omitidos']} omitidos")
    return summary


def wipe(session, tables: list[str], whole: bool) -> None:
    """Vacia las colecciones de Ventas elegidas. Las guardias de unicidad se vacian solo si se copian TODAS las tablas."""
    from app.core.odm import _UNIQUE, Document
    import app.models_sql  # noqa: F401

    models = {m.__tablename__: m for m in Document.__subclasses__()}
    names = [models[t].collection_name() for t in tables if t in models] + ([_UNIQUE] if whole else [])
    for name in names:
        removed = 0
        for snap in session.client.collection(name).stream():
            snap.reference.delete()
            removed += 1
        print(f"  vaciada {name}: {removed} documentos")
    session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tables", help="lista separada por comas; por defecto, todas")
    parser.add_argument(
        "--replace", action="store_true",
        help="antes de copiar, BORRA en Firestore las colecciones ventas_* de las tablas elegidas (y las guardias de unicidad): "
             "para repetir la copia completa desde cero en la ventana de corte. Solo con --apply.",
    )
    args = parser.parse_args()
    import psycopg2

    from app.core.odm import new_session

    pg = psycopg2.connect(os.environ["POSTGRES_URL"])
    pg.set_session(readonly=True)  # esta herramienta nunca escribe en Postgres
    tables = args.tables.split(",") if args.tables else ORDER
    session = new_session()
    if args.replace and args.apply:
        wipe(session, tables, whole=args.tables is None)
    migrate(pg, session, tables, args.apply)


if __name__ == "__main__":
    main()
