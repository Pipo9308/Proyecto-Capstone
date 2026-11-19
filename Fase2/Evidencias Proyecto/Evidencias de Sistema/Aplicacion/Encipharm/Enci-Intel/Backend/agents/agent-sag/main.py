import sys
import logging
from datetime import datetime, timezone

sys.path.insert(0, 'agents/agent-sag')

from db_session import get_db
from scraper import descargar_registros_sag
from detector import cargar_registros_previos, detectar_cambios, sincronizar_productos, generar_alertas, validar_descarga
from enriquecedor_sag import analizar, cargar_config
from app.llm_agentes import describir_ia

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("agente_sag")

def main():
    db = get_db()
    ts = datetime.now(timezone.utc)

    # Registrar inicio en agent_runs
    run_doc = {
        "agent_id":   "agente_sag",
        "status":     "running",
        "started_at": ts,
    }
    result = db.agent_runs.insert_one(run_doc)
    run_id = result.inserted_id

    # Actualizar estado en agents
    db.agents.update_one(
        {"_id": "agente_sag"},
        {"$set": {
            "status":      "running",
            "last_run":    ts,
            "name":        "Agente SAG",
            "description": "Monitoreo de registros SAG de productos",
        }},
        upsert=True
    )

    try:
        logger.info("Descargando registros SAG...")
        df = descargar_registros_sag(db)
        logger.info(f"Registros descargados: {len(df)}")

        logger.info("Cargando previos de Firestore...")
        previos = cargar_registros_previos(db)

        logger.info("Detectando cambios...")
        nuevos, cancelados = detectar_cambios(df, previos)
        validar_descarga(previos, cancelados)

        logger.info("Sincronizando productos...")
        sincronizar_productos(db, df, cancelados)

        analisis = None
        # Se carga siempre para dejar en el historial que modelo se usaria; solo se llama si hay cambios.
        cfg = cargar_config(db, "sag")
        ia = describir_ia(cfg)
        logger.info(f"IA configurada: {ia}")
        if cfg and (nuevos or cancelados):
            logger.info(f"Analizando {len(nuevos) + len(cancelados)} registros con {cfg['model']}...")
            analisis = analizar(db, df, nuevos, cancelados, previos, cfg)

        logger.info("Generando alertas...")
        total_alertas = generar_alertas(db, nuevos, cancelados, df, previos, analisis)

        # Registrar éxito
        db.agent_runs.update_one(
            {"_id": run_id},
            {"$set": {
                "status":          "success",
                "ended_at":        datetime.now(timezone.utc),
                "nuevos":          len(nuevos),
                "cancelados":      len(cancelados),
                "total_alertas":   total_alertas,
                "revisados":       len(df),
                "ia":              ia,
            }}
        )

        db.agents.update_one(
            {"_id": "agente_sag"},
            {"$set": {
                "status":      "active",
                "last_run":    ts,
                "last_result": {
                    "nuevos":        len(nuevos),
                    "cancelados":    len(cancelados),
                    "total_alertas": total_alertas,
                    "revisados":     len(df),
                    "ia":            ia,
                }
            }}
        )

        logger.info(f"Agente SAG completado: {len(nuevos)} nuevos, {len(cancelados)} cancelados, {total_alertas} alertas")

    except Exception as e:
        logger.error(f"Error en agente SAG: {e}")
        db.agent_runs.update_one({
            "_id": run_id
        }, {"$set": {
            "status":   "failure",
            "error":    str(e),
            "ended_at": datetime.now(timezone.utc),
        }})
        db.agents.update_one({
            "_id": "agente_sag"
        }, {"$set": {
            "status": "error",
            "last_error": str(e),
        }})
        raise

if __name__ == "__main__":
    main()