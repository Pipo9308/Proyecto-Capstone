import sys
import logging
import argparse
from datetime import datetime, timezone

sys.path.insert(0, "agents/agent-competidores")

from db_session import get_db
from enriquecedor import cargar_config, enriquecer
from app.llm_agentes import describir_ia
from scraper import scrape_todas
from detector import (
    cargar_noticias_previas,
    detectar_noticias_nuevas,
    sincronizar_noticias,
    generar_alertas,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("agente_competidores")


def main(dry_run: bool = False, populate_only: bool = False, force_alerts: bool = False):
    ts = datetime.now(timezone.utc)

    if dry_run:
        logger.info("=== MODO DRY-RUN: solo scraping, sin Firestore ===")
        noticias = scrape_todas()
        print(f"\n========== NOTICIAS ({len(noticias)}) ==========")
        for n in noticias:
            print(f"  [{n['fecha']}] {n['titulo']}")
            print(f"           {n['url']}")
        return

    db = get_db()

    run_doc = {
        "agent_id":   "agente_competidores",
        "status":     "running",
        "started_at": ts,
    }
    result = db.agent_runs.insert_one(run_doc)
    run_id = result.inserted_id

    db.agents.update_one(
        {"_id": "agente_competidores"},
        {"$set": {
            "status":      "running",
            "last_run":    ts,
            "name":        "Agente Competidores",
            "description": "Monitoreo de noticias de Drag Pharma, Zoetis y Agrovet",
        }},
        upsert=True
    )

    try:
        logger.info("Scrapeando noticias (Drag Pharma, Zoetis, Agrovet)...")
        avisos: list[str] = []  # fuentes que no respondieron: la corrida queda "parcial"
        noticias = scrape_todas(avisos)
        logger.info(f"  {len(noticias)} noticias encontradas")
        for aviso in avisos:
            logger.warning(f"Corrida parcial: {aviso}")

        if force_alerts:
            logger.info("=== MODO FORCE-ALERTS: tratando todo como nuevo ===")
            previas = {}
        else:
            previas = cargar_noticias_previas(db)

        nuevas = detectar_noticias_nuevas(noticias, previas)
        logger.info(f"  {len(nuevas)} noticias nuevas")

        # Se carga siempre para dejar en el historial que modelo se usaria; solo se llama si hay noticias nuevas.
        cfg = cargar_config(db, "competidores")
        ia = describir_ia(cfg)
        logger.info(f"IA configurada: {ia}")
        if cfg and nuevas:
            logger.info(f"Enriqueciendo {len(nuevas)} noticias con {cfg['model']}...")
            enriquecer(nuevas, cfg)  # modifica los mismos dicts que van a sincronizarse

        sincronizar_noticias(db, noticias)

        total_alertas = 0
        if not populate_only:
            relevantes = [n for n in nuevas if n.get("relevante", True)]
            logger.info(f"  {len(nuevas) - len(relevantes)} descartadas por no ser relevantes")
            total_alertas = generar_alertas(db, relevantes)
        else:
            logger.info("Populate-only: omitiendo generación de alertas")

        db.agent_runs.update_one(
            {"_id": run_id},
            {"$set": {
                "status":        "success",
                "ended_at":      datetime.now(timezone.utc),
                "nuevos":        len(nuevas),
                "total_alertas": total_alertas,
                "revisados":     len(noticias),
                "ia":            ia,
                "avisos":        avisos,
            }}
        )
        db.agents.update_one(
            {"_id": "agente_competidores"},
            {"$set": {
                "status": "active",
                "last_result": {"nuevos": len(nuevas), "total_alertas": total_alertas,
                                "revisados": len(noticias), "ia": ia, "avisos": avisos},
            }}
        )

        logger.info(f"Agente completado: {len(nuevas)} noticias nuevas, {total_alertas} alertas")

    except Exception as e:
        logger.error(f"Error en agente competidores: {e}")
        db.agent_runs.update_one({"_id": run_id}, {"$set": {"status": "failure", "error": str(e), "ended_at": datetime.now(timezone.utc)}})
        db.agents.update_one({"_id": "agente_competidores"}, {"$set": {"status": "error", "last_error": str(e)}})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",       action="store_true")
    parser.add_argument("--populate-only", action="store_true")
    parser.add_argument("--force-alerts",  action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run, populate_only=args.populate_only, force_alerts=args.force_alerts)