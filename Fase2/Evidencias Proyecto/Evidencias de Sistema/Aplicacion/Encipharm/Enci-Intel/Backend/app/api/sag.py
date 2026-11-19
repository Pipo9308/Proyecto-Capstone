"""Registro SAG de productos veterinarios (coleccion sag_productos, poblada por agent-sag).

Reemplaza las respuestas inventadas de /products para la ficha de competidor/producto
(RQ-09). Acepta JWT de usuario o la API key de servicio (proxy de Enci-Ventas).
"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_user_or_service
from app.db import get_db

router = APIRouter()

# Columnas del Excel del SAG que el agente guarda tal cual en cada documento.
CAMPO_REGISTRO = "Registro"
CAMPO_NOMBRE = "Nombre comercial"
CAMPO_GENERICO = "Nombre Genérico"
CAMPO_IMPORTADOR = "Importador o Registrante"
CAMPO_FABRICANTE = "Empresa Fabricante"
CAMPO_CLASIFICACION = "Clasificación"

# Campos donde busca `q`: nombre comercial, principio activo (nombre generico),
# titular (importador/fabricante) y numero de registro.
CAMPOS_BUSQUEDA = (CAMPO_NOMBRE, CAMPO_GENERICO, CAMPO_IMPORTADOR, CAMPO_FABRICANTE, CAMPO_REGISTRO)

_INTERNOS = {"_id", "updated_at", "cancelled_at", "status"}


def _resumen(doc: dict) -> dict:
    return {
        "registro": str(doc["_id"]),
        "nombre_comercial": doc.get(CAMPO_NOMBRE),
        "principio_activo": doc.get(CAMPO_GENERICO),
        "titular": doc.get(CAMPO_IMPORTADOR),
        "fabricante": doc.get(CAMPO_FABRICANTE),
        "clasificacion": doc.get(CAMPO_CLASIFICACION),
        "estado": doc.get("status", "activo"),
        "actualizado": _iso(doc.get("updated_at")),
    }


def _iso(value):
    """Fechas de Mongo sin zona = UTC: se devuelven con offset explicito."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return value


@router.get("/productos")
async def search_productos(
    q: str = Query("", max_length=100),
    estado: str | None = Query(None, pattern="^(activo|cancelado)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_user_or_service),
):
    """Busca por nombre comercial, principio activo, titular o numero de registro."""
    query: dict = {}
    text = q.strip()
    if text:
        pattern = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{campo: pattern} for campo in CAMPOS_BUSQUEDA] + [{"_id": text}]
    if estado:
        query["status"] = estado

    db = get_db()
    total = await db.sag_productos.count_documents(query)
    docs = await db.sag_productos.find(query).sort(CAMPO_NOMBRE, 1).skip(offset).limit(limit).to_list(length=limit)
    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(docs) < total,
        "data": [_resumen(d) for d in docs],
    }


@router.get("/productos/{registro}")
async def get_producto(registro: str, _: dict = Depends(require_user_or_service)):
    """Ficha completa del registro SAG, con las alertas generadas para ese producto."""
    db = get_db()
    doc = await db.sag_productos.find_one({"_id": registro})
    if not doc:
        raise HTTPException(status_code=404, detail="Registro SAG no encontrado")

    alertas = []
    for alert_id in (f"sag_newsku_{registro}", f"sag_cancel_{registro}"):
        alert = await db.alerts.find_one({"_id": alert_id})
        if alert:
            alertas.append({
                "id": str(alert["_id"]),
                "titulo": alert.get("title"),
                "tipo": alert.get("subtype"),
                "prioridad": alert.get("priority"),
                "creada": _iso(alert.get("created_at")),
            })

    detalle = {k: v for k, v in doc.items() if k not in _INTERNOS}
    return {"success": True, "data": {**_resumen(doc), "registro_sag": detalle, "alertas": alertas}}
