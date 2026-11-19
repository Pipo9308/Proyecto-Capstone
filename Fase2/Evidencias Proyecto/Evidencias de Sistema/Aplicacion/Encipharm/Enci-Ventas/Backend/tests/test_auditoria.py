"""Auditoria (RNF-03): quien, que, cuando, desde donde y como termino; sin guardar secretos."""
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models_sql.audit import AuditLog
from app.models_sql.user import User
from app.services import audit


def _add_user(db, uid, rol="vendedor", password="ClaveInicial123"):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=True,
        password_hash=get_password_hash(password), webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _h(user, **extra):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}", **extra}


@pytest.fixture
def ana(db_session):
    return _add_user(db_session, "ana")


@pytest.fixture
def admin(db_session):
    return _add_user(db_session, "adm", "admin")


def rows(db, **filters):
    return db.query(AuditLog).filter_by(**filters).order_by(AuditLog.createdAt).all()


CLIENTE = {"nombre": "Maria", "empresa": "Avicola Pinos", "rut": "12345678-5", "rubro": "Aves"}


def test_crear_un_cliente_deja_quien_que_donde_y_como_termino(client, db_session, ana):
    response = client.post(
        "/clientes", json=CLIENTE,
        headers=_h(ana, **{"User-Agent": "EnciApp/1.2 (Android)", "X-Enci-Client": "mobile", "X-Forwarded-For": "200.1.2.3, 10.0.0.1"}),
    )

    assert response.status_code == 200
    row = rows(db_session, resource="clientes")[0]
    assert (row.userUid, row.userRole, row.method, row.route) == (ana.id, "vendedor", "POST", "/clientes")
    assert (row.statusCode, row.result, row.client) == (200, "success", "mobile")
    assert row.ip == "200.1.2.3" and row.userAgent == "EnciApp/1.2 (Android)"
    assert row.createdAt is not None


def test_la_ruta_se_guarda_como_plantilla_con_el_id_aparte(client, db_session, ana):
    cliente = client.post("/clientes", json=CLIENTE, headers=_h(ana)).json()

    client.patch(f"/clientes/{cliente['id']}", json={"region": "Maule"}, headers=_h(ana))

    row = rows(db_session, method="PATCH")[0]
    assert row.route == "/clientes/{cliente_id}" and row.resourceId == cliente["id"]


def test_las_lecturas_no_se_auditan_pero_la_descarga_de_archivos_si(db_session):
    assert not audit.should_audit("GET", "/clientes")
    assert audit.should_audit("GET", "/propuestas/archivos/descarga")
    assert audit.should_audit("DELETE", "/rag/documents/abc")
    assert not audit.should_audit("PATCH", "/notificaciones/x/leida")
    assert not audit.should_audit("POST", "/inteligencia/competencia-chat/stream")


def test_un_get_no_deja_registro(client, db_session, ana):
    client.get("/clientes", headers=_h(ana))

    assert db_session.query(AuditLog).count() == 0


def test_un_permiso_denegado_queda_como_denied(client, db_session, ana):
    response = client.post("/competencia/catalogo", json={"nombre": "X"}, headers=_h(ana))

    assert response.status_code == 403
    row = rows(db_session, resource="competencia")[0]
    assert row.result == "denied" and row.statusCode == 403 and row.userUid == ana.id


def test_un_error_de_validacion_queda_como_failure(client, db_session, ana):
    client.post("/clientes", json={"nombre": "solo nombre"}, headers=_h(ana))

    assert rows(db_session, resource="clientes")[0].result == "failure"


def test_sin_sesion_se_registra_como_anonimo(client, db_session):
    client.post("/clientes", json=CLIENTE)

    row = rows(db_session, resource="clientes")[0]
    assert row.userUid is None and row.result == "denied"


def test_un_token_falso_no_atribuye_la_accion_a_nadie(client, db_session):
    client.post("/clientes", json=CLIENTE, headers={"Authorization": "Bearer no.es.un.token"})

    assert rows(db_session, resource="clientes")[0].userUid is None


def test_el_login_registra_el_correo_y_nunca_la_contrasena(client, db_session, ana):
    client.post("/auth/login", json={"email": ana.email, "password": "ClaveInicial123"})
    client.post("/auth/login", json={"email": ana.email, "password": "ContraseñaIncorrecta99"})
    client.post("/auth/login", json={"email": "nadie@test.cl", "password": "ClaveInicial123"})

    ok, bad, unknown = rows(db_session, resource="auth")
    assert (ok.result, ok.userUid, ok.details) == ("success", ana.id, {"email": ana.email})
    assert (bad.result, bad.statusCode) == ("denied", 401)
    assert (unknown.result, unknown.userUid, unknown.details) == ("denied", None, {"email": "nadie@test.cl"})
    everything = " ".join(str(vars(r)) for r in db_session.query(AuditLog).all())
    assert "ClaveInicial123" not in everything and "ContraseñaIncorrecta99" not in everything


def test_un_fallo_al_guardar_la_auditoria_no_tumba_la_peticion(client, ana):
    def broken():
        raise RuntimeError("base de auditoria caida")

    app.state.audit_session_factory = broken

    assert client.post("/clientes", json=CLIENTE, headers=_h(ana)).status_code == 200


# ── Consulta ─────────────────────────────────────────────────────────────────

def test_solo_el_admin_consulta_la_auditoria(client, ana, admin):
    assert client.get("/auditoria", headers=_h(ana)).status_code == 403
    assert client.get("/auditoria").status_code == 401
    assert client.get("/auditoria", headers=_h(admin)).status_code == 200


def test_el_timestamp_es_iso_8601_utc_con_milisegundos(client, ana, admin):
    client.post("/clientes", json=CLIENTE, headers=_h(ana))

    entry = client.get("/auditoria?recurso=clientes", headers=_h(admin)).json()["items"][0]

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", entry["timestamp"])
    assert entry["userUid"] == ana.id and entry["result"] == "success"


def test_filtros_y_paginacion_de_la_consulta(client, db_session, ana, admin):
    for i in range(3):
        client.post("/clientes", json={**CLIENTE, "rut": f"1234567{i}-0", "email": f"c{i}@x.cl"}, headers=_h(ana))
    client.post("/competencia/catalogo", json={"nombre": "X"}, headers=_h(ana))  # denegado

    def get(qs):
        return client.get(f"/auditoria?{qs}", headers=_h(admin)).json()

    assert get("")["total"] == 4
    assert get("usuario=" + ana.id)["total"] == 4
    assert get("resultado=denied")["total"] == 1
    assert get("recurso=clientes&limit=2")["total"] == 3 and len(get("recurso=clientes&limit=2")["items"]) == 2
    assert len(get("recurso=clientes&limit=2&offset=2")["items"]) == 1
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert get(f"desde={future}")["total"] == 0
    assert client.get("/auditoria?limit=1000", headers=_h(admin)).status_code == 422
    assert client.get("/auditoria?resultado=raro", headers=_h(admin)).status_code == 422


def test_no_hay_forma_de_editar_ni_borrar_registros(client, admin):
    for method in ("put", "patch", "delete", "post"):
        assert getattr(client, method)("/auditoria", headers=_h(admin)).status_code == 405
