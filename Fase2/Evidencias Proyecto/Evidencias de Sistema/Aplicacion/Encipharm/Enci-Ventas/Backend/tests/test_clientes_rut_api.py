"""Alta de clientes (RQ-06): RUT obligatorio y unico, campos requeridos iguales en web y backend,
errores por campo y asignacion de vendedor."""
from datetime import datetime, timezone

import pytest
from app.core.odm import IntegrityError

from app.core.security import create_access_token, get_password_hash
from app.models_sql.cliente import Cliente
from app.models_sql.user import User
from app.services.clientes import import_clientes_csv, list_clientes

RUT_A = "12.345.678-5"
RUT_B = "11.111.111-1"


def _add_user(db, uid, rol):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.replace("-", " ").title(), rol=rol, activo=True,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _headers(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def vendedor(db_session):
    return _add_user(db_session, "vend-1", "vendedor")


@pytest.fixture
def supervisor(db_session):
    return _add_user(db_session, "sup-1", "supervisor")


def payload(**overrides):
    data = {"nombre": "Maria Soto", "empresa": "Avicola Los Pinos", "rut": RUT_A, "rubro": "Aves"}
    data.update(overrides)
    return data


def create(client, user, **overrides):
    return client.post("/clientes", json=payload(**overrides), headers=_headers(user))


# ── Campos obligatorios ──────────────────────────────────────────────────────

def test_minimum_valid_client_has_contact_company_rut_and_industry(client, vendedor):
    response = create(client, vendedor)

    assert response.status_code == 200
    body = response.json()
    assert body["rut"] == "12345678-5"  # sin puntos
    assert body["email"] is None and body["telefono"] is None and body["region"] is None
    assert body["vendedorUid"] == vendedor.id


@pytest.mark.parametrize("missing", ["nombre", "empresa", "rut", "rubro"])
def test_each_required_field_is_enforced(client, vendedor, missing):
    data = payload()
    del data[missing]

    response = client.post("/clientes", json=data, headers=_headers(vendedor))

    assert response.status_code == 422
    assert any(d["loc"][-1] == missing for d in response.json()["detalles"])


@pytest.mark.parametrize("empty", ["nombre", "empresa", "rubro"])
def test_blank_required_fields_are_rejected(client, vendedor, empty):
    assert create(client, vendedor, **{empty: ""}).status_code == 422


def test_optional_fields_can_still_be_sent(client, vendedor):
    response = create(client, vendedor, email="Maria@LosPinos.cl", telefono="+56 9 8765 4321", region="Maule")

    assert response.status_code == 200
    assert response.json()["email"] == "maria@lospinos.cl"
    assert response.json()["telefono"] == "87654321"


def test_invalid_rut_is_a_field_error_on_rut(client, vendedor):
    response = create(client, vendedor, rut="12.345.678-4")

    assert response.status_code == 422
    detail = next(d for d in response.json()["detalles"] if d["loc"][-1] == "rut")
    assert "verificador" in detail["msg"]


@pytest.mark.parametrize("rut", ["abc", "123", "12345678"])
def test_malformed_rut_is_rejected(client, vendedor, rut):
    assert create(client, vendedor, rut=rut).status_code == 422


# ── Unicidad ─────────────────────────────────────────────────────────────────

def test_duplicate_rut_names_the_existing_client_and_its_owner(client, vendedor, db_session):
    otro = _add_user(db_session, "vend-2", "vendedor")
    create(client, vendedor)

    response = create(client, otro, empresa="Otra Empresa", rut="12345678-5")

    assert response.status_code == 409
    body = response.json()
    assert body["codigo"] == "ERR_RUT_DUPLICADO"
    assert "Avicola Los Pinos" in body["error"] and "Vend 1" in body["error"]
    assert body["detalles"]["campo"] == "rut" and body["detalles"]["vendedor"] == "Vend 1"


def test_same_rut_in_any_format_counts_as_duplicate(client, vendedor):
    create(client, vendedor, rut="12.345.678-5")

    assert create(client, vendedor, empresa="Otra", rut=" 123456785 ").status_code == 409


def test_a_deleted_client_frees_its_rut(client, vendedor):
    first = create(client, vendedor).json()
    client.delete(f"/clientes/{first['id']}", headers=_headers(vendedor))

    assert create(client, vendedor, empresa="Nueva razon social").status_code == 200


def test_database_enforces_rut_uniqueness_for_active_clients(db_session):
    now = datetime.now(timezone.utc)
    base = dict(nombre="a", empresa="b", rubro="c", createdAt=now, updatedAt=now)
    db_session.add(Cliente(rut="12345678-5", **base))
    db_session.commit()
    db_session.add(Cliente(rut="12345678-5", **base))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_updating_to_another_clients_rut_is_a_conflict_but_keeping_your_own_is_fine(client, vendedor):
    one = create(client, vendedor).json()
    two = create(client, vendedor, empresa="Segunda", rut=RUT_B).json()

    assert client.patch(f"/clientes/{two['id']}", json={"rut": RUT_A}, headers=_headers(vendedor)).status_code == 409
    assert client.patch(f"/clientes/{one['id']}", json={"rut": "12.345.678-5"}, headers=_headers(vendedor)).status_code == 200


def test_duplicate_email_is_reported_on_the_email_field(client, vendedor):
    create(client, vendedor, email="uno@empresa.cl")

    response = create(client, vendedor, empresa="Otra", rut=RUT_B, email="UNO@empresa.cl")

    assert response.status_code == 409
    assert response.json()["detalles"]["campo"] == "email"


def test_clients_without_email_do_not_conflict_with_each_other(client, vendedor):
    assert create(client, vendedor).status_code == 200
    assert create(client, vendedor, empresa="Otra", rut=RUT_B).status_code == 200


# ── Lista y asignacion ───────────────────────────────────────────────────────

def test_new_client_shows_up_in_the_list_immediately(client, vendedor):
    created = create(client, vendedor).json()

    listed = client.get("/clientes", headers=_headers(vendedor)).json()

    assert [c["id"] for c in listed] == [created["id"]]
    assert listed[0]["rut"] == "12345678-5"


def test_vendedor_cannot_create_clients_for_someone_else(client, vendedor, db_session):
    otro = _add_user(db_session, "vend-2", "vendedor")

    assert create(client, vendedor, vendedorUid=otro.id).json()["vendedorUid"] == vendedor.id


@pytest.mark.parametrize("rol", ["supervisor", "admin"])
def test_supervisor_and_admin_can_assign_the_client_to_a_seller(client, vendedor, db_session, rol):
    jefe = _add_user(db_session, f"jefe-{rol}", rol)

    response = create(client, jefe, vendedorUid=vendedor.id)

    assert response.status_code == 200 and response.json()["vendedorUid"] == vendedor.id


def test_supervisor_can_reassign_an_existing_client(client, vendedor, supervisor, db_session):
    otro = _add_user(db_session, "vend-2", "vendedor")
    created = create(client, vendedor).json()

    response = client.patch(f"/clientes/{created['id']}", json={"vendedorUid": otro.id}, headers=_headers(supervisor))

    assert response.status_code == 200 and response.json()["vendedorUid"] == otro.id


def test_vendedor_cannot_reassign_their_client(client, vendedor, db_session):
    otro = _add_user(db_session, "vend-2", "vendedor")
    created = create(client, vendedor).json()

    response = client.patch(f"/clientes/{created['id']}", json={"vendedorUid": otro.id}, headers=_headers(vendedor))

    assert response.json()["vendedorUid"] == vendedor.id


def test_assigning_to_a_nonexistent_user_is_a_clear_422_not_a_500(client, supervisor):
    response = create(client, supervisor, vendedorUid="no-existe")

    assert response.status_code == 422
    assert response.json()["codigo"] == "ERR_VENDEDOR_INVALIDO"


def test_assigning_to_an_inactive_user_is_rejected(client, supervisor, db_session):
    inactivo = _add_user(db_session, "vend-off", "vendedor")
    inactivo.activo = False
    db_session.commit()

    assert create(client, supervisor, vendedorUid=inactivo.id).status_code == 422


# ── CSV ──────────────────────────────────────────────────────────────────────

def test_csv_requires_rut_and_industry_and_rejects_duplicates(db_session):
    content = "\n".join([
        "nombre,empresa,rut,rubro",
        "Uno,Empresa Uno,12.345.678-5,Aves",
        "Dos,Empresa Dos,,Aves",
        "Tres,Empresa Tres,12345678-5,Cerdos",
        "Cuatro,Empresa Cuatro,11111111-1,",
    ]).encode()

    result = import_clientes_csv(db_session, content)

    assert result["importados"] == 0
    assert {e["fila"] for e in result["errores"]} == {3, 4, 5}
    assert list_clientes(db_session) == []


def test_valid_csv_imports_canonical_ruts(db_session):
    content = "nombre,empresa,rut,rubro\nUno,Empresa Uno,12.345.678-5,Aves\nDos,Empresa Dos,11111111-1,Cerdos\n".encode()

    result = import_clientes_csv(db_session, content)

    assert result["importados"] == 2
    assert {c["rut"] for c in list_clientes(db_session)} == {"12345678-5", "11111111-1"}


# ── Orden de la lista ────────────────────────────────────────────────────────

def test_la_lista_trae_primero_el_cliente_mas_reciente_y_el_admin_lo_ve_en_la_primera_pagina(client, db_session, vendedor):
    from datetime import timedelta

    admin = _add_user(db_session, "adm-1", "admin")
    base = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(12):
        db_session.add(Cliente(
            id=f"c{i:02d}", nombre=f"N{i}", empresa=f"Empresa {i}", vendedorUid=vendedor.id, ownerUid=vendedor.id,
            estado="En proceso", createdAt=base + timedelta(minutes=i), updatedAt=base,
        ))
    db_session.commit()
    nuevo = create(client, vendedor, empresa="Recien Creado", rut=RUT_B).json()

    listing = client.get("/clientes?limit=500", headers=_headers(admin)).json()

    assert listing[0]["id"] == nuevo["id"]  # el que acaba de crear el vendedor, primero
    assert [c["empresa"] for c in listing[1:3]] == ["Empresa 11", "Empresa 10"]
    assert len(listing) == 13
