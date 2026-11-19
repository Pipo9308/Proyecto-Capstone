from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from app.core.odm import Session

from app.models.comercial import (
    InteractionCreate,
    normalize_opportunity_stage,
    normalize_proposal_status,
    OpportunityCreate,
    ProposalCreate,
)
from app.models_sql.comercial import Interaction, Opportunity, Proposal
from app.models_sql.cliente import Cliente
from app.services import notificaciones


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _proposal_amounts(monto_neto: float, descuento_pct: float) -> tuple[float, float]:
    monto_descuento = round(monto_neto * (descuento_pct / 100), 2)
    monto_total = round(monto_neto - monto_descuento, 2)
    return monto_descuento, monto_total

def _interaction_model_to_dict(interaction: Interaction) -> dict[str, Any]:
    return {
        "id": interaction.id,
        "clienteId": interaction.clienteId,
        "tipo": interaction.tipo,
        "fecha": interaction.fecha,
        "resumen": interaction.resumen,
        "resultado": interaction.resultado,
        "proximaAccion": interaction.proximaAccion,
        "vendedorUid": interaction.vendedorUid,
        "createdAt": interaction.createdAt,
        "updatedAt": interaction.updatedAt,
    }

def _opportunity_model_to_dict(opportunity: Opportunity) -> dict[str, Any]:
    return {
        "id": opportunity.id,
        "clienteId": opportunity.clienteId,
        "titulo": opportunity.titulo,
        "descripcion": opportunity.descripcion,
        "etapa": opportunity.etapa,
        "valorEstimado": opportunity.valorEstimado,
        "probabilidad": opportunity.probabilidad,
        "vendedorUid": opportunity.vendedorUid,
        "createdAt": opportunity.createdAt,
        "updatedAt": opportunity.updatedAt,
    }

def _proposal_model_to_dict(proposal: Proposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "clienteId": proposal.clienteId,
        "oportunidadId": proposal.oportunidadId,
        "titulo": proposal.titulo,
        "montoNeto": proposal.montoNeto,
        "descuentoPct": proposal.descuentoPct,
        "estado": proposal.estado,
        "notas": proposal.notas,
        "vendedorUid": proposal.vendedorUid,
        "montoDescuento": proposal.montoDescuento,
        "montoTotal": proposal.montoTotal,
        "createdAt": proposal.createdAt,
        "updatedAt": proposal.updatedAt,
    }


def assert_cliente_visible(db: Session, cliente_id: str, user: dict) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.estado != "Eliminado").first()
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    
    if user["rol"] == "vendedor":
        user_uid = user["uid"]
        if cliente.vendedorUid != user_uid and cliente.ownerUid != user_uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para este cliente",
            )
    return cliente


