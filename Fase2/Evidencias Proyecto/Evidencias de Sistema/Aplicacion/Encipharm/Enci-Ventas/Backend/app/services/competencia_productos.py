"""Base de productos de la competencia (RQ-04): productos, historial de precios, aprobacion,
equivalencias con el catalogo Encipharm (D5), comparativa y resumen.

Reglas: cada reporte de precio es un registro nuevo (nada se pisa); los reportes de un vendedor
quedan "pendiente" hasta que un supervisor/admin los aprueba; solo los aprobados cuentan para
comparar. Los precios por unidad se calculan al leer (precio / cantidadPresentacion).
"""
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from app.core.odm import func, or_
from app.core.odm import Session

from app.models_sql.competencia import (
    PrecioCompetencia,
    ProductoCompetencia,
    ProductoEncipharm,
    EquivalenciaProducto,
)
from app.models_sql.user import User
from app.services.comercial import assert_cliente_visible

MAX_PAGE_SIZE = 100


def _error(http_status: int, message: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail=message)


def _principios(text: str | None) -> list[str]:
    return [p for p in (text or "").split(";") if p]


def _ppu(precio: Any, cantidad: Any) -> float:
    return round(float(precio) / float(cantidad), 4)


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _apply(model, data: dict[str, Any]) -> None:
    for key, value in data.items():
        if key == "principiosActivos":
            value = ";".join(value or [])
        setattr(model, key, value)


# ── Catalogo Encipharm ───────────────────────────────────────────────────────

def serialize_encipharm(p: ProductoEncipharm) -> dict[str, Any]:
    return {
        "id": p.id, "nombre": p.nombre, "sku": p.sku,
        "principiosActivos": _principios(p.principiosActivos),
        "concentracion": p.concentracion, "presentacion": p.presentacion,
        "unidadMedida": p.unidadMedida, "cantidadPresentacion": float(p.cantidadPresentacion),
        "precioLista": None if p.precioLista is None else float(p.precioLista),
        "precioPorUnidad": None if p.precioLista is None else _ppu(p.precioLista, p.cantidadPresentacion),
        "moneda": p.moneda, "categoria": p.categoria, "especie": p.especie, "activo": p.activo,
    }


def _sku_free(db: Session, sku: str | None, exclude_id: str | None = None) -> None:
    if not sku:
        return
    query = db.query(ProductoEncipharm.id).filter(func.lower(ProductoEncipharm.sku) == sku.lower())
    if exclude_id:
        query = query.filter(ProductoEncipharm.id != exclude_id)
    if query.first():
        raise _error(status.HTTP_409_CONFLICT, "Ya existe un producto Encipharm con ese SKU")


def list_encipharm(db: Session, search: str | None = None, solo_activos: bool = True) -> list[dict[str, Any]]:
    query = db.query(ProductoEncipharm)
    if solo_activos:
        query = query.filter(ProductoEncipharm.activo.is_(True))
    if search:
        pattern = _like(search.strip())
        query = query.filter(or_(
            ProductoEncipharm.nombre.ilike(pattern, escape="\\"),
            ProductoEncipharm.principiosActivos.ilike(pattern, escape="\\"),
        ))
    return [serialize_encipharm(p) for p in query.order_by(ProductoEncipharm.nombre).limit(500).all()]


def get_encipharm_or_404(db: Session, product_id: str) -> ProductoEncipharm:
    product = db.query(ProductoEncipharm).filter(ProductoEncipharm.id == product_id).first()
    if product is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Producto Encipharm no encontrado")
    return product


def create_encipharm(db: Session, payload) -> dict[str, Any]:
    data = payload.model_dump()
    _sku_free(db, data.get("sku"))
    product = ProductoEncipharm()
    _apply(product, data)
    db.add(product)
    db.commit()
    return serialize_encipharm(product)


def update_encipharm(db: Session, product_id: str, payload) -> dict[str, Any]:
    product = get_encipharm_or_404(db, product_id)
    data = payload.model_dump(exclude_unset=True)
    for required in ("nombre", "unidadMedida", "cantidadPresentacion", "moneda", "activo"):
        if required in data and data[required] is None:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{required} no puede quedar vacio")
    if "sku" in data:
        _sku_free(db, data["sku"], exclude_id=product.id)
    _apply(product, data)
    db.commit()
    return serialize_encipharm(product)


