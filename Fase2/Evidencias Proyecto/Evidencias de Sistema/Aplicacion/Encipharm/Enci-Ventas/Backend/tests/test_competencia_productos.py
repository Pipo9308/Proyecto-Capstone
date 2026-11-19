"""RQ-04: productos de la competencia, historial de precios con aprobacion, equivalencias,
comparativa por precio por unidad, resumen, filtros con paginacion y permisos."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models_sql.cliente import Cliente
from app.models_sql.competencia import PrecioCompetencia
from app.models_sql.user import User


def _add_user(db, uid, rol):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.replace("-", " ").title(), rol=rol, activo=True,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _h(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def vendedor(db_session):
    return _add_user(db_session, "vend-1", "vendedor")


@pytest.fixture
def otro_vendedor(db_session):
    return _add_user(db_session, "vend-2", "vendedor")


@pytest.fixture
def supervisor(db_session):
    return _add_user(db_session, "sup-1", "supervisor")


@pytest.fixture
def admin(db_session):
    return _add_user(db_session, "adm-1", "admin")


def producto(**over):
    data = {
        "competidor": "Zoetis", "nombre": "Ivomec 1%", "principiosActivos": ["ivermectina"],
        "concentracion": "1%", "presentacion": "Frasco 500 ml", "unidadMedida": "ml", "cantidadPresentacion": 500,
        "categoria": "Antiparasitario", "especie": "Bovinos",
    }
    data.update(over)
    return data


def catalogo(**over):
    data = {
        "nombre": "Ivermax 1%", "sku": "IVX-500", "principiosActivos": ["ivermectina"], "unidadMedida": "ml",
        "cantidadPresentacion": 500, "precioLista": 40000, "categoria": "Antiparasitario",
    }
    data.update(over)
    return data


def crear_producto(client, user, **over):
    response = client.post("/competencia/productos", json=producto(**over), headers=_h(user))
    assert response.status_code == 201, response.text
    return response.json()


def crear_catalogo(client, user, **over):
    response = client.post("/competencia/catalogo", json=catalogo(**over), headers=_h(user))
    assert response.status_code == 201, response.text
    return response.json()


def reportar(client, user, product_id, precio=50000, **over):
    return client.post(f"/competencia/productos/{product_id}/precios", json={"precio": precio, **over}, headers=_h(user))


# ── Productos ────────────────────────────────────────────────────────────────

def test_vendedor_registra_un_producto_y_se_normalizan_los_textos(client, vendedor):
    body = crear_producto(client, vendedor, nombre="  Ivomec   1% ", principiosActivos=[" ivermectina ", ""])

    assert body["nombre"] == "Ivomec 1%"
    assert body["principiosActivos"] == ["ivermectina"]
    assert body["ultimoPrecio"] is None and body["equivalentes"] == []


def test_un_producto_repetido_da_409(client, vendedor):
    crear_producto(client, vendedor)

    response = client.post("/competencia/productos", json=producto(competidor="ZOETIS", nombre="ivomec 1%"), headers=_h(vendedor))

    assert response.status_code == 409


@pytest.mark.parametrize("campo,valor", [
    ("cantidadPresentacion", 0), ("unidadMedida", "litros"), ("nombre", "   "), ("competidor", ""),
    ("principiosActivos", ["a;b"]),
])
def test_valores_invalidos_se_rechazan(client, vendedor, campo, valor):
    response = client.post("/competencia/productos", json=producto(**{campo: valor}), headers=_h(vendedor))

    assert response.status_code == 422


def test_solo_supervisor_edita_y_solo_admin_borra(client, vendedor, supervisor, admin):
    pid = crear_producto(client, vendedor)["id"]

    assert client.patch(f"/competencia/productos/{pid}", json={"categoria": "X"}, headers=_h(vendedor)).status_code == 403
    edited = client.patch(f"/competencia/productos/{pid}", json={"categoria": "Vacunas"}, headers=_h(supervisor))
    assert edited.status_code == 200 and edited.json()["categoria"] == "Vacunas"
    assert client.delete(f"/competencia/productos/{pid}", headers=_h(supervisor)).status_code == 403
    assert client.delete(f"/competencia/productos/{pid}", headers=_h(admin)).status_code == 204
    assert client.get(f"/competencia/productos/{pid}", headers=_h(admin)).status_code == 404


def test_editar_no_puede_dejar_un_duplicado(client, vendedor, supervisor):
    crear_producto(client, vendedor)
    otro = crear_producto(client, vendedor, nombre="Otro", presentacion="Frasco 100 ml", cantidadPresentacion=100)

    response = client.patch(
        f"/competencia/productos/{otro['id']}", json={"nombre": "Ivomec 1%", "presentacion": "Frasco 500 ml"}, headers=_h(supervisor)
    )

    assert response.status_code == 409


# ── Precios ──────────────────────────────────────────────────────────────────

def test_el_reporte_de_un_vendedor_queda_pendiente_y_no_cuenta_hasta_aprobarse(client, vendedor, supervisor):
    pid = crear_producto(client, vendedor)["id"]

    reporte = reportar(client, vendedor, pid, 50000, fuente="Cotizacion cliente")
    assert reporte.status_code == 201
    assert reporte.json()["estado"] == "pendiente"
    assert reporte.json()["precioPorUnidad"] == 100.0  # 50000 / 500 ml
    listado = client.get("/competencia/productos", headers=_h(vendedor)).json()
    assert listado["items"][0]["ultimoPrecio"] is None

    aprobado = client.post(f"/competencia/precios/{reporte.json()['id']}/aprobar", headers=_h(supervisor))
    assert aprobado.status_code == 200 and aprobado.json()["estado"] == "aprobado"
    assert aprobado.json()["revisadoPor"] == supervisor.id
    listado = client.get("/competencia/productos", headers=_h(vendedor)).json()
    assert listado["items"][0]["ultimoPrecio"]["precio"] == 50000


def test_el_reporte_de_un_supervisor_se_aprueba_solo(client, supervisor):
    pid = crear_producto(client, supervisor)["id"]

    assert reportar(client, supervisor, pid).json()["estado"] == "aprobado"


def test_un_reporte_ya_revisado_no_se_revisa_dos_veces(client, vendedor, supervisor):
    pid = crear_producto(client, vendedor)["id"]
    rid = reportar(client, vendedor, pid).json()["id"]
    assert client.post(f"/competencia/precios/{rid}/descartar", headers=_h(supervisor)).json()["estado"] == "descartado"

    assert client.post(f"/competencia/precios/{rid}/aprobar", headers=_h(supervisor)).status_code == 409


def test_el_vendedor_no_puede_aprobar_ni_ver_la_cola(client, vendedor):
    pid = crear_producto(client, vendedor)["id"]
    rid = reportar(client, vendedor, pid).json()["id"]

    assert client.post(f"/competencia/precios/{rid}/aprobar", headers=_h(vendedor)).status_code == 403
    assert client.get("/competencia/precios", headers=_h(vendedor)).status_code == 403


def test_el_historial_no_se_pisa_y_el_ultimo_es_el_de_fecha_mas_reciente(client, supervisor):
    pid = crear_producto(client, supervisor)["id"]
    ayer = (date.today() - timedelta(days=1)).isoformat()
    reportar(client, supervisor, pid, 45000, fechaPrecio=ayer)
    reportar(client, supervisor, pid, 50000)
    reportar(client, supervisor, pid, 30000, fechaPrecio=(date.today() - timedelta(days=30)).isoformat())

    detalle = client.get(f"/competencia/productos/{pid}", headers=_h(supervisor)).json()

    assert [h["precio"] for h in detalle["historial"]] == [50000, 45000, 30000]
    assert detalle["ultimoPrecio"]["precio"] == 50000


def test_el_vendedor_solo_ve_sus_pendientes_en_el_historial(client, vendedor, otro_vendedor, supervisor):
    pid = crear_producto(client, vendedor)["id"]
    reportar(client, vendedor, pid, 11000)
    reportar(client, otro_vendedor, pid, 22000)
    reportar(client, supervisor, pid, 33000)

    precios = [h["precio"] for h in client.get(f"/competencia/productos/{pid}", headers=_h(vendedor)).json()["historial"]]

    assert sorted(precios) == [11000, 33000]


def test_precio_invalido_o_con_fecha_futura(client, vendedor):
    pid = crear_producto(client, vendedor)["id"]
    manana = (date.today() + timedelta(days=1)).isoformat()

    assert reportar(client, vendedor, pid, 0).status_code == 422
    assert reportar(client, vendedor, pid, 100, fechaPrecio=manana).status_code == 422
    assert reportar(client, vendedor, pid, 100, moneda="PESOS").status_code == 422
    assert reportar(client, vendedor, "no-existe", 100).status_code == 404


def test_un_vendedor_no_puede_asociar_un_cliente_ajeno(client, db_session, vendedor, otro_vendedor):
    pid = crear_producto(client, vendedor)["id"]
    db_session.add(Cliente(
        id="cli-ajeno", nombre="X", empresa="Ajena", rut="11111111-1", vendedorUid=otro_vendedor.id,
        ownerUid=otro_vendedor.id, estado="Activo",
    ))
    db_session.commit()

    assert reportar(client, vendedor, pid, 100, clienteId="cli-ajeno").status_code == 403


def test_la_cola_de_revision_pagina_y_filtra_por_estado(client, vendedor, supervisor):
    pid = crear_producto(client, vendedor)["id"]
    for precio in (1000, 2000, 3000):
        reportar(client, vendedor, pid, precio)
    reportar(client, supervisor, pid, 4000)  # aprobado

    cola = client.get("/competencia/precios?pageSize=2", headers=_h(supervisor)).json()

    assert cola["total"] == 3 and len(cola["items"]) == 2
    assert cola["items"][0]["productoNombre"] == "Ivomec 1%" and cola["items"][0]["competidor"] == "Zoetis"
    pagina2 = client.get("/competencia/precios?pageSize=2&page=2", headers=_h(supervisor)).json()
    assert len(pagina2["items"]) == 1
    assert client.get("/competencia/precios?estado=aprobado", headers=_h(supervisor)).json()["total"] == 1


# ── Lista con filtros y paginacion en base de datos ─────────────────────────

def test_filtros_por_competidor_categoria_principio_y_paginacion(client, vendedor):
    for i in range(5):
        crear_producto(client, vendedor, nombre=f"Ivomec {i}", presentacion=f"Frasco {i}")
    crear_producto(client, vendedor, competidor="Agrovet", nombre="Closantel", principiosActivos=["closantel"], categoria="Fasciolicida")

    def listar(qs):
        return client.get(f"/competencia/productos?{qs}", headers=_h(vendedor)).json()

    assert listar("competidor=zoetis")["total"] == 5
    assert listar("categoria=fasciolicida")["items"][0]["nombre"] == "Closantel"
    assert listar("principio=IVERM")["total"] == 5
    assert listar("q=closan")["total"] == 1
    primera, segunda = listar("pageSize=4&page=1"), listar("pageSize=4&page=2")
    assert (primera["total"], len(primera["items"]), len(segunda["items"])) == (6, 4, 2)
    assert primera["items"][0]["competidor"] == "Agrovet"  # orden estable por competidor y nombre
    assert client.get("/competencia/productos?pageSize=1000", headers=_h(vendedor)).status_code == 422


def test_los_comodines_de_la_busqueda_no_se_interpretan(client, vendedor):
    crear_producto(client, vendedor)

    assert client.get("/competencia/productos?q=_", headers=_h(vendedor)).json()["total"] == 0


# ── Catalogo Encipharm y equivalencias ───────────────────────────────────────

def test_catalogo_calcula_precio_por_unidad_y_solo_supervisor_escribe(client, vendedor, supervisor, admin):
    assert client.post("/competencia/catalogo", json=catalogo(), headers=_h(vendedor)).status_code == 403
    creado = crear_catalogo(client, supervisor)

    assert creado["precioPorUnidad"] == 80.0
    assert client.post("/competencia/catalogo", json=catalogo(), headers=_h(supervisor)).status_code == 409  # SKU repetido
    assert [p["id"] for p in client.get("/competencia/catalogo", headers=_h(vendedor)).json()] == [creado["id"]]
    assert client.delete(f"/competencia/catalogo/{creado['id']}", headers=_h(supervisor)).status_code == 403
    assert client.delete(f"/competencia/catalogo/{creado['id']}", headers=_h(admin)).status_code == 204


def test_los_inactivos_no_salen_del_catalogo_salvo_que_se_pidan(client, supervisor):
    creado = crear_catalogo(client, supervisor)
    client.patch(f"/competencia/catalogo/{creado['id']}", json={"activo": False}, headers=_h(supervisor))

    assert client.get("/competencia/catalogo", headers=_h(supervisor)).json() == []
    assert len(client.get("/competencia/catalogo?incluirInactivos=true", headers=_h(supervisor)).json()) == 1


def test_equivalencias_se_reemplazan_y_validan_que_el_producto_exista(client, vendedor, supervisor):
    pid = crear_producto(client, vendedor)["id"]
    a, b = crear_catalogo(client, supervisor)["id"], crear_catalogo(client, supervisor, nombre="Otro", sku="OTR")["id"]

    assert client.put(f"/competencia/productos/{pid}/equivalentes", json={"encipharmIds": [a]}, headers=_h(vendedor)).status_code == 403
    ok = client.put(f"/competencia/productos/{pid}/equivalentes", json={"encipharmIds": [a, b, a]}, headers=_h(supervisor))
    assert ok.status_code == 200 and [e["id"] for e in ok.json()["equivalentes"]] == [a, b]
    assert client.put(f"/competencia/productos/{pid}/equivalentes", json={"encipharmIds": ["x"]}, headers=_h(supervisor)).status_code == 422
    vacio = client.put(f"/competencia/productos/{pid}/equivalentes", json={"encipharmIds": []}, headers=_h(supervisor))
    assert vacio.json()["equivalentes"] == []


# ── Comparativa y resumen ────────────────────────────────────────────────────

def _escenario(client, supervisor, precio_comp=50000, **comp):
    enci = crear_catalogo(client, supervisor)["id"]  # 40000 / 500 ml = 80 por ml
    pid = crear_producto(client, supervisor, **comp)["id"]
    client.put(f"/competencia/productos/{pid}/equivalentes", json={"encipharmIds": [enci]}, headers=_h(supervisor))
    if precio_comp:
        reportar(client, supervisor, pid, precio_comp)  # 50000 / 500 ml = 100 por ml
    return enci, pid


def test_comparativa_usa_precio_por_unidad_y_el_signo_es_encipharm_menos_competidor(client, supervisor):
    enci, _ = _escenario(client, supervisor)

    body = client.get(f"/competencia/comparativa?productoEncipharmId={enci}", headers=_h(supervisor)).json()

    fila = body["equivalentes"][0]
    assert fila["precioPorUnidad"] == 100.0
    assert fila["diferenciaPct"] == -20.0  # Encipharm 20 % mas barato
    assert fila["motivoSinDiferencia"] is None


def test_comparativa_compara_presentaciones_distintas_por_unidad(client, supervisor):
    enci, _ = _escenario(client, supervisor, precio_comp=11000, presentacion="Frasco 100 ml", cantidadPresentacion=100)

    fila = client.get(f"/competencia/comparativa?productoEncipharmId={enci}", headers=_h(supervisor)).json()["equivalentes"][0]

    assert fila["precioPorUnidad"] == 110.0
    assert fila["diferenciaPct"] == -27.27


def test_comparativa_explica_por_que_no_hay_diferencia(client, vendedor, supervisor):
    enci, pid = _escenario(client, supervisor, precio_comp=None)
    reportar(client, vendedor, pid, 99999)  # pendiente: no cuenta

    fila = client.get(f"/competencia/comparativa?productoEncipharmId={enci}", headers=_h(vendedor)).json()["equivalentes"][0]
    assert fila["diferenciaPct"] is None and "Sin precio aprobado" in fila["motivoSinDiferencia"]

    reportar(client, supervisor, pid, 50000, moneda="USD")
    fila = client.get(f"/competencia/comparativa?productoEncipharmId={enci}", headers=_h(vendedor)).json()["equivalentes"][0]
    assert fila["diferenciaPct"] is None and fila["motivoSinDiferencia"] == "Monedas distintas"


def test_comparativa_unidades_distintas_no_se_comparan(client, supervisor):
    enci = crear_catalogo(client, supervisor, unidadMedida="g")["id"]
    pid = crear_producto(client, supervisor)["id"]
    client.put(f"/competencia/productos/{pid}/equivalentes", json={"encipharmIds": [enci]}, headers=_h(supervisor))
    reportar(client, supervisor, pid, 50000)

    fila = client.get(f"/competencia/comparativa?productoEncipharmId={enci}", headers=_h(supervisor)).json()["equivalentes"][0]

    assert fila["diferenciaPct"] is None and fila["motivoSinDiferencia"] == "Unidades de medida distintas"
    assert client.get("/competencia/comparativa?productoEncipharmId=nada", headers=_h(supervisor)).status_code == 404


def test_resumen_por_categoria_y_competidor(client, supervisor):
    _escenario(client, supervisor)
    sin_precio = crear_producto(client, supervisor, competidor="Agrovet", nombre="Sin precio")
    assert sin_precio["ultimoPrecio"] is None

    resumen = client.get("/competencia/resumen", headers=_h(supervisor)).json()

    assert resumen["porCategoria"] == [{
        "clave": "Antiparasitario", "unidadMedida": "ml", "moneda": "CLP", "productos": 1,
        "precioPromedioPorUnidad": 100.0, "diferenciaPromedioPct": -20.0,
    }]
    assert [r["clave"] for r in resumen["porCompetidor"]] == ["Zoetis"]
    assert resumen["productosSinPrecio"] == 1


def test_borrar_un_producto_borra_sus_precios_y_equivalencias(client, db_session, supervisor, admin):
    enci, pid = _escenario(client, supervisor)

    client.delete(f"/competencia/productos/{pid}", headers=_h(admin))

    assert db_session.query(PrecioCompetencia).count() == 0
    assert client.get(f"/competencia/comparativa?productoEncipharmId={enci}", headers=_h(admin)).json()["equivalentes"] == []


def test_sin_sesion_no_se_accede(client):
    assert client.get("/competencia/productos").status_code == 401
