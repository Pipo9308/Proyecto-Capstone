"""RQ-04: productos de la competencia, historial de precios, comparativa y catalogo Encipharm.

Permisos (RF-04.09): el vendedor consulta, registra productos y reporta precios; supervisor y admin
editan, definen equivalencias y aprueban; solo el admin borra.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from app.core.odm import Session

from app.core.auth import require_role
from app.core.db import get_db
from app.models.competencia_productos import (
    Comparativa,
    EquivalenciasRequest,
    PrecioCreate,
    PrecioResponse,
    PreciosPagina,
    ProductoCompetenciaCreate,
    ProductoCompetenciaDetalle,
    ProductoCompetenciaResponse,
    ProductoCompetenciaUpdate,
    ProductoEncipharmCreate,
    ProductoEncipharmResponse,
    ProductoEncipharmUpdate,
    ProductosCompetenciaPagina,
    Resumen,
)
from app.services import competencia_productos as svc

router = APIRouter(prefix="/competencia", tags=["Competencia"])


@router.get("/productos", response_model=ProductosCompetenciaPagina)
async def get_productos(
    competidor: str | None = None,
    categoria: str | None = None,
    principio: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=25, ge=1, le=svc.MAX_PAGE_SIZE),
    _: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
):
    return svc.list_productos(
        db, competidor=competidor, categoria=categoria, principio=principio, search=q, page=page, page_size=pageSize,
    )


@router.post("/productos", response_model=ProductoCompetenciaResponse, status_code=status.HTTP_201_CREATED)
async def post_producto(
    payload: ProductoCompetenciaCreate, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db),
):
    return svc.create_producto(db, payload, user)


@router.get("/productos/{product_id}", response_model=ProductoCompetenciaDetalle)
async def get_producto(product_id: str, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)):
    return svc.get_producto_detalle(db, product_id, user)


@router.patch("/productos/{product_id}", response_model=ProductoCompetenciaResponse)
async def patch_producto(
    product_id: str, payload: ProductoCompetenciaUpdate, _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db),
):
    return svc.update_producto(db, product_id, payload)


@router.delete("/productos/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_producto(product_id: str, _: dict = Depends(require_role("admin")), db: Session = Depends(get_db)):
    svc.delete_producto(db, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/productos/{product_id}/equivalentes", response_model=ProductoCompetenciaResponse)
async def put_equivalentes(
    product_id: str, payload: EquivalenciasRequest, _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db),
):
    return svc.set_equivalencias(db, product_id, payload.encipharmIds)


@router.post("/productos/{product_id}/precios", response_model=PrecioResponse, status_code=status.HTTP_201_CREATED)
async def post_precio(
    product_id: str, payload: PrecioCreate, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db),
):
    return svc.report_price(db, product_id, payload, user)


@router.get("/precios", response_model=PreciosPagina)
async def get_precios(
    estado: Literal["pendiente", "aprobado", "descartado"] | None = "pendiente",
    productoId: str | None = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=25, ge=1, le=svc.MAX_PAGE_SIZE),
    _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db),
):
    return svc.list_prices(db, estado=estado, producto_id=productoId, page=page, page_size=pageSize)


@router.post("/precios/{price_id}/aprobar", response_model=PrecioResponse)
async def aprobar_precio(price_id: str, user: dict = Depends(require_role("supervisor")), db: Session = Depends(get_db)):
    return svc.review_price(db, price_id, True, user)


@router.post("/precios/{price_id}/descartar", response_model=PrecioResponse)
async def descartar_precio(price_id: str, user: dict = Depends(require_role("supervisor")), db: Session = Depends(get_db)):
    return svc.review_price(db, price_id, False, user)


@router.get("/comparativa", response_model=Comparativa)
async def get_comparativa(
    productoEncipharmId: str, _: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db),
):
    return svc.build_comparativa(db, productoEncipharmId)


@router.get("/resumen", response_model=Resumen)
async def get_resumen(_: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)):
    return svc.build_resumen(db)


@router.get("/catalogo", response_model=list[ProductoEncipharmResponse])
async def get_catalogo(
    q: str | None = Query(default=None, max_length=100),
    incluirInactivos: bool = False,
    _: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
):
    return svc.list_encipharm(db, search=q, solo_activos=not incluirInactivos)


@router.post("/catalogo", response_model=ProductoEncipharmResponse, status_code=status.HTTP_201_CREATED)
async def post_catalogo(
    payload: ProductoEncipharmCreate, _: dict = Depends(require_role("supervisor")), db: Session = Depends(get_db),
):
    return svc.create_encipharm(db, payload)


@router.patch("/catalogo/{product_id}", response_model=ProductoEncipharmResponse)
async def patch_catalogo(
    product_id: str, payload: ProductoEncipharmUpdate, _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db),
):
    return svc.update_encipharm(db, product_id, payload)


@router.delete("/catalogo/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalogo(product_id: str, _: dict = Depends(require_role("admin")), db: Session = Depends(get_db)):
    svc.delete_encipharm(db, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