def delete_encipharm(db: Session, product_id: str) -> None:
    product = get_encipharm_or_404(db, product_id)
    # SQLite de pruebas no aplica el ON DELETE CASCADE: se borran las equivalencias a mano.
    db.query(EquivalenciaProducto).filter(EquivalenciaProducto.productoEncipharmId == product.id).delete()
    db.delete(product)
    db.commit()


# ── Productos de la competencia ──────────────────────────────────────────────

def _price_dict(price: PrecioCompetencia, product: ProductoCompetencia, names: dict[str, str], with_product: bool = False) -> dict[str, Any]:
    data = {
        "id": price.id, "productoId": price.productoId, "precio": float(price.precio), "moneda": price.moneda,
        "precioPorUnidad": _ppu(price.precio, product.cantidadPresentacion), "unidadMedida": product.unidadMedida,
        "fuente": price.fuente, "fechaPrecio": price.fechaPrecio, "zona": price.zona, "clienteId": price.clienteId,
        "nota": price.nota, "estado": price.estado, "reportadoPor": price.reportadoPor,
        "reportadoPorNombre": names.get(price.reportadoPor), "revisadoPor": price.revisadoPor,
        "revisadoAt": price.revisadoAt, "createdAt": price.createdAt,
    }
    if with_product:
        data["productoNombre"] = product.nombre
        data["competidor"] = product.competidor
    return data


def _user_names(db: Session, prices: list[PrecioCompetencia]) -> dict[str, str]:
    ids = {p.reportadoPor for p in prices}
    if not ids:
        return {}
    return {u.id: u.nombre for u in db.query(User.id, User.nombre).filter(User.id.in_(ids)).all()}


def _latest_approved(db: Session, product_ids: list[str]) -> dict[str, PrecioCompetencia]:
    if not product_ids:
        return {}
    rows = (
        db.query(PrecioCompetencia)
        .filter(PrecioCompetencia.productoId.in_(product_ids), PrecioCompetencia.estado == "aprobado")
        .order_by(PrecioCompetencia.fechaPrecio.desc(), PrecioCompetencia.createdAt.desc())
        .all()
    )
    latest: dict[str, PrecioCompetencia] = {}
    for row in rows:
        latest.setdefault(row.productoId, row)
    return latest


def _encipharm_by_id(db: Session, ids: set[str]) -> dict[str, ProductoEncipharm]:
    if not ids:
        return {}
    return {p.id: p for p in db.query(ProductoEncipharm).filter(ProductoEncipharm.id.in_(ids)).all()}


def _equivalentes(db: Session, product_ids: list[str]) -> dict[str, list[dict[str, str]]]:
    if not product_ids:
        return {}
    links = db.query(EquivalenciaProducto).filter(EquivalenciaProducto.productoCompetenciaId.in_(product_ids)).all()
    catalog = _encipharm_by_id(db, {link.productoEncipharmId for link in links})
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for link in sorted(links, key=lambda l: catalog[l.productoEncipharmId].nombre if l.productoEncipharmId in catalog else ""):
        if link.productoEncipharmId in catalog:
            result[link.productoCompetenciaId].append(
                {"id": link.productoEncipharmId, "nombre": catalog[link.productoEncipharmId].nombre}
            )
    return result


def _serialize_products(db: Session, products: list[ProductoCompetencia]) -> list[dict[str, Any]]:
    ids = [p.id for p in products]
    latest = _latest_approved(db, ids)
    equivalentes = _equivalentes(db, ids)
    names = _user_names(db, list(latest.values()))
    return [
        {
            "id": p.id, "competidor": p.competidor, "nombre": p.nombre,
            "principiosActivos": _principios(p.principiosActivos), "concentracion": p.concentracion,
            "presentacion": p.presentacion, "unidadMedida": p.unidadMedida,
            "cantidadPresentacion": float(p.cantidadPresentacion), "categoria": p.categoria, "especie": p.especie,
            "registroSag": p.registroSag, "equivalentes": equivalentes.get(p.id, []),
            "ultimoPrecio": _price_dict(latest[p.id], p, names) if p.id in latest else None,
            "createdAt": p.createdAt, "updatedAt": p.updatedAt,
        }
        for p in products
    ]


