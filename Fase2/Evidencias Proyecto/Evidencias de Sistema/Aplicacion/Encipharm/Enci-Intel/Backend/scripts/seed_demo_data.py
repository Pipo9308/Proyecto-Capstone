"""Seed sample market-intelligence data for local development/demos.

The scraping agents (agent-sag, agent-competidores) are what's supposed to
populate these MongoDB collections in a real environment. Locally they take
time to run (and agent-competidores only covers one site today), so this
script writes a small, fixed set of documents directly, matching the shapes
`app/api/market.py` and `app/api/products.py` read from Mongo. Without this
(or the agents actually running), those endpoints return empty data and the
CRM's Inteligencia/Analisis de Competencia tabs look blank.

Solo para desarrollo local. Requiere --apply para escribir (por defecto solo
imprime que haria un dry-run), igual que scripts/seed_max_wellq_demo.py en
Enci-Ventas.

Run from Backend with:
    python scripts/seed_demo_data.py --apply
or inside the docker container:
    docker exec enci_backend python scripts/seed_demo_data.py --apply
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.firestore_db import create_async_database  # noqa: E402


MARKET_SHARE = {
    "period": "Q1-2026",
    "total_market_usd": 4200000,
    "competitors": [
        {"id": "encipharm", "name": "Encipharm", "share_pct": 34.0, "trend": "up"},
        {"id": "zoetis", "name": "Zoetis", "share_pct": 28.0, "trend": "down"},
        {"id": "drag_pharma", "name": "Drag Pharma", "share_pct": 21.0, "trend": "up"},
        {"id": "agrovet", "name": "Agrovet", "share_pct": 17.0, "trend": "stable"},
    ],
}

POSITIONING_MATRIX = {
    "axes": {
        "x": {"label": "Velocidad Regulatoria ISP", "unit": "dias promedio"},
        "y": {"label": "Precio Promedio de Portafolio", "unit": "CLP"},
    },
    "points": [
        {"competitor_id": "encipharm", "name": "Encipharm", "x": 45, "y": 18500, "size": 34},
        {"competitor_id": "zoetis", "name": "Zoetis", "x": 70, "y": 24500, "size": 28},
        {"competitor_id": "drag_pharma", "name": "Drag Pharma", "x": 58, "y": 21000, "size": 21},
        {"competitor_id": "agrovet", "name": "Agrovet", "x": 62, "y": 19800, "size": 17},
    ],
}

IMPORT_TRENDS = {
    "months": ["2026-01", "2026-02", "2026-03"],
    "series": [
        {"competitor_id": "encipharm", "competitor_name": "Encipharm", "values_kg": [42000, 55000, 61000], "trend_pct": 18.5},
        {"competitor_id": "zoetis", "competitor_name": "Zoetis", "values_kg": [32000, 38000, 44000], "trend_pct": 10.2},
    ],
    "source": "SAG_DIN",
}

PRODUCTS = [
    {"nombre": "Oxivet 200 LA", "titular": "Encipharm", "especie": "Bovino", "estado": "vigente"},
    {"nombre": "Ivermectina Plus", "titular": "Encipharm", "especie": "Ovino", "estado": "vigente"},
]


async def seed(apply: bool):
    if not apply:
        print("Dry-run (nada escrito). Vuelve a correr con --apply para sembrar los datos.")
        return

    db = create_async_database(os.environ.get("FIREBASE_PROJECT_ID"))
    now = datetime.now(timezone.utc)

    await db.market_share.delete_many({})
    await db.market_share.insert_one({**MARKET_SHARE, "last_updated": now})

    await db.positioning_matrix.delete_many({})
    await db.positioning_matrix.insert_one({**POSITIONING_MATRIX, "last_updated": now})

    await db.import_trends.delete_many({})
    await db.import_trends.insert_one({**IMPORT_TRENDS, "last_updated": now})

    await db.products.delete_many({})
    await db.products.insert_many([{**p, "updated_at": now} for p in PRODUCTS])

    print("Seed aplicado: market_share, positioning_matrix, import_trends, products.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(seed(args.apply))
