from fastapi import APIRouter, Depends, Query

from app.core.auth import require_role
from app.models.comercial import (
    InteractionCreate,
    InteractionResponse,
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunityResponse,
    OpportunityUpdate,
    ProposalCreate,
    ProposalResponse,
    ProposalUpdate,
)
from app.services.comercial import (
    create_interaction,
    create_opportunity,
    create_proposal,
    get_opportunity_detail,
    list_interactions,
    list_opportunities,
    list_proposals,
    update_opportunity,
    update_proposal,
)
from app.core.db import get_db
from app.core.odm import Session


router = APIRouter(tags=["Flujo comercial"])


@router.get("/interacciones", response_model=list[InteractionResponse])
async def get_interacciones(
    cliente_id: str | None = Query(default=None, alias="clienteId", max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return list_interactions(db, user=user, cliente_id=cliente_id, limit=limit)


@router.post("/interacciones", response_model=InteractionResponse)
async def post_interaccion(
    payload: InteractionCreate,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return create_interaction(db, payload, user)


@router.get("/oportunidades", response_model=list[OpportunityResponse])
async def get_oportunidades(
    cliente_id: str | None = Query(default=None, alias="clienteId", max_length=128),
    etapa: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return list_opportunities(db, user=user, cliente_id=cliente_id, etapa=etapa, limit=limit)


@router.get("/oportunidades/{oportunidad_id}/detalle", response_model=OpportunityDetailResponse)
async def get_oportunidad_detalle(
    oportunidad_id: str,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return get_opportunity_detail(db, oportunidad_id, user)


@router.post("/oportunidades", response_model=OpportunityResponse)
async def post_oportunidad(
    payload: OpportunityCreate,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return create_opportunity(db, payload, user)


@router.patch("/oportunidades/{oportunidad_id}", response_model=OpportunityResponse)
async def patch_oportunidad(
    oportunidad_id: str,
    payload: OpportunityUpdate,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return update_opportunity(
        db,
        oportunidad_id,
        payload.model_dump(exclude_unset=True),
        user,
    )


@router.get("/propuestas", response_model=list[ProposalResponse])
async def get_propuestas(
    cliente_id: str | None = Query(default=None, alias="clienteId", max_length=128),
    estado: str | None = Query(default=None, max_length=64),
    oportunidad_id: str | None = Query(default=None, alias="oportunidadId", max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return list_proposals(
        db,
        user=user,
        cliente_id=cliente_id,
        estado=estado,
        oportunidad_id=oportunidad_id,
        limit=limit,
    )


@router.post("/propuestas", response_model=ProposalResponse)
async def post_propuesta(
    payload: ProposalCreate,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return create_proposal(db, payload, user)


@router.patch("/propuestas/{propuesta_id}", response_model=ProposalResponse)
async def patch_propuesta(
    propuesta_id: str,
    payload: ProposalUpdate,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return update_proposal(
        db,
        propuesta_id,
        payload.model_dump(exclude_unset=True),
        user,
    )
