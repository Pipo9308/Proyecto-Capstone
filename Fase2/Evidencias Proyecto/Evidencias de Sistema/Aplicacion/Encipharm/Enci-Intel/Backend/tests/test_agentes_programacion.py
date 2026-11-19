"""Agentes: guarda de cordura del SAG, preparacion al arrancar, disparo con API key de servicio y API key de IA cifrada."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1] / "agents" / "agent-sag"
sys.path.insert(0, str(AGENT_DIR))

from detector import validar_descarga  # noqa: E402

from app import llm_settings, scheduler  # noqa: E402


# ── Guarda de cordura del SAG ────────────────────────────────────────────────

def _previos(n):
    return {str(i): {} for i in range(n)}


def test_una_descarga_vacia_no_cancela_todo_el_listado():
    with pytest.raises(RuntimeError, match="sospechosa"):
        validar_descarga(_previos(404), cancelados=set(_previos(404)))


def test_unas_pocas_cancelaciones_reales_pasan():
    validar_descarga(_previos(404), cancelados={"1", "2", "3"})


def test_la_primera_corrida_sin_previos_pasa():
    validar_descarga({}, cancelados=set())


def test_un_listado_chico_tolera_hasta_el_minimo():
    validar_descarga(_previos(20), cancelados=set(list(_previos(20))[:10]))


# ── Preparacion de agentes al arrancar ───────────────────────────────────────

@pytest.fixture
def sin_jobs():
    yield
    for job in scheduler.scheduler.get_jobs():
        job.remove()


async def test_preparar_crea_agentes_cierra_huerfanas_y_programa(fake_db, sin_jobs):
    viejo = datetime.now(timezone.utc) - timedelta(hours=5)
    reciente = datetime.now(timezone.utc) - timedelta(minutes=5)
    await fake_db.agents.insert_one({"_id": "agente_competidores", "name": "Agente Competidores"})  # sin horario
    await fake_db.agent_runs.insert_one({"_id": "r1", "agent_id": "agente_sag", "status": "running", "started_at": viejo})
    await fake_db.agent_runs.insert_one({"_id": "r2", "agent_id": "agente_sag", "status": "running", "started_at": reciente})

    await scheduler.preparar_agentes(fake_db)

    agentes = {a["_id"]: a for a in fake_db.agents.docs}
    assert agentes["agente_sag"]["schedule"] == scheduler.AGENTES_POR_DEFECTO["agente_sag"]["schedule"]
    assert agentes["agente_sag"]["enabled"] is True
    assert agentes["agente_competidores"]["schedule"] == scheduler.AGENTES_POR_DEFECTO["agente_competidores"]["schedule"]
    estados = {r["_id"]: r["status"] for r in fake_db.agent_runs.docs}
    assert estados == {"r1": "failure", "r2": "running"}
    assert {j.id for j in scheduler.scheduler.get_jobs()} == {"job_agente_sag", "job_agente_competidores"}


async def test_preparar_respeta_un_agente_deshabilitado(fake_db, sin_jobs):
    await fake_db.agents.insert_one({"_id": "agente_sag", "schedule": "0 3 * * *", "enabled": False})

    await scheduler.preparar_agentes(fake_db)

    assert scheduler.scheduler.get_job("job_agente_sag") is None
    assert next(a for a in fake_db.agents.docs if a["_id"] == "agente_sag")["schedule"] == "0 3 * * *"


async def test_los_horarios_corren_en_hora_de_chile_y_los_antiguos_en_utc_se_convierten(fake_db, sin_jobs):
    await fake_db.agents.insert_one({"_id": "agente_sag", "schedule": "0 11 * * *", "enabled": True})  # 8:00 Chile en UTC

    await scheduler.preparar_agentes(fake_db)

    assert next(a for a in fake_db.agents.docs if a["_id"] == "agente_sag")["schedule"] == "0 8 * * *"
    trigger = scheduler.scheduler.get_job("job_agente_sag").trigger
    assert str(trigger.timezone) == "America/Santiago"
    # 8:00 de Chile en un dia de verano (UTC-3) son las 11:00 UTC
    desde = datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert trigger.get_next_fire_time(None, desde).astimezone(timezone.utc).hour == 11


def test_no_lanza_una_segunda_corrida_mientras_la_primera_sigue(monkeypatch):
    lanzados = []

    class Proceso:
        def poll(self):
            return None  # sigue corriendo

    monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *a, **kw: lanzados.append(kw["cwd"]) or Proceso())
    monkeypatch.setattr(scheduler, "_procesos", {})

    assert scheduler.run_agent_subprocess("agente_sag") and scheduler.run_agent_subprocess("agente_sag")
    assert lanzados == [scheduler.BACKEND_DIR]


# ── Disparo externo con la API key de servicio ───────────────────────────────

@pytest.fixture
def disparo(monkeypatch, fake_db):
    import app.api.agents as agents_api

    lanzados = []
    monkeypatch.setattr(agents_api, "check_and_increment", lambda *a, **kw: True)
    monkeypatch.setattr(agents_api, "run_agent_subprocess", lambda agent_id: lanzados.append(agent_id) or True)
    fake_db.agents.docs.append({"_id": "agente_sag", "enabled": True, "status": "active"})
    return lanzados


def test_el_disparador_externo_corre_un_agente_con_la_key_de_servicio(client, service_headers, disparo):
    assert client.post("/api/v1/agents/agente_sag/run", headers=service_headers).status_code == 200
    assert disparo == ["agente_sag"]


def test_ejecutar_borra_la_cache_y_no_se_cachea_mientras_el_agente_corre(client, service_headers, admin_headers, disparo,
                                                                         monkeypatch):
    import app.api.agents as agents_api

    borradas, guardadas = [], []
    monkeypatch.setattr(agents_api._cache, "invalidate", borradas.append)
    monkeypatch.setattr(agents_api._cache, "get", lambda key: None)
    monkeypatch.setattr(agents_api._cache, "set", lambda key, val, ttl=0: guardadas.append(key))

    client.post("/api/v1/agents/agente_sag/run", headers=service_headers)
    assert set(borradas) == {"agents", "agent_runs:agente_sag:10"}

    monkeypatch.setattr(agents_api, "corriendo", lambda agent_id: True)  # lanzado, sin corrida escrita aun
    assert client.get("/api/v1/agents/agente_sag/runs", headers=admin_headers).status_code == 200
    assert guardadas == []

    monkeypatch.setattr(agents_api, "corriendo", lambda agent_id: False)
    assert client.get("/api/v1/agents/agente_sag/runs", headers=admin_headers).status_code == 200
    assert guardadas == ["agent_runs:agente_sag:10"]


def test_un_usuario_comun_no_puede_correr_agentes(client, user_headers, disparo):
    assert client.post("/api/v1/agents/agente_sag/run", headers=user_headers).status_code == 403
    assert client.post("/api/v1/agents/agente_sag/run", headers={"X-API-Key": "mala"}).status_code == 401
    assert disparo == []


# ── API key de IA cifrada en Firestore ───────────────────────────────────────

@pytest.fixture
def llm_limpio(monkeypatch):
    monkeypatch.setattr(llm_settings, "_saved", {})


async def test_la_api_key_se_guarda_cifrada_y_se_lee_en_claro(fake_db, llm_limpio):
    await llm_settings.save({"api_key": "AIza-secreta-1234", "model": "gemini"}, "admin@test.com", datetime.now())

    guardada = fake_db.app_settings.docs[0]["api_key"]
    assert guardada.startswith("enc:") and "AIza" not in guardada
    assert llm_settings.effective()["api_key"] == "AIza-secreta-1234"
    await llm_settings.load()
    assert llm_settings.effective()["api_key"] == "AIza-secreta-1234"


async def test_una_key_guardada_en_claro_se_cifra_al_arrancar(fake_db, llm_limpio):
    fake_db.app_settings.docs.append({"_id": "llm", "api_key": "AIza-vieja-9999", "model": "gemini"})

    await llm_settings.load()

    assert llm_settings.effective()["api_key"] == "AIza-vieja-9999"
    assert fake_db.app_settings.docs[0]["api_key"].startswith("enc:")


def test_con_otro_secreto_la_key_no_se_descifra(monkeypatch):
    cifrada = llm_settings.cifrar("AIza-secreta-1234")
    monkeypatch.setenv("JWT_SECRET_KEY", "otro-secreto-distinto-de-al-menos-32-caracteres")

    assert llm_settings.descifrar(cifrada) == ""
