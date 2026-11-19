"""Seed demo commercial data for vendedor.demo@enci.cl.

Run from Backend with:
    uv run python scripts/seed_max_wellq_demo.py --apply

The script is idempotent: it writes deterministic document IDs tagged with
``max-wellq-demo-20260615`` and keeps existing unrelated data untouched.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

from app.core.odm import Session
from app.core.db import SessionLocal
from app.core.security import get_password_hash
from app.models_sql.user import User
from app.models_sql.cliente import Cliente
from app.models_sql.comercial import Opportunity, Proposal, Interaction

TARGET_EMAIL = "vendedor.demo@enci.cl"
SEED_TAG = "max-wellq-demo-20260615"
# Solo local: en una base online definir DEMO_PASSWORD con una clave propia.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "password123")


CLIENTS = [
    ("max-wellq-cliente-01", "Carolina Medina", "Agrovet Los Andes", "carolina.medina@agrovetandes.cl", "22334455", "Avicola", "Region Metropolitana", "En proceso", "nuevo", "Prospeccion nutricional broilers", 18_500_000, 20, "enviada"),
    ("max-wellq-cliente-02", "Ignacio Fuentes", "Planteles BioSur", "ignacio.fuentes@biosur.cl", "22334456", "Porcino", "Biobio", "En proceso", "contactado", "Validacion sanitaria reproductoras", 27_000_000, 35, "borrador"),
    ("max-wellq-cliente-03", "Valentina Rojas", "Clinica Veterinaria Andes", "valentina.rojas@vetandes.cl", "22334457", "Clinica", "Valparaiso", "Completado", "cotizacion", "Programa anual farmacos clinicos", 9_800_000, 55, "enviada"),
    ("max-wellq-cliente-04", "Pablo Araya", "Lecheria Santa Clara", "pablo.araya@santaclara.cl", "22334458", "Bovino", "Los Lagos", "En proceso", "negociacion", "Tratamiento metabolico temporada alta", 34_200_000, 72, "enviada"),
    ("max-wellq-cliente-05", "Francisca Soto", "AquaGen Patagonia", "francisca.soto@aquagen.cl", "22334459", "Acuicola", "Magallanes", "Completado", "ganado", "Abastecimiento preventivo centros marinos", 41_000_000, 100, "aceptada"),
    ("max-wellq-cliente-06", "Matias Vera", "Ganadera El Roble", "matias.vera@elroble.cl", "22334460", "Bovino", "Maule", "En proceso", "contactado", "Plan antiparasitario rodeo premium", 16_700_000, 40, "borrador"),
    ("max-wellq-cliente-07", "Daniela Morales", "Avicola Horizonte", "daniela.morales@horizonte.cl", "22334461", "Avicola", "Coquimbo", "En proceso", "cotizacion", "Suplementacion ponedoras fase invierno", 22_400_000, 60, "enviada"),
    ("max-wellq-cliente-08", "Sebastian Pino", "Porcinos San Rafael", "sebastian.pino@sanrafael.cl", "22334462", "Porcino", "O'Higgins", "Inactivo", "perdido", "Recuperacion de cuenta bioseguridad", 12_900_000, 10, "rechazada"),
    ("max-wellq-cliente-09", "Camila Torres", "Equisalud Centro", "camila.torres@equisalud.cl", "22334463", "Equino", "Region Metropolitana", "En proceso", "nuevo", "Linea premium medicina deportiva", 7_600_000, 15, "borrador"),
    ("max-wellq-cliente-10", "Rodrigo Salinas", "Distribuidora VetNorte", "rodrigo.salinas@vetnorte.cl", "22334464", "Distribucion", "Antofagasta", "En proceso", "negociacion", "Acuerdo marco zona norte", 58_000_000, 68, "enviada"),
]


def find_or_create_user(db: Session) -> User:
    user = db.query(User).filter(User.email == TARGET_EMAIL).first()
    if not user:
        now = datetime.now(timezone.utc)
        user = User(
            id="seed-user-max",
            email=TARGET_EMAIL,
            password_hash=get_password_hash(DEMO_PASSWORD),
            nombre="Max Wellq",
            rol="vendedor",
            cargo="Vendedor",
            rango="Vendedor",
            zona="Zona centro",
            appMovil=True,
            webApp=True,
            activo=True,
            theme="dark",
            language="es",
            createdAt=now,
            updatedAt=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.password_hash = get_password_hash(DEMO_PASSWORD)
        db.commit()
    return user


def seed_data(db: Session, user: User, apply: bool) -> int:
    now = datetime.now(timezone.utc)
    uid = user.id
    docs_prepared = 0

    for index, row in enumerate(CLIENTS, start=1):
        (
            client_id,
            nombre,
            empresa,
            email,
            telefono,
            rubro,
            region,
            estado,
            etapa,
            titulo,
            valor,
            probabilidad,
            propuesta_estado,
        ) = row
        created_at = now - timedelta(days=32 - index * 2)
        opportunity_id = f"max-wellq-oportunidad-{index:02d}"
        proposal_id = f"max-wellq-propuesta-{index:02d}"
        interaction_id = f"max-wellq-interaccion-{index:02d}"
        discount = 4 if propuesta_estado == "aceptada" else 7 if propuesta_estado == "rechazada" else 0
        
        docs_prepared += 4
        
        if apply:
            # Upsert Cliente
            cliente = db.query(Cliente).filter(Cliente.id == client_id).first()
            if not cliente:
                cliente = Cliente(id=client_id)
            cliente.nombre = nombre
            cliente.empresa = empresa
            cliente.email = email
            cliente.telefono = telefono
            cliente.rubro = rubro
            cliente.region = region
            cliente.estado = estado
            cliente.vendedorUid = uid
            cliente.ownerUid = uid
            cliente.createdAt = created_at
            cliente.updatedAt = now
            db.add(cliente)

            # Upsert Oportunidad
            opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
            if not opp:
                opp = Opportunity(id=opportunity_id)
            opp.clienteId = client_id
            opp.titulo = titulo
            opp.etapa = etapa
            opp.valorEstimado = valor
            opp.probabilidad = probabilidad
            opp.descripcion = f"Oportunidad seed para {empresa} asociada a {TARGET_EMAIL}."
            opp.vendedorUid = uid
            opp.createdAt = created_at + timedelta(days=1)
            opp.updatedAt = now
            db.add(opp)

            # Upsert Propuesta
            prop = db.query(Proposal).filter(Proposal.id == proposal_id).first()
            if not prop:
                prop = Proposal(id=proposal_id)
            prop.clienteId = client_id
            prop.oportunidadId = opportunity_id
            prop.titulo = f"Propuesta comercial - {titulo}"
            prop.montoNeto = valor
            prop.descuentoPct = discount
            prop.estado = propuesta_estado
            prop.notas = "Registro demo para dashboard, pipeline y proyecciones."
            prop.vendedorUid = uid
            prop.createdAt = created_at + timedelta(days=2)
            prop.updatedAt = now
            db.add(prop)

            # Upsert Interaccion
            inter = db.query(Interaction).filter(Interaction.id == interaction_id).first()
            if not inter:
                inter = Interaction(id=interaction_id)
            inter.clienteId = client_id
            inter.tipo = "reunion" if index % 3 == 0 else "llamada"
            inter.fecha = created_at + timedelta(days=3)
            inter.resumen = f"Seguimiento comercial con {empresa} para revisar avance de {titulo}."
            inter.resultado = "Pendiente de siguiente accion" if etapa not in {"ganado", "perdido"} else "Ciclo cerrado"
            inter.proximaAccion = "Agendar revision de propuesta" if etapa in {"cotizacion", "negociacion"} else "Actualizar estado CRM"
            inter.vendedorUid = uid
            inter.createdAt = created_at + timedelta(days=3)
            inter.updatedAt = now
            db.add(inter)
            
            db.commit()

    return docs_prepared


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Max Wellq demo commercial data.")
    parser.add_argument("--apply", action="store_true", help="Write documents to Database.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = find_or_create_user(db)
        print(f"Target: {TARGET_EMAIL} ({user.id})")
        
        if not args.apply:
            docs_prepared = seed_data(db, user, apply=False)
            print(f"Documents prepared: {docs_prepared}")
            print("Dry run only. Re-run with --apply to write data.")
            return

        docs_prepared = seed_data(db, user, apply=True)
        print(f"Documents written: {docs_prepared}")
        print(f"Seed applied with tag {SEED_TAG}.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