def list_interactions(db: Session, user: dict, cliente_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = db.query(Interaction)
    if cliente_id:
        query = query.filter(Interaction.clienteId == cliente_id)
    if user["rol"] == "vendedor":
        query = query.filter(Interaction.vendedorUid == user["uid"])
        
    query = query.order_by(Interaction.fecha.desc(), Interaction.createdAt.desc()).limit(limit)
    return [_interaction_model_to_dict(i) for i in query.all()]


def create_interaction(db: Session, payload: InteractionCreate, user: dict) -> dict[str, Any]:
    assert_cliente_visible(db, payload.clienteId, user)
    
    data = payload.model_dump()
    data["vendedorUid"] = user["uid"]
    data["fecha"] = data.get("fecha") or _now()
    
    new_interaction = Interaction(**data)
    db.add(new_interaction)
    db.commit()
    db.refresh(new_interaction)
    
    return _interaction_model_to_dict(new_interaction)


def list_opportunities(
    db: Session,
    user: dict,
    cliente_id: str | None = None,
    etapa: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = db.query(Opportunity)
    if cliente_id:
        query = query.filter(Opportunity.clienteId == cliente_id)
    if etapa:
        etapa_normalized = normalize_opportunity_stage(etapa)
        query = query.filter(Opportunity.etapa == etapa_normalized)
    if user["rol"] == "vendedor":
        query = query.filter(Opportunity.vendedorUid == user["uid"])
        
    query = query.order_by(Opportunity.updatedAt.desc()).limit(limit)
    return [_opportunity_model_to_dict(o) for o in query.all()]


def create_opportunity(db: Session, payload: OpportunityCreate, user: dict) -> dict[str, Any]:
    assert_cliente_visible(db, payload.clienteId, user)
    
    data = payload.model_dump()
    data["vendedorUid"] = user["uid"]
    
    new_opportunity = Opportunity(**data)
    db.add(new_opportunity)
    db.commit()
    db.refresh(new_opportunity)
    
    return _opportunity_model_to_dict(new_opportunity)


def update_opportunity(db: Session, opportunity_id: str, changes: dict[str, Any], user: dict) -> dict[str, Any]:
    opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oportunidad no encontrada")
        
    if user["rol"] not in ["admin", "supervisor"] and opportunity.vendedorUid != user["uid"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para esta oportunidad")
        
    clean_changes = {key: value for key, value in changes.items() if value is not None}
    
    for key, value in clean_changes.items():
        if hasattr(opportunity, key):
            setattr(opportunity, key, value)
            
    opportunity.updatedAt = _now()
    db.commit()
    db.refresh(opportunity)
    
    return _opportunity_model_to_dict(opportunity)


def get_opportunity_detail(db: Session, opportunity_id: str, user: dict) -> dict[str, Any]:
    opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oportunidad no encontrada")
        
    if user["rol"] not in ["admin", "supervisor"] and opportunity.vendedorUid != user["uid"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para esta oportunidad")
        
    cliente_id = opportunity.clienteId
    
    return {
        "oportunidad": _opportunity_model_to_dict(opportunity),
        "interacciones": list_interactions(db, user=user, cliente_id=cliente_id, limit=25),
        "propuestas": [
            p for p in list_proposals(db, user=user, cliente_id=cliente_id, limit=100)
            if p.get("oportunidadId") == opportunity_id
        ],
    }


def list_proposals(
    db: Session,
    user: dict,
    cliente_id: str | None = None,
    estado: str | None = None,
    oportunidad_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = db.query(Proposal)
    if cliente_id:
        query = query.filter(Proposal.clienteId == cliente_id)
    if estado:
        estado_normalized = normalize_proposal_status(estado)
        query = query.filter(Proposal.estado == estado_normalized)
    if oportunidad_id:
        query = query.filter(Proposal.oportunidadId == oportunidad_id)
    if user["rol"] == "vendedor":
        query = query.filter(Proposal.vendedorUid == user["uid"])
        
    query = query.order_by(Proposal.updatedAt.desc()).limit(limit)
    return [_proposal_model_to_dict(p) for p in query.all()]


def _ensure_proposal_create_allowed(user: dict) -> None:
    if user["rol"] == "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor solo puede consultar y aprobar propuestas",
        )


def _ensure_proposal_update_allowed(proposal: Proposal, changes: dict[str, Any], user: dict) -> None:
    if user["rol"] == "admin":
        return
    if user["rol"] == "supervisor":
        if set(changes.keys()) == {"estado"} and changes.get("estado") == "aceptada":
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor solo puede aprobar propuestas",
        )
    if proposal.vendedorUid != user["uid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta propuesta",
        )


def create_proposal(db: Session, payload: ProposalCreate, user: dict) -> dict[str, Any]:
    _ensure_proposal_create_allowed(user)
    assert_cliente_visible(db, payload.clienteId, user)
    
    opportunity = db.query(Opportunity).filter(Opportunity.id == payload.oportunidadId).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oportunidad no encontrada")
        
    if user["rol"] not in ["admin", "supervisor"] and opportunity.vendedorUid != user["uid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta oportunidad",
        )
    if opportunity.clienteId != payload.clienteId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La oportunidad no pertenece al cliente indicado",
        )
        
    data = payload.model_dump()
    data["vendedorUid"] = user["uid"]
    
    new_proposal = Proposal(**data)
    db.add(new_proposal)
    db.commit()
    db.refresh(new_proposal)
    
    return _proposal_model_to_dict(new_proposal)


def update_proposal(db: Session, proposal_id: str, changes: dict[str, Any], user: dict) -> dict[str, Any]:
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propuesta no encontrada")
        
    clean_changes = {key: value for key, value in changes.items() if value is not None}
    _ensure_proposal_update_allowed(proposal, clean_changes, user)
    previous_state = proposal.estado

    for key, value in clean_changes.items():
        if hasattr(proposal, key):
            setattr(proposal, key, value)

    proposal.updatedAt = _now()
    if proposal.estado != previous_state and proposal.vendedorUid != user["uid"]:
        notificaciones.crear(
            db, proposal.vendedorUid, notificaciones.TIPO_PROPUESTA,
            f"Tu propuesta «{proposal.titulo}» pasó a {proposal.estado}",
            mensaje=f"Antes estaba {previous_state}. Cambio hecho por {user.get('nombre') or 'un supervisor'}.",
            enlace="/propuestas", referencia=f"{proposal.id}:{proposal.estado}:{proposal.updatedAt.isoformat()}",
        )
    db.commit()
    db.refresh(proposal)
    
    return _proposal_model_to_dict(proposal)
