import logging
from datetime import datetime, timezone, timedelta
import pandas as pd

logger = logging.getLogger("agente_sag.detector")

# Umbrales: critical ≥80, high 60-79, medium 40-59, low <40
def _urgency_to_priority(urgency: int) -> str:
    if urgency >= 80:
        return "critical"
    if urgency >= 60:
        return "high"
    if urgency >= 40:
        return "medium"
    return "low"

_EXPIRY_DELTA = {
    "critical": timedelta(hours=24),
    "high":     timedelta(hours=72),
    "medium":   timedelta(days=7),
    "low":      timedelta(days=30),
}

def _expires_at(priority: str, created_at: datetime) -> datetime:
    return created_at + _EXPIRY_DELTA.get(priority, timedelta(days=30))

COL_REGISTRO = "Registro"
COL_NOMBRE   = "Nombre comercial"
COL_EMPRESA  = "Empresa Fabricante"
COL_IMPORTADOR = "Importador o Registrante"
COL_CLASIFICACION = "Clasificación"

COLECCION = "sag_productos"

# Categorias con mayor relevancia estrategica segun el Documento Funcional de
# Encipharm (#6.5, Motor de Alertas Estrategicas): "nueva aprobacion ISP en
# categorias estrategicas (antibioticos, vacunas)". En el dato real del SAG
# esas categorias aparecen como ANTIMICROBIANOS e INMUNOLOGICO.
CATEGORIAS_ESTRATEGICAS = {"ANTIMICROBIANOS", "INMUNOLOGICO"}
# Categoria con mas registros de competidores en el mercado (ver conteo real:
# ANTIPARASITARIO domina con ~25% de los registros de Zoetis/Drag Pharma/Agrovet).
CATEGORIA_ALTO_VOLUMEN = {"ANTIPARASITARIO"}


def _resolve_urgency(clasificacion: str | None, es_cancelacion: bool) -> int:
    """Urgencia diferenciada por categoria terapeutica, en vez del valor fijo
    (75 nuevo / 90 cancelacion) que no distinguia entre un antiparasitario
    cualquiera y un nuevo antibiotico o vacuna de un competidor."""
    categoria = (clasificacion or "").strip().upper()
    if categoria in CATEGORIAS_ESTRATEGICAS:
        return 90 if es_cancelacion else 80
    if categoria in CATEGORIA_ALTO_VOLUMEN:
        return 75 if es_cancelacion else 65
    return 65 if es_cancelacion else 55


BONO_SOLAPAMIENTO = 15


def _con_analisis(urgency: int, description: str, data: dict, extra: dict | None) -> tuple[int, str, dict]:
    """Suma lo que aporto el modelo (resumen y solapamiento con el catalogo de Enci); sin analisis no cambia nada."""
    if not extra:
        return urgency, description, data
    if extra.get("resumen"):
        description += f" | {extra['resumen']}"
    data = {**data, "resumen_ia": extra.get("resumen", ""), "solapa_con": extra.get("solapa_con", [])}
    if extra.get("solapa_con"):
        urgency = min(100, urgency + BONO_SOLAPAMIENTO)
    return urgency, description, data


def cargar_registros_previos(db) -> dict:
    docs = db[COLECCION].find()
    return {
        doc["_id"]: doc
        for doc in docs
        if doc.get("status") != "cancelado"
    }


def detectar_cambios(df_actual: pd.DataFrame, previos: dict) -> tuple[set, set]:
    actuales_ids = set(df_actual[COL_REGISTRO].astype(str).str.strip().tolist())
    previos_ids  = set(previos.keys())
    nuevos      = actuales_ids - previos_ids
    cancelados  = previos_ids - actuales_ids
    return nuevos, cancelados


# Si desaparece de golpe mas de esta fraccion del listado, la descarga se trata como rota y no como cancelaciones reales.
MAX_FRACCION_CANCELADOS = 0.2
MIN_CANCELADOS_SOSPECHOSOS = 10


def validar_descarga(previos: dict, cancelados: set) -> None:
    """Lanza si la descarga parece rota (SAG vacio, HTML cambiado o filtro de competidores sin coincidencias)."""
    if len(cancelados) > max(MIN_CANCELADOS_SOSPECHOSOS, len(previos) * MAX_FRACCION_CANCELADOS):
        raise RuntimeError(
            f"Descarga SAG sospechosa: desaparecieron {len(cancelados)} de {len(previos)} registros. "
            "No se guardó nada; revisar el sitio del SAG antes de volver a correr."
        )


