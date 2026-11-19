"""Datos sinteticos de Intel (catalogo, market share, matriz de posicionamiento, importaciones), marcados [DEMO].

Aditivo: no borra lo existente. Los ids llevan prefijo ``demo-``; ``--borrar`` quita solo esos.
    python scripts/seed_demo_intel.py --apply
    python scripts/seed_demo_intel.py --borrar
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.firestore_db import create_async_database  # noqa: E402

R = random.Random(20261116)
D = "[DEMO] "

# nombre, categoria, especie, principios activos, precio lista CLP
PRODUCTOS = [
    ("Enci-Ivermec 1%", "Antiparasitario", "Bovino", "ivermectina", 38000),
    ("Enci-Doramec 1%", "Antiparasitario", "Bovino", "doramectina", 62000),
    ("Enci-Moxi 1%", "Antiparasitario", "Bovino", "moxidectina", 58000),
    ("Enci-Albendazol 10%", "Antiparasitario", "Bovino", "albendazol", 24000),
    ("Enci-Fenbenda 10%", "Antiparasitario", "Bovino, porcino", "fenbendazol", 21500),
    ("Enci-Tulatro 10%", "Antibiótico", "Bovino, porcino", "tulatromicina", 52000),
    ("Enci-Enrofloxacina 10%", "Antibiótico", "Ave, porcino", "enrofloxacina", 14500),
    ("Enci-Oxitetra LA 20%", "Antibiótico", "Bovino", "oxitetraciclina", 54000),
    ("Enci-Florfenicol 30%", "Antibiótico", "Bovino, porcino", "florfenicol", 31000),
    ("Enci-Ceftio 5%", "Antibiótico", "Bovino, porcino", "ceftiofur", 46000),
    ("Enci-Amoxi LA 15%", "Antibiótico", "Bovino, porcino", "amoxicilina", 17800),
    ("Enci-Tilosina 20%", "Antibiótico", "Bovino, porcino", "tilosina", 12800),
    ("Enci-Vitamina ADE", "Vitaminas", "Bovino, equino", "vitamina A; vitamina D3; vitamina E", 9800),
    ("Enci-Complejo B", "Vitaminas", "Bovino, equino, canino", "vitamina B1; vitamina B6; vitamina B12", 7600),
    ("Enci-Selenio E", "Vitaminas", "Bovino, ovino", "selenio; vitamina E", 8400),
    ("Enci-Meloxicam 2%", "Antiinflamatorio", "Bovino, porcino, canino", "meloxicam", 13900),
    ("Enci-Ketoprofeno 10%", "Antiinflamatorio", "Bovino, equino", "ketoprofeno", 11200),
    ("Enci-Oxitocina 10 UI", "Reproductivo", "Bovino, porcino", "oxitocina", 7400),
    ("Enci-Coccistop", "Antiparasitario", "Ave, porcino", "toltrazuril", 34000),
    ("Enci-Spot On Perros", "Antiparasitario", "Canino", "fipronil", 11500),
]

# id, nombre, participacion base Q1 (%), tendencia anual en puntos
EMPRESAS = [("encipharm", "Encipharm", 30.0, 1.4), ("zoetis", "Zoetis", 29.0, -1.0), ("drag_pharma", "Drag Pharma", 17.0, 0.6),
            ("agrovet", "Agrovet", 14.0, -0.2), ("elanco", "Elanco", 6.0, -0.4), ("bayer", "Bayer", 4.0, -0.4)]
PRECIO_PROMEDIO = {"encipharm": 18500, "zoetis": 24500, "drag_pharma": 21000, "agrovet": 19800, "elanco": 22800, "bayer": 25600}
DIAS_ISP = {"encipharm": 45, "zoetis": 70, "drag_pharma": 58, "agrovet": 62, "elanco": 66, "bayer": 74}


def market_share_docs():
    docs = []
    for q in (2, 3):
        shares = [(i, n, max(base + trend * (q - 1) / 4 + R.uniform(-0.4, 0.4), 1)) for i, n, base, trend in EMPRESAS]
        total = sum(s for *_, s in shares)
        docs.append({"_id": f"demo-ms-q{q}", "period": f"Q{q}-2026 [DEMO]", "total_market_usd": 4_200_000 + q * 150_000,
                     "competitors": [{"id": i, "name": n, "share_pct": round(s / total * 100, 1),
                                      "trend": "up" if (s / total * 100) > base else "down" if (s / total * 100) < base - 0.3 else "stable"}
                                     for (i, n, s), (_, _, base, _) in zip(shares, EMPRESAS)]})
    return docs


async def apply():
    db = create_async_database(os.environ.get("FIREBASE_PROJECT_ID"))
    now = datetime.now(timezone.utc)
    for n, (nombre, cat, especie, activos, precio) in enumerate(PRODUCTOS, start=1):
        await db.products.update_one({"_id": f"demo-prod-{n:02d}"}, {"$set": {
            "name": D + nombre, "nombre": D + nombre, "category": cat, "categoria": cat, "especie": especie,
            "principios_activos": activos, "price": precio, "stock": R.randint(40, 900), "titular": "Encipharm",
            "estado": "vigente", "demo": True, "updated_at": now}}, upsert=True)
    for doc in market_share_docs():
        _id = doc.pop("_id")
        await db.market_share.update_one({"_id": _id}, {"$set": {**doc, "demo": True, "last_updated": now}}, upsert=True)
    await db.positioning_matrix.update_one({"_id": "demo-pos"}, {"$set": {
        "axes": {"x": {"label": "Velocidad Regulatoria ISP [DEMO]", "unit": "dias promedio"},
                 "y": {"label": "Precio Promedio de Portafolio [DEMO]", "unit": "CLP"}},
        "points": [{"competitor_id": i, "name": n, "x": DIAS_ISP[i], "y": PRECIO_PROMEDIO[i], "size": round(base)}
                   for i, n, base, _ in EMPRESAS], "demo": True, "last_updated": now}}, upsert=True)
    meses = ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    series = []
    for i, n, base, trend in EMPRESAS[:4]:
        v = [int(base * 1500 * (1 + 0.06 * k) * R.uniform(0.9, 1.1)) for k in range(6)]
        series.append({"competitor_id": i, "competitor_name": n, "values_kg": v, "trend_pct": round((v[-1] / v[0] - 1) * 100, 1)})
    await db.import_trends.update_one({"_id": "demo-imp"}, {"$set": {"months": meses, "series": series,
                                                                      "source": "SAG_DIN [DEMO]", "demo": True, "last_updated": now}}, upsert=True)
    print(f"Listo: {len(PRODUCTOS)} productos, 2 trimestres de market share, matriz de {len(EMPRESAS)} empresas, tendencia de importaciones.")


async def borrar():
    db = create_async_database(os.environ.get("FIREBASE_PROJECT_ID"))
    for col in (db.products, db.market_share, db.positioning_matrix, db.import_trends):
        r = await col.delete_many({"demo": True})
        print(getattr(r, "deleted_count", r))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--borrar", action="store_true")
    a = p.parse_args()
    asyncio.run(borrar() if a.borrar else apply() if a.apply else print("Dry-run: usa --apply o --borrar"))
