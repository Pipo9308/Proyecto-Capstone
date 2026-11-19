"""RQ-01: avisos dentro de la web. Creacion por hecho, privacidad por usuario, lectura, sondeo de
alertas de Intel (sin duplicar, solo recientes, solo a quien tiene acceso) y retencion de 90 dias."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api import notificaciones as api
from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.cliente import ClienteCreate
from app.models.comercial import OpportunityCreate, ProposalCreate
from app.models_sql.notificacion import Notificacion
from app.models_sql.user import User
from app.services import notificaciones as service
from app.services.clientes import create_cliente, update_cliente
from app.services.comercial import create_opportunity, create_proposal, update_proposal


def _add_user(db, uid, rol="vendedor", intel=False, active=True):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=active,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True,
        accesoInteligencia=intel, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _h(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


def _hours_ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class FakeIntel:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.alerts = {
            "critical": [{"id": "a-new", "title": "Cancelación SAG: X", "competitor": "ZOETIS", "created_at": _hours_ago(2)},
                         {"id": "a-old", "title": "Vieja", "competitor": "ZOETIS", "created_at": _hours_ago(24 * 10)}],
            "high": [{"id": "a-high", "title": "Nuevo registro", "competitor": "AGROVET", "created_at": _hours_ago(5)}],
        }

    async def get_alertas(self, *, priority=None, limit=50, **_):
        self.calls += 1
        if self.fail:
            raise HTTPException(status_code=503, detail="Intel caido")
        return {"data": self.alerts.get(priority, [])}


@pytest.fixture(autouse=True)
def fresh_throttle():
    service._last_run.clear()
    yield
    service._last_run.clear()


@pytest.fixture
def env(client, db_session):
    state = type("Env", (), {})()
    state.intel = FakeIntel()
    state.settings = get_settings().model_copy(update={"NOTIFICATIONS_INTEL_POLL_SECONDS": 120, "NOTIFICATIONS_INTEL_LOOKBACK_HOURS": 72})
    app.dependency_overrides[api.get_intel] = lambda: state.intel
    app.dependency_overrides[api.get_session_factory] = lambda: (lambda: nullcontext(db_session))
    app.dependency_overrides[get_settings] = lambda: state.settings
    return state


@pytest.fixture
def ana(db_session):
    return _add_user(db_session, "ana")


@pytest.fixture
def beto(db_session):
    return _add_user(db_session, "beto")


def avisar(db, user, titulo="Hola", **kwargs):
    row = service.crear(db, user.id, "prueba", titulo, **kwargs)
    db.commit()
    return row


# ── Crear, listar, leer ──────────────────────────────────────────────────────

def test_el_mismo_hecho_avisa_una_sola_vez(db_session, ana):
    assert avisar(db_session, ana, referencia="alerta-1") is not None
    assert service.crear(db_session, ana.id, "prueba", "Otra vez", referencia="alerta-1") is None
    assert avisar(db_session, ana, referencia="alerta-2") is not None
    assert db_session.query(Notificacion).count() == 2


def test_cada_usuario_ve_solo_sus_avisos_y_el_contador_de_no_leidas(client, env, db_session, ana, beto):
    avisar(db_session, ana, "Para Ana 1")
    avisar(db_session, ana, "Para Ana 2")
    avisar(db_session, beto, "Para Beto")

    page = client.get("/notificaciones", headers=_h(ana)).json()

    assert page["total"] == 2 and page["noLeidas"] == 2
    assert {n["titulo"] for n in page["items"]} == {"Para Ana 1", "Para Ana 2"}


def test_marcar_leida_y_marcar_todas(client, env, db_session, ana, beto):
    first = avisar(db_session, ana, "Uno")
    avisar(db_session, ana, "Dos")
    ajeno = avisar(db_session, beto, "De Beto")

    assert client.patch(f"/notificaciones/{first.id}/leida", headers=_h(ana)).status_code == 204
    assert client.get("/notificaciones?soloNoLeidas=true", headers=_h(ana)).json()["total"] == 1
    assert client.patch(f"/notificaciones/{ajeno.id}/leida", headers=_h(ana)).status_code == 404  # ni leer ajenas
    assert client.get("/notificaciones", headers=_h(beto)).json()["noLeidas"] == 1

    assert client.post("/notificaciones/marcar-todas", headers=_h(ana)).json() == {"marcadas": 1}
    assert client.get("/notificaciones", headers=_h(ana)).json()["noLeidas"] == 0
    assert client.get("/notificaciones", headers=_h(beto)).json()["noLeidas"] == 1  # las de otros no se tocan


def test_paginacion_y_orden_del_mas_nuevo_al_mas_viejo(client, env, db_session, ana):
    for i in range(3):
        row = avisar(db_session, ana, f"Aviso {i}")
        row.createdAt = datetime.now(timezone.utc) + timedelta(minutes=i)
    db_session.commit()

    page = client.get("/notificaciones?limit=2", headers=_h(ana)).json()
    rest = client.get("/notificaciones?limit=2&offset=2", headers=_h(ana)).json()

    assert [n["titulo"] for n in page["items"]] == ["Aviso 2", "Aviso 1"]
    assert [n["titulo"] for n in rest["items"]] == ["Aviso 0"]
    assert client.get("/notificaciones?limit=500", headers=_h(ana)).status_code == 422


def test_sin_sesion_no_se_accede(client):
    assert client.get("/notificaciones").status_code == 401


# ── Alertas de Intel ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_las_alertas_recientes_avisan_solo_a_quien_tiene_acceso_y_sin_duplicar(db_session):
    con_acceso = _add_user(db_session, "con-acceso", intel=True)
    admin = _add_user(db_session, "admin-1", rol="admin")
    _add_user(db_session, "sin-acceso", intel=False)
    _add_user(db_session, "inactivo", intel=True, active=False)
    intel = FakeIntel()

    created = await service.sync_intel_alerts(db_session, intel, lookback_hours=72)
    again = await service.sync_intel_alerts(db_session, intel, lookback_hours=72)

    assert created == 4 and again == 0  # 2 alertas recientes x 2 usuarios; la de hace 10 dias no
    rows = db_session.query(Notificacion).all()
    assert {r.usuarioId for r in rows} == {con_acceso.id, admin.id}
    assert {r.referencia for r in rows} == {"a-new", "a-high"}
    assert all(r.enlace == "/inteligencia" and r.tipo == service.TIPO_ALERTA for r in rows)


@pytest.mark.anyio
async def test_el_sondeo_respeta_el_intervalo_y_un_fallo_de_intel_no_lanza(db_session):
    _add_user(db_session, "con-acceso", intel=True)
    intel = FakeIntel()
    factory = lambda: nullcontext(db_session)  # noqa: E731

    await service.mantenimiento(factory, intel, poll_seconds=120, lookback_hours=72)
    calls_after_first = intel.calls
    await service.mantenimiento(factory, intel, poll_seconds=120, lookback_hours=72)
    assert intel.calls == calls_after_first  # dentro del intervalo no vuelve a consultar

    service._last_run.clear()
    intel.fail = True
    await service.mantenimiento(factory, intel, poll_seconds=120, lookback_hours=72)  # no lanza


@pytest.mark.anyio
async def test_con_el_sondeo_apagado_no_consulta_a_intel(db_session):
    _add_user(db_session, "con-acceso", intel=True)
    intel = FakeIntel()

    await service.mantenimiento(lambda: nullcontext(db_session), intel, poll_seconds=0, lookback_hours=72)

    assert intel.calls == 0


def test_consultar_los_avisos_trae_las_alertas_de_intel(client, env, db_session):
    usuario = _add_user(db_session, "con-acceso", intel=True)

    primera = client.get("/notificaciones", headers=_h(usuario)).json()  # dispara el sondeo despues de responder
    segunda = client.get("/notificaciones", headers=_h(usuario)).json()

    assert primera["total"] == 0
    assert segunda["total"] == 2 and segunda["noLeidas"] == 2
    assert env.intel.calls == 2  # critical + high, una sola vez pese a dos consultas


# ── Retencion ────────────────────────────────────────────────────────────────

def test_la_purga_borra_solo_lo_anterior_a_90_dias(db_session, ana):
    viejo, reciente = avisar(db_session, ana, "viejo"), avisar(db_session, ana, "reciente")
    viejo.createdAt = datetime.now(timezone.utc) - timedelta(days=91)
    reciente.createdAt = datetime.now(timezone.utc) - timedelta(days=89)
    db_session.commit()

    assert service.purgar(db_session) == 1
    assert [n.titulo for n in db_session.query(Notificacion).all()] == ["reciente"]


# ── Hechos que originan avisos ───────────────────────────────────────────────

def _cliente_payload(**over):
    data = {"nombre": "Maria", "empresa": "Avicola Pinos", "rut": "12345678-5", "rubro": "Aves"}
    data.update(over)
    return ClienteCreate(**data)


def test_asignar_un_cliente_a_otro_vendedor_le_avisa(db_session, ana):
    supervisor = {"uid": "sup-1", "rol": "supervisor", "nombre": "Sofia"}

    cliente = create_cliente(db_session, _cliente_payload(vendedorUid=ana.id), user=supervisor)

    row = db_session.query(Notificacion).one()
    assert row.usuarioId == ana.id and row.tipo == service.TIPO_CLIENTE
    assert "Avicola Pinos" in row.titulo and "Sofia" in row.mensaje and row.enlace == f"/clientes/{cliente['id']}"


def test_un_vendedor_que_crea_su_propio_cliente_no_se_avisa_a_si_mismo(db_session, ana):
    create_cliente(db_session, _cliente_payload(vendedorUid=ana.id), user={"uid": ana.id, "rol": "vendedor"})

    assert db_session.query(Notificacion).count() == 0


def test_reasignar_avisa_al_nuevo_vendedor_y_no_si_no_cambia(db_session, ana, beto):
    admin = {"uid": "adm-1", "rol": "admin", "nombre": "Admin"}
    cliente = create_cliente(db_session, _cliente_payload(vendedorUid=ana.id), user=admin)
    db_session.query(Notificacion).delete()
    db_session.commit()

    update_cliente(db_session, cliente["id"], {"nombre": "Otro nombre"}, user=admin)
    assert db_session.query(Notificacion).count() == 0

    update_cliente(db_session, cliente["id"], {"vendedorUid": beto.id}, user=admin)
    assert [n.usuarioId for n in db_session.query(Notificacion).all()] == [beto.id]


def _propuesta(db, owner_uid):
    cliente = create_cliente(db, _cliente_payload(vendedorUid=owner_uid), user={"uid": owner_uid, "rol": "vendedor"})
    owner = {"uid": owner_uid, "rol": "vendedor"}
    opp = create_opportunity(db, OpportunityCreate(clienteId=cliente["id"], titulo="Venta"), owner)
    return create_proposal(db, ProposalCreate(clienteId=cliente["id"], oportunidadId=opp["id"], titulo="Oferta anual", montoNeto=1000), owner)


def test_cuando_otro_cambia_el_estado_de_la_propuesta_el_dueno_recibe_el_aviso(db_session, ana):
    proposal = _propuesta(db_session, ana.id)

    update_proposal(db_session, proposal["id"], {"estado": "aceptada"}, {"uid": "sup-1", "rol": "supervisor", "nombre": "Sofia"})

    row = db_session.query(Notificacion).one()
    assert row.usuarioId == ana.id and row.tipo == service.TIPO_PROPUESTA
    assert "Oferta anual" in row.titulo and "aceptada" in row.titulo and row.enlace == "/propuestas"


def test_si_el_dueno_cambia_su_propia_propuesta_no_hay_aviso(db_session, ana):
    proposal = _propuesta(db_session, ana.id)

    update_proposal(db_session, proposal["id"], {"estado": "enviada"}, {"uid": ana.id, "rol": "vendedor"})

    assert db_session.query(Notificacion).count() == 0
