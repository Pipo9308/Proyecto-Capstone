"""RNF-09: logs estructurados, un X-Request-ID por peticion y traza de los errores 500."""
import json
import logging

from fastapi.testclient import TestClient

from app.core.logging_config import JsonFormatter
from app.main import app


def _record(message="hola", **extra):
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)
    record.extra_fields = extra
    return record


def test_el_formato_json_trae_hora_iso_nivel_y_campos():
    line = json.loads(JsonFormatter().format(_record(request_id="abc", status=200)))

    assert line["timestamp"].endswith("Z") and "T" in line["timestamp"] and len(line["timestamp"].split(".")[1]) == 4
    assert (line["level"], line["logger"], line["message"]) == ("INFO", "app.test", "hola")
    assert line["request_id"] == "abc" and line["status"] == 200


def test_la_excepcion_va_en_el_mismo_registro():
    try:
        raise ValueError("falla")
    except ValueError:
        import sys
        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())

    assert "ValueError: falla" in json.loads(JsonFormatter().format(record))["exception"]


def test_cada_respuesta_trae_x_request_id_y_se_respeta_el_que_llega(client):
    generated = client.get("/health").headers["x-request-id"]
    echoed = client.get("/health", headers={"X-Request-ID": "trace-12345678"}).headers["x-request-id"]
    unsafe = client.get("/health", headers={"X-Request-ID": "mal id\ncon salto"}).headers["x-request-id"]

    assert len(generated) == 32
    assert echoed == "trace-12345678"
    assert unsafe != "mal id\ncon salto" and len(unsafe) == 32


def test_cada_peticion_deja_un_log_con_ruta_estado_y_duracion(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.post("/auth/login", json={"email": "x@test.cl", "password": "ClaveInicial123"})

    entry = next(r for r in caplog.records if r.name == "app.request").extra_fields
    assert (entry["method"], entry["route"], entry["status"]) == ("POST", "/auth/login", 401)
    assert entry["duration_ms"] >= 0 and entry["request_id"]


def test_las_sondas_de_health_no_llenan_el_log(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/health")

    assert [r for r in caplog.records if r.name == "app.request"] == []


def test_un_error_500_deja_traceback_nivel_error_y_el_id_de_la_peticion(caplog):
    @app.get("/_boom")
    def boom():
        raise RuntimeError("fallo inesperado")

    try:
        with caplog.at_level(logging.INFO):
            response = TestClient(app, raise_server_exceptions=False).get("/_boom", headers={"X-Request-ID": "trace-boom-001"})
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_boom"]

    assert response.status_code == 500 and response.json()["error"] == "Error interno del servidor"
    assert "fallo inesperado" not in response.text  # el detalle no sale al cliente
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    traced = next(r for r in errors if r.name == "app.core.errors")
    assert traced.exc_info and traced.extra_fields["request_id"] == "trace-boom-001"
    assert any(r.name == "app.request" and r.extra_fields["status"] == 500 for r in errors)


def test_un_error_500_lleva_cabeceras_cors_para_que_el_navegador_vea_la_causa_real():
    """Sin esto el navegador mostraba un 500 como 'bloqueado por CORS' y ocultaba el fallo."""
    from app.core.config import get_settings

    @app.get("/_boom2")
    def boom():
        raise RuntimeError("tabla inexistente")

    origin = get_settings().cors_origins_list[0]
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/_boom2", headers={"Origin": origin})
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/_boom2"]

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin
    assert response.json()["error"] == "Error interno del servidor"