def sincronizar_productos(db, df_actual: pd.DataFrame, cancelados: set):
    ts = datetime.now(timezone.utc)
    from app.firestore_db import UpdateOne
    ops = []

    for _, row in df_actual.iterrows():
        num = str(row[COL_REGISTRO]).strip()
        data = {**row.to_dict(), "updated_at": ts, "status": "activo"}
        ops.append(UpdateOne({"_id": num}, {"$set": data}, upsert=True))

    for reg_id in cancelados:
        data = {"status": "cancelado", "cancelled_at": ts}
        ops.append(UpdateOne({"_id": reg_id}, {"$set": data}, upsert=True))

    if ops:
        db[COLECCION].bulk_write(ops)
    logger.info(f"Sincronizados {len(df_actual)} productos, {len(cancelados)} marcados como cancelados")


def generar_alertas(db, nuevos: set, cancelados: set, df_actual: pd.DataFrame, previos: dict | None = None,
                    analisis: dict | None = None):
    ts  = datetime.now(timezone.utc)
    from app.firestore_db import UpdateOne
    ops = []
    total = 0

    for reg_id in nuevos:
        fila = df_actual[df_actual[COL_REGISTRO].astype(str).str.strip() == reg_id]
        if fila.empty:
            continue
        row = fila.iloc[0]
        clasificacion = row.get(COL_CLASIFICACION, "")
        description = (f"Competidor: {row.get(COL_IMPORTADOR, '')} | Fabricante: {row.get(COL_EMPRESA, '')}"
                       + (f" | Categoria: {clasificacion}" if clasificacion else ""))
        urgency, description, data = _con_analisis(
            _resolve_urgency(clasificacion, es_cancelacion=False), description, row.to_dict(), (analisis or {}).get(reg_id))
        priority = _urgency_to_priority(urgency)
        alert_id = f"sag_newsku_{reg_id}"
        doc = {
            "type":        "REGULATORY",
            "subtype":     "NEWSKU",
            "title":       f"Nuevo registro SAG: {row.get(COL_NOMBRE, reg_id)}",
            "description": description,
            "urgency":     urgency,
            "priority":    priority,
            "source":      "SAG",
            "agent_id":    "agente_sag",
            "data":        data,
            "status":      "active",
            "created_at":  ts,
            "expires_at":  _expires_at(priority, ts),
        }
        ops.append(UpdateOne({"_id": alert_id}, {"$set": doc}, upsert=True))
        total += 1

    for reg_id in cancelados:
        alert_id = f"sag_cancel_{reg_id}"

        # Marcar producto como cancelado para que no vuelva a detectarse
        db[COLECCION].update_one({"_id": reg_id}, {"$set": {"status": "cancelado", "cancelled_at": ts}}, upsert=True)

        # Solo crear alerta si no existe una activa
        existing = db.alerts.find_one({"_id": alert_id})
        if existing:
            exp = existing.get("expires_at")
            if exp and isinstance(exp, datetime) and exp.replace(tzinfo=timezone.utc) > ts:
                logger.info(f"Alerta {alert_id} ya existe y sigue activa, omitiendo")
                continue

        producto = (previos or {}).get(reg_id, {})
        nombre   = producto.get(COL_NOMBRE, "")
        empresa  = producto.get(COL_EMPRESA, "") or producto.get(COL_IMPORTADOR, "")
        clasificacion = producto.get(COL_CLASIFICACION, "")
        description = (f"El registro {reg_id} ({nombre}) ya no aparece en el listado oficial SAG" + (f" — {empresa}" if empresa else "")
                       + (f" | Categoria: {clasificacion}" if clasificacion else ""))
        data = {"registro": reg_id, "nombre": nombre, "empresa": empresa, **{k: v for k, v in producto.items() if k not in ("status", "cancelled_at", "updated_at", "_id")}}
        urgency, description, data = _con_analisis(
            _resolve_urgency(clasificacion, es_cancelacion=True), description, data, (analisis or {}).get(reg_id))
        priority = _urgency_to_priority(urgency)
        doc = {
            "type":        "REGULATORY",
            "subtype":     "CANCELACION",
            "title":       f"Cancelación SAG: {nombre or f'registro {reg_id}'}",
            "description": description,
            "urgency":     urgency,
            "priority":    priority,
            "source":      "SAG",
            "agent_id":    "agente_sag",
            "data":        data,
            "status":      "active",
            "created_at":  ts,
            "expires_at":  _expires_at(priority, ts),
        }
        ops.append(UpdateOne({"_id": alert_id}, {"$set": doc}, upsert=True))
        total += 1

    if ops:
        db.alerts.bulk_write(ops)

    logger.info(f"Alertas generadas: {total} ({len(nuevos)} nuevos, {len(cancelados)} cancelados)")
    return total