def list_productos(
    db: Session, *, competidor: str | None, categoria: str | None, principio: str | None,
    search: str | None, page: int, page_size: int,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    query = db.query(ProductoCompetencia)
    if competidor:
        query = query.filter(func.lower(ProductoCompetencia.competidor) == competidor.strip().lower())
    if categoria:
        query = query.filter(func.lower(ProductoCompetencia.categoria) == categoria.strip().lower())
    if principio:
        query = query.filter(ProductoCompetencia.principiosActivos.ilike(_like(principio.strip()), escape="\\"))
    if search:
        pattern = _like(search.strip())
        query = query.filter(or_(
            ProductoCompetencia.nombre.ilike(pattern, escape="\\"),
            ProductoCompetencia.competidor.ilike(pattern, escape="\\"),
        ))
    total = query.count()
    products = (
        query.order_by(ProductoCompetencia.competidor, ProductoCompetencia.nombre, ProductoCompetencia.id)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    return {"items": _serialize_products(db, products), "total": total, "page": page, "pageSize": page_size}


def get_producto_or_404(db: Session, product_id: str) -> ProductoCompetencia:
    product = db.query(ProductoCompetencia).filter(ProductoCompetencia.id == product_id).first()
    if product is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Producto de la competencia no encontrado")
    return product


def get_producto_detalle(db: Session, product_id: str, user: dict) -> dict[str, Any]:
    product = get_producto_or_404(db, product_id)
    query = db.query(PrecioCompetencia).filter(PrecioCompetencia.productoId == product.id)
    if user["rol"] == "vendedor":  # los pendientes/descartados de otros no se ven
        query = query.filter(or_(PrecioCompetencia.estado == "aprobado", PrecioCompetencia.reportadoPor == user["uid"]))
    prices = query.order_by(PrecioCompetencia.fechaPrecio.desc(), PrecioCompetencia.createdAt.desc()).all()
    names = _user_names(db, prices)
    data = _serialize_products(db, [product])[0]
    data["historial"] = [_price_dict(p, product, names) for p in prices]
    return data


def _assert_not_duplicate(db: Session, competidor: str, nombre: str, presentacion: str | None, exclude_id: str | None = None) -> None:
    query = db.query(ProductoCompetencia.id).filter(
        func.lower(ProductoCompetencia.competidor) == competidor.lower(),
        func.lower(ProductoCompetencia.nombre) == nombre.lower(),
    )
    query = query.filter(
        func.lower(ProductoCompetencia.presentacion) == presentacion.lower()
        if presentacion else ProductoCompetencia.presentacion.is_(None)
    )
    if exclude_id:
        query = query.filter(ProductoCompetencia.id != exclude_id)
    if query.first():
        raise _error(status.HTTP_409_CONFLICT, "Ese producto de la competencia ya esta registrado")


def create_producto(db: Session, payload, user: dict) -> dict[str, Any]:
    data = payload.model_dump()
    _assert_not_duplicate(db, data["competidor"], data["nombre"], data.get("presentacion"))
    product = ProductoCompetencia(creadoPor=user["uid"])
    _apply(product, data)
    db.add(product)
    db.commit()
    return _serialize_products(db, [product])[0]


def update_producto(db: Session, product_id: str, payload) -> dict[str, Any]:
    product = get_producto_or_404(db, product_id)
    data = payload.model_dump(exclude_unset=True)
    for required in ("competidor", "nombre", "unidadMedida", "cantidadPresentacion"):
        if required in data and data[required] is None:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{required} no puede quedar vacio")
    competidor = data.get("competidor", product.competidor)
    nombre = data.get("nombre", product.nombre)
    presentacion = data["presentacion"] if "presentacion" in data else product.presentacion
    _assert_not_duplicate(db, competidor, nombre, presentacion, exclude_id=product.id)
    _apply(product, data)
    db.commit()
    return _serialize_products(db, [product])[0]


def delete_producto(db: Session, product_id: str) -> None:
    product = get_producto_or_404(db, product_id)
    # Firestore no tiene cascadas: se borran los hijos a mano.
    db.query(PrecioCompetencia).filter(PrecioCompetencia.productoId == product.id).delete()
    db.query(EquivalenciaProducto).filter(EquivalenciaProducto.productoCompetenciaId == product.id).delete()
    db.delete(product)
    db.commit()


def set_equivalencias(db: Session, product_id: str, encipharm_ids: list[str]) -> dict[str, Any]:
    product = get_producto_or_404(db, product_id)
    ids = list(dict.fromkeys(encipharm_ids))
    found = {r[0] for r in db.query(ProductoEncipharm.id).filter(ProductoEncipharm.id.in_(ids)).all()} if ids else set()
    missing = [i for i in ids if i not in found]
    if missing:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Hay productos Encipharm que no existen")
    db.query(EquivalenciaProducto).filter(EquivalenciaProducto.productoCompetenciaId == product.id).delete()
    db.add_all(
        EquivalenciaProducto(id=f"{product.id}:{i}", productoCompetenciaId=product.id, productoEncipharmId=i) for i in ids
    )
    db.commit()
    return _serialize_products(db, [product])[0]


# ── Precios ──────────────────────────────────────────────────────────────────

def report_price(db: Session, product_id: str, payload, user: dict) -> dict[str, Any]:
    product = get_producto_or_404(db, product_id)
    data = payload.model_dump()
    if data.get("clienteId"):
        assert_cliente_visible(db, data["clienteId"], user)
    data["fechaPrecio"] = data["fechaPrecio"] or date.today()
    reviewer_is_reporter = user["rol"] in {"supervisor", "admin"}
    price = PrecioCompetencia(
        productoId=product.id, reportadoPor=user["uid"], **data,
        estado="aprobado" if reviewer_is_reporter else "pendiente",
        revisadoPor=user["uid"] if reviewer_is_reporter else None,
        revisadoAt=datetime.now(timezone.utc) if reviewer_is_reporter else None,
    )
    db.add(price)
    db.commit()
    return _price_dict(price, product, _user_names(db, [price]))


def list_prices(db: Session, *, estado: str | None, producto_id: str | None, page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    query = db.query(PrecioCompetencia)
    if estado:
        query = query.filter(PrecioCompetencia.estado == estado)
    if producto_id:
        query = query.filter(PrecioCompetencia.productoId == producto_id)
    total = query.count()
    prices = (
        query.order_by(PrecioCompetencia.createdAt.desc(), PrecioCompetencia.id)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    products = {p.id: p for p in db.query(ProductoCompetencia).filter(ProductoCompetencia.id.in_({x.productoId for x in prices})).all()} if prices else {}
    names = _user_names(db, prices)
    items = [_price_dict(p, products[p.productoId], names, with_product=True) for p in prices]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def review_price(db: Session, price_id: str, approve: bool, user: dict) -> dict[str, Any]:
    price = db.query(PrecioCompetencia).filter(PrecioCompetencia.id == price_id).first()
    if price is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Reporte de precio no encontrado")
    if price.estado != "pendiente":
        raise _error(status.HTTP_409_CONFLICT, f"El reporte ya esta {price.estado}")
    price.estado = "aprobado" if approve else "descartado"
    price.revisadoPor = user["uid"]
    price.revisadoAt = datetime.now(timezone.utc)
    db.commit()
    product = get_producto_or_404(db, price.productoId)
    return _price_dict(price, product, _user_names(db, [price]), with_product=True)


# ── Comparativa y resumen ────────────────────────────────────────────────────

def _difference(enci: ProductoEncipharm, comp: ProductoCompetencia, price: PrecioCompetencia | None) -> tuple[float | None, float | None, str | None]:
    """(precio por unidad del competidor, diferencia %, motivo si no se puede calcular)."""
    if price is None:
        return None, None, "Sin precio aprobado de la competencia"
    comp_ppu = _ppu(price.precio, comp.cantidadPresentacion)
    if enci.precioLista is None:
        return comp_ppu, None, "El producto Encipharm no tiene precio de lista"
    if enci.unidadMedida != comp.unidadMedida:
        return comp_ppu, None, "Unidades de medida distintas"
    if enci.moneda != price.moneda:
        return comp_ppu, None, "Monedas distintas"
    return comp_ppu, round((_ppu(enci.precioLista, enci.cantidadPresentacion) - comp_ppu) / comp_ppu * 100, 2), None


def build_comparativa(db: Session, encipharm_id: str) -> dict[str, Any]:
    enci = get_encipharm_or_404(db, encipharm_id)
    links = db.query(EquivalenciaProducto).filter(EquivalenciaProducto.productoEncipharmId == enci.id).all()
    comps = (
        db.query(ProductoCompetencia)
        .filter(ProductoCompetencia.id.in_({link.productoCompetenciaId for link in links}))
        .order_by(ProductoCompetencia.competidor, ProductoCompetencia.nombre)
        .all()
        if links else []
    )
    latest = _latest_approved(db, [c.id for c in comps])
    rows = []
    for comp in comps:
        price = latest.get(comp.id)
        comp_ppu, diff, reason = _difference(enci, comp, price)
        rows.append({
            "productoCompetenciaId": comp.id, "competidor": comp.competidor, "nombre": comp.nombre,
            "presentacion": comp.presentacion, "principiosActivos": _principios(comp.principiosActivos),
            "concentracion": comp.concentracion, "registroSag": comp.registroSag, "precioPorUnidad": comp_ppu,
            "moneda": price.moneda if price else None, "fechaPrecio": price.fechaPrecio if price else None,
            "fuente": price.fuente if price else None, "diferenciaPct": diff, "motivoSinDiferencia": reason,
        })
    return {"productoEncipharm": serialize_encipharm(enci), "equivalentes": rows}


def build_resumen(db: Session) -> dict[str, Any]:
    # shortcut: se agrupa en memoria sobre todo el catalogo; subir a SQL si pasa de unos miles de productos.
    products = db.query(ProductoCompetencia).all()
    latest = _latest_approved(db, [p.id for p in products])
    enci_by_comp: dict[str, list[ProductoEncipharm]] = defaultdict(list)
    links = db.query(EquivalenciaProducto).all()
    catalog = _encipharm_by_id(db, {link.productoEncipharmId for link in links})
    for link in links:
        if link.productoEncipharmId in catalog:
            enci_by_comp[link.productoCompetenciaId].append(catalog[link.productoEncipharmId])

    def summarize(key_of) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(lambda: {"ppu": [], "diff": []})
        for p in products:
            price = latest.get(p.id)
            if price is None:
                continue
            group = groups[(key_of(p), p.unidadMedida, price.moneda)]
            group["ppu"].append(_ppu(price.precio, p.cantidadPresentacion))
            for enci in enci_by_comp.get(p.id, []):
                diff = _difference(enci, p, price)[1]
                if diff is not None:
                    group["diff"].append(diff)
        return [
            {
                "clave": key, "unidadMedida": unit, "moneda": currency, "productos": len(g["ppu"]),
                "precioPromedioPorUnidad": round(sum(g["ppu"]) / len(g["ppu"]), 4),
                "diferenciaPromedioPct": round(sum(g["diff"]) / len(g["diff"]), 2) if g["diff"] else None,
            }
            for (key, unit, currency), g in sorted(groups.items())
        ]

    return {
        "porCategoria": summarize(lambda p: p.categoria or "Sin categoria"),
        "porCompetidor": summarize(lambda p: p.competidor),
        "productosSinPrecio": sum(1 for p in products if p.id not in latest),
    }


def precios_para_chat(db: Session, texto: str, limit: int = 5) -> list[dict[str, Any]]:
    """Productos que coinciden con el texto y su ultimo precio aprobado, para la herramienta del chat."""
    texto = texto.strip()
    if not texto:
        return []
    pattern = _like(texto)
    products = (
        db.query(ProductoCompetencia)
        .filter(or_(
            ProductoCompetencia.nombre.ilike(pattern, escape="\\"),
            ProductoCompetencia.principiosActivos.ilike(pattern, escape="\\"),
        ))
        .order_by(ProductoCompetencia.competidor, ProductoCompetencia.nombre).limit(limit * 3).all()
    )
    latest = _latest_approved(db, [p.id for p in products])
    return [
        {
            "competidor": p.competidor, "nombre": p.nombre, "presentacion": p.presentacion,
            "precio": float(latest[p.id].precio), "moneda": latest[p.id].moneda,
            "precioPorUnidad": _ppu(latest[p.id].precio, p.cantidadPresentacion), "unidadMedida": p.unidadMedida,
            "fechaPrecio": latest[p.id].fechaPrecio.isoformat(), "fuente": latest[p.id].fuente,
        }
        for p in products if p.id in latest
    ][:limit]


def ficha_competencia(db: Session, registro: str) -> dict[str, Any]:
    """Precios aprobados y equivalente Encipharm de los productos con ese registro SAG (ficha de Intel)."""
    products = db.query(ProductoCompetencia).filter(ProductoCompetencia.registroSag == registro).all()
    latest = _latest_approved(db, [p.id for p in products])
    equivalentes = _equivalentes(db, [p.id for p in products])
    precios = [
        {
            "fuente": f"{p.competidor} · {p.presentacion or p.nombre} ({latest[p.id].fechaPrecio.isoformat()})",
            "precio": float(latest[p.id].precio), "moneda": latest[p.id].moneda,
            "precioPorUnidad": _ppu(latest[p.id].precio, p.cantidadPresentacion), "unidadMedida": p.unidadMedida,
            "fecha": latest[p.id].fechaPrecio.isoformat(),
        }
        for p in products if p.id in latest
    ]
    nombres = sorted({e["nombre"] for p in products for e in equivalentes.get(p.id, [])})
    return {"precios": precios, "equivalente_encipharm": {"nombre": ", ".join(nombres)} if nombres else None}
