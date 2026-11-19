"""RQ-02: calendario. Permisos por rol, validaciones, mover, realizada -> historial del cliente, y
avisos de 24 h / 1 h por el sistema de notificaciones."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models_sql.cliente import Cliente
from app.models_sql.comercial import Interaction, Opportunity
from app.models_sql.evento import Evento
from app.models_sql.notificacion import Notificacion
from app.models_sql.user import User
from app.services import notificaciones
from app.services.eventos import sync_reminders

NOW = datetime(2026, 10, 12, 12, 0, 0)  # UTC sin zona, como se guarda


def _add_user(db, uid, rol="vendedor"):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=True,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _h(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


def _cliente(db, uid, name="Avicola Pinos", rut="11111111-1"):
    cliente = Cliente(nombre="Maria", empresa=name, rut=rut, vendedorUid=uid, ownerUid=uid, estado="Activo")
    db.add(cliente)
    db.commit()
    return cliente


@pytest.fixture
def ana(db_session):
    return _add_user(db_session, "ana")


@pytest.fixture
def beto(db_session):
    return _add_user(db_session, "beto")


@pytest.fixture
def sup(db_session):
    return _add_user(db_session, "sup", "supervisor")


@pytest.fixture
def cliente_ana(db_session, ana):
    return _cliente(db_session, ana.id)


def evento(cliente, start=NOW + timedelta(days=1), hours=1, **over):
    data = {
        "clienteId": cliente.id, "tipo": "presencial", "inicio": start.isoformat() + "Z",
        "fin": (start + timedelta(hours=hours)).isoformat() + "Z", "lugar": "Plantel norte",
    }
    data.update(over)
    return data


def crear(client, user, cliente, **over):
    response = client.post("/eventos", json=evento(cliente, **over), headers=_h(user))
    assert response.status_code == 201, response.text
    return response.json()


def listar(client, user, desde=NOW - timedelta(days=1), hasta=NOW + timedelta(days=10), **params):
    query = {"desde": desde.isoformat() + "Z", "hasta": hasta.isoformat() + "Z", **params}
    return client.get("/eventos", params=query, headers=_h(user))


# ── Crear y listar ───────────────────────────────────────────────────────────

def test_el_vendedor_agenda_una_visita_a_su_cliente(client, ana, cliente_ana):
    body = crear(client, ana, cliente_ana)

    assert body["estado"] == "planificada" and body["vendedorUid"] == ana.id
    assert body["clienteNombre"] == "Avicola Pinos" and body["vendedorNombre"] == "Ana"
    assert body["inicio"].startswith("2026-10-13T12:00")


def test_las_horas_con_zona_se_guardan_en_utc(client, ana, cliente_ana):
    body = crear(client, ana, cliente_ana, inicio="2026-10-13T09:00:00-03:00", fin="2026-10-13T10:00:00-03:00")

    assert body["inicio"].startswith("2026-10-13T12:00:00")


def test_un_vendedor_no_agenda_con_un_cliente_ajeno(client, db_session, ana, beto):
    ajeno = _cliente(db_session, beto.id, "Ajena", "22222222-2")

    response = client.post("/eventos", json=evento(ajeno), headers=_h(ana))

    assert response.status_code == 403


@pytest.mark.parametrize("over", [
    {"fin": (NOW + timedelta(days=1)).isoformat() + "Z"},  # fin == inicio
    {"fin": (NOW - timedelta(days=1)).isoformat() + "Z"},  # fin antes del inicio
    {"fin": (NOW + timedelta(days=1, hours=13)).isoformat() + "Z"},  # mas de 12 horas
    {"tipo": "telepatia"},
])
def test_datos_invalidos_se_rechazan(client, ana, cliente_ana, over):
    assert client.post("/eventos", json=evento(cliente_ana, **over), headers=_h(ana)).status_code == 422


def test_la_oportunidad_debe_ser_del_mismo_cliente(client, db_session, ana, cliente_ana):
    otro = _cliente(db_session, ana.id, "Otra", "33333333-3")
    opp = Opportunity(clienteId=otro.id, titulo="X", vendedorUid=ana.id)
    db_session.add(opp)
    db_session.commit()

    assert client.post("/eventos", json=evento(cliente_ana, oportunidadId=opp.id), headers=_h(ana)).status_code == 422
    assert client.post("/eventos", json=evento(otro, oportunidadId=opp.id), headers=_h(ana)).status_code == 201


def test_cada_vendedor_ve_solo_sus_eventos_y_el_supervisor_todos_con_filtro(client, db_session, ana, beto, sup, cliente_ana):
    cliente_beto = _cliente(db_session, beto.id, "De Beto", "44444444-4")
    crear(client, ana, cliente_ana)
    crear(client, beto, cliente_beto)

    assert [e["vendedorUid"] for e in listar(client, ana).json()] == [ana.id]
    assert [e["vendedorUid"] for e in listar(client, ana, vendedorUid=beto.id).json()] == [ana.id]  # el filtro no la deja ver a Beto
    assert len(listar(client, sup).json()) == 2
    assert [e["vendedorUid"] for e in listar(client, sup, vendedorUid=beto.id).json()] == [beto.id]


def test_el_listado_trae_lo_que_se_cruza_con_el_rango(client, ana, cliente_ana):
    crear(client, ana, cliente_ana, start=NOW + timedelta(days=1))
    crear(client, ana, cliente_ana, start=NOW + timedelta(days=20))

    assert len(listar(client, ana, hasta=NOW + timedelta(days=5)).json()) == 1
    assert len(listar(client, ana, desde=NOW + timedelta(days=1, minutes=30), hasta=NOW + timedelta(days=2)).json()) == 1  # cruza a mitad
    assert listar(client, ana, desde=NOW + timedelta(days=3), hasta=NOW + timedelta(days=4)).json() == []


def test_rangos_invalidos_o_demasiado_grandes(client, ana):
    assert listar(client, ana, desde=NOW, hasta=NOW - timedelta(days=1)).status_code == 422
    assert listar(client, ana, desde=NOW, hasta=NOW + timedelta(days=200)).status_code == 422


def test_el_supervisor_agenda_para_un_vendedor_y_a_este_le_llega_el_aviso(client, db_session, ana, sup, cliente_ana):
    body = crear(client, sup, cliente_ana, vendedorUid=ana.id)

    assert body["vendedorUid"] == ana.id
    aviso = db_session.query(Notificacion).one()
    assert aviso.usuarioId == ana.id and aviso.enlace == "/calendario" and "Sup" in aviso.mensaje


def test_un_vendedor_no_agenda_para_otro(client, ana, beto, cliente_ana):
    assert client.post("/eventos", json=evento(cliente_ana, vendedorUid=beto.id), headers=_h(ana)).status_code == 403


# ── Mover, realizar, cancelar ────────────────────────────────────────────────

def test_mover_un_evento_cambia_inicio_y_fin(client, ana, cliente_ana):
    event = crear(client, ana, cliente_ana)
    nuevo = NOW + timedelta(days=2)

    response = client.patch(
        f"/eventos/{event['id']}", json={"inicio": nuevo.isoformat() + "Z", "fin": (nuevo + timedelta(hours=2)).isoformat() + "Z"}, headers=_h(ana),
    )

    assert response.status_code == 200 and response.json()["inicio"].startswith("2026-10-14T12:00")


def test_no_se_puede_mover_dejando_el_fin_antes_del_inicio(client, ana, cliente_ana):
    event = crear(client, ana, cliente_ana)

    response = client.patch(f"/eventos/{event['id']}", json={"inicio": (NOW + timedelta(days=5)).isoformat() + "Z"}, headers=_h(ana))

    assert response.status_code == 422


def test_marcar_como_realizada_registra_la_visita_en_el_historial_una_sola_vez(client, db_session, ana, cliente_ana):
    event = crear(client, ana, cliente_ana, notas="Revisar galpones")

    done = client.patch(f"/eventos/{event['id']}", json={"estado": "realizada"}, headers=_h(ana)).json()

    interaction = db_session.query(Interaction).one()
    assert done["interaccionId"] == interaction.id
    assert interaction.clienteId == cliente_ana.id and interaction.tipo == "visita" and interaction.vendedorUid == ana.id
    assert "Plantel norte" in interaction.resumen and "Revisar galpones" in interaction.resumen
    again = client.patch(f"/eventos/{event['id']}", json={"estado": "realizada"}, headers=_h(ana))
    assert again.status_code == 409 and db_session.query(Interaction).count() == 1


@pytest.mark.parametrize("tipo,esperado", [("virtual", "reunion"), ("llamada", "llamada")])
def test_el_tipo_de_evento_define_el_tipo_de_interaccion(client, db_session, ana, cliente_ana, tipo, esperado):
    event = crear(client, ana, cliente_ana, tipo=tipo)

    client.patch(f"/eventos/{event['id']}", json={"estado": "realizada"}, headers=_h(ana))

    assert db_session.query(Interaction).one().tipo == esperado


def test_un_evento_cancelado_o_realizado_ya_no_se_mueve(client, ana, cliente_ana):
    event = crear(client, ana, cliente_ana)
    assert client.patch(f"/eventos/{event['id']}", json={"estado": "cancelada"}, headers=_h(ana)).json()["estado"] == "cancelada"

    moved = client.patch(f"/eventos/{event['id']}", json={"inicio": (NOW + timedelta(days=3)).isoformat() + "Z"}, headers=_h(ana))
    note = client.patch(f"/eventos/{event['id']}", json={"notas": "Se cancelo por lluvia"}, headers=_h(ana))

    assert moved.status_code == 409
    assert note.status_code == 200  # las notas si se pueden completar


def test_cancelar_no_crea_historial(client, db_session, ana, cliente_ana):
    event = crear(client, ana, cliente_ana)

    client.patch(f"/eventos/{event['id']}", json={"estado": "cancelada"}, headers=_h(ana))

    assert db_session.query(Interaction).count() == 0


def test_solo_el_dueno_o_un_supervisor_edita(client, ana, beto, sup, cliente_ana):
    event = crear(client, ana, cliente_ana)

    assert client.patch(f"/eventos/{event['id']}", json={"lugar": "X"}, headers=_h(beto)).status_code == 403
    assert client.patch(f"/eventos/{event['id']}", json={"lugar": "Y"}, headers=_h(sup)).status_code == 200
    assert client.patch("/eventos/no-existe", json={"lugar": "Y"}, headers=_h(sup)).status_code == 404


def test_sin_sesion_no_se_accede(client):
    assert client.get("/eventos", params={"desde": "2026-10-01T00:00:00Z", "hasta": "2026-10-02T00:00:00Z"}).status_code == 401


# ── Avisos 24 h y 1 h ────────────────────────────────────────────────────────

def _planned(db, ana, cliente, start):
    event = Evento(
        clienteId=cliente.id, vendedorUid=ana.id, tipo="presencial", inicio=start, fin=start + timedelta(hours=1),
        lugar="Plantel norte", estado="planificada",
    )
    db.add(event)
    db.commit()
    return event


def _titles(db):
    return sorted(n.titulo for n in db.query(Notificacion).filter(Notificacion.tipo == notificaciones.TIPO_VISITA).all())


def test_una_visita_en_menos_de_24_horas_avisa_una_vez(db_session, ana, cliente_ana):
    _planned(db_session, ana, cliente_ana, NOW + timedelta(hours=10))

    assert sync_reminders(db_session, now=NOW) == 1
    assert sync_reminders(db_session, now=NOW + timedelta(minutes=5)) == 0
    assert _titles(db_session) == ["Visita en menos de 24 horas: Avicola Pinos"]


def test_media_hora_antes_avisa_la_de_1_hora(db_session, ana, cliente_ana):
    _planned(db_session, ana, cliente_ana, NOW + timedelta(hours=10))
    sync_reminders(db_session, now=NOW)

    assert sync_reminders(db_session, now=NOW + timedelta(hours=9, minutes=30)) == 1

    assert _titles(db_session) == ["Visita en menos de 1 hora: Avicola Pinos", "Visita en menos de 24 horas: Avicola Pinos"]


def test_no_avisa_de_visitas_lejanas_pasadas_canceladas_ni_realizadas(db_session, ana, cliente_ana):
    _planned(db_session, ana, cliente_ana, NOW + timedelta(hours=30))
    _planned(db_session, ana, cliente_ana, NOW - timedelta(hours=1))
    for estado in ("cancelada", "realizada"):
        event = _planned(db_session, ana, cliente_ana, NOW + timedelta(hours=5))
        event.estado = estado
    db_session.commit()

    assert sync_reminders(db_session, now=NOW) == 0


def test_si_la_visita_se_mueve_vuelve_a_avisar(db_session, ana, cliente_ana):
    event = _planned(db_session, ana, cliente_ana, NOW + timedelta(hours=10))
    sync_reminders(db_session, now=NOW)

    event.inicio = NOW + timedelta(hours=12)
    event.fin = event.inicio + timedelta(hours=1)
    db_session.commit()

    assert sync_reminders(db_session, now=NOW) == 1


def test_el_aviso_llega_a_quien_consulta_sus_notificaciones(client, db_session, ana, cliente_ana):
    from contextlib import nullcontext
    from app.api import notificaciones as api
    from app.main import app
    from app.services.notificaciones import _last_run

    _last_run.clear()
    app.dependency_overrides[api.get_intel] = lambda: None
    app.dependency_overrides[api.get_session_factory] = lambda: (lambda: nullcontext(db_session))
    _planned(db_session, ana, cliente_ana, datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30))

    client.get("/notificaciones", headers=_h(ana))  # el mantenimiento corre despues de responder
    page = client.get("/notificaciones", headers=_h(ana)).json()

    assert [n["titulo"] for n in page["items"]] == ["Visita en menos de 1 hora: Avicola Pinos"]
    _last_run.clear()
