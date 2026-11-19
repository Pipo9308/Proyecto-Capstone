from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from app.core.odm import Session

from app.core.auth import require_intel_access
from app.core.db import get_db
from app.services.competencia_productos import ficha_competencia
from app.services.enci_intel import EnciIntelService
from app.services.intel_lecturas import mark_alert_read, read_alert_ids

router = APIRouter(prefix="/inteligencia", tags=["Inteligencia"], dependencies=[Depends(require_intel_access)])

# Los ids viajan dentro de la URL hacia Enci-Intel: solo caracteres de id (sin "/", "..", etc.).
ALERT_ID = Path(max_length=120, pattern=r"^[A-Za-z0-9_.:\-]+$")
REGISTRO = Path(max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")

# Cantidad de alertas recientes sobre las que se calcula el contador de no leidas.
UNREAD_WINDOW = 200


class ChatQuery(BaseModel):
    pregunta: str


@router.get("/noticias")
async def get_noticias():
    service = EnciIntelService()
    return await service.get_noticias()


@router.get("/competencia")
async def get_competencia():
    service = EnciIntelService()
    return await service.get_competencia()


@router.post("/chat")
async def chat(query: ChatQuery):
    service = EnciIntelService()
    return await service.chat_query(query.pregunta)


# ── Alertas de competencia (RQ-09) ───────────────────────────────────────────

@router.get("/alertas")
async def get_alertas(
    priority: str | None = Query(None, max_length=20),
    type: str | None = Query(None, max_length=40),
    competitor: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_intel_access),
    db: Session = Depends(get_db),
):
    """Feed de alertas de Enci-Intel con filtros, paginacion y estado de lectura del usuario."""
    result = await EnciIntelService().get_alertas(
        priority=priority, type=type, competitor=competitor, limit=limit, offset=offset
    )
    alerts = result.get("data", [])
    read = read_alert_ids(db, user["uid"], [a["id"] for a in alerts])
    for alert in alerts:
        alert["leida"] = alert["id"] in read
    return result


# Debe declararse antes de /alertas/{alert_id} para que "no-leidas" no se tome como un id.
@router.get("/alertas/no-leidas")
async def count_unread(user: dict = Depends(require_intel_access), db: Session = Depends(get_db)):
    """Alertas sin leer entre las UNREAD_WINDOW mas recientes."""
    result = await EnciIntelService().get_alertas(limit=UNREAD_WINDOW)
    ids = [a["id"] for a in result.get("data", [])]
    read = read_alert_ids(db, user["uid"], ids)
    return {"no_leidas": len([i for i in ids if i not in read])}


@router.get("/alertas/{alert_id}")
async def get_alerta(
    alert_id: str = ALERT_ID,
    user: dict = Depends(require_intel_access),
    db: Session = Depends(get_db),
):
    result = await EnciIntelService().get_alerta(alert_id)
    alert = result["data"]
    alert["leida"] = alert["id"] in read_alert_ids(db, user["uid"], [alert["id"]])
    return result


@router.patch("/alertas/{alert_id}/leida")
async def mark_read(
    alert_id: str = ALERT_ID,
    user: dict = Depends(require_intel_access),
    db: Session = Depends(get_db),
):
    # Se confirma que la alerta existe en Intel para no guardar ids arbitrarios.
    await EnciIntelService().get_alerta(alert_id)
    mark_alert_read(db, user["uid"], alert_id)
    return {"alertId": alert_id, "leida": True}


# ── Productos del registro SAG (RQ-09) ───────────────────────────────────────

@router.get("/productos")
async def search_productos(
    q: str = Query("", max_length=100),
    estado: str | None = Query(None, pattern="^(activo|cancelado)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Busca por nombre comercial, principio activo, titular o numero de registro."""
    return await EnciIntelService().search_productos(q=q, estado=estado, limit=limit, offset=offset)


@router.get("/productos/{registro}/ficha")
async def get_ficha(registro: str = REGISTRO, db: Session = Depends(get_db)):
    """Ficha de un producto: registro SAG y alertas relacionadas, con el origen de cada dato.

    `precios` y `equivalente_encipharm` salen de la base de competencia (RQ-04): solo precios
    aprobados de productos cuyo registro SAG coincide.
    """
    result = await EnciIntelService().get_producto(registro)
    producto = result["data"]
    competencia = ficha_competencia(db, registro)
    return {
        "success": True,
        "data": {
            **producto,
            **competencia,
            "fuentes": [
                {"dato": "registro_sag", "origen": "SAG (Enci-Intel)", "fecha": producto.get("actualizado")},
                {"dato": "alertas", "origen": "Enci-Intel", "fecha": None},
                {"dato": "precios", "origen": "Reportes de vendedores (Encipharm)", "fecha": max((p["fecha"] for p in competencia["precios"]), default=None)},
            ],
        },
    }
