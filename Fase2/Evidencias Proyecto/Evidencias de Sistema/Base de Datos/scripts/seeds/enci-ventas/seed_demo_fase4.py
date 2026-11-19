"""Datos de prueba para las pantallas nuevas (competencia, calendario, notificaciones, propuestas).

Desde Backend, en el contenedor:
    docker exec enci-backend-local uv run python scripts/seed_demo_fase4.py

Es idempotente: usa ids fijos con prefijo ``demo4-`` y se puede correr varias veces. No toca datos
que no sean suyos. Solo para entornos locales: crea usuarios con una clave conocida (DEMO_PASSWORD).
Las visitas se calculan a partir de "ahora", asi que conviene volver a correrlo para tener
eventos cercanos y avisos nuevos.
"""
import os
from datetime import date, datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.core.rut import compute_dv
from app.core.security import get_password_hash
from app.models_sql.cliente import Cliente
from app.models_sql.comercial import Interaction, Opportunity, Proposal
from app.models_sql.competencia import (
    EquivalenciaProducto, PrecioCompetencia, ProductoCompetencia, ProductoEncipharm,
)
from app.models_sql.evento import Evento
from app.models_sql.notificacion import Notificacion
from app.models_sql.user import User

PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo12345678")
NOW = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
TODAY = date.today()


def rut(body: int) -> str:
    return f"{body}-{compute_dv(str(body))}"


def upsert(db, model, id_, **fields):
    row = db.get(model, id_)
    if row is None:
        row = model(id=id_)
        db.add(row)
    for key, value in fields.items():
        setattr(row, key, value)
    return row


# ── Usuarios ─────────────────────────────────────────────────────────────────
USERS = [
    # id, correo, nombre, rol, zona, acceso a Inteligencia
    ("demo4-sup", "sofia.supervisora@enci.cl", "Sofía Reyes", "supervisor", "Zona centro", True),
    ("demo4-ana", "ana.vendedora@enci.cl", "Ana Muñoz", "vendedor", "Zona sur", True),
    ("demo4-beto", "beto.vendedor@enci.cl", "Beto Contreras", "vendedor", "Zona norte", False),
]

# ── Clientes (id, contacto, empresa, rut, rubro, region, vendedor) ───────────
CLIENTS = [
    ("demo4-c1", "María Soto", "Avícola Los Pinos", 76123456, "Avícola", "Maule", "demo4-ana"),
    ("demo4-c2", "Jorge Lagos", "Lechería Santa Clara", 77234567, "Bovino leche", "Los Lagos", "demo4-ana"),
    ("demo4-c3", "Paula Díaz", "Porcinos San Rafael", 78345678, "Porcino", "O'Higgins", "demo4-beto"),
    ("demo4-c4", "Tomás Rivas", "Clínica Veterinaria Andes", 79456789, "Clínica", "Valparaíso", "demo4-beto"),
    ("demo4-c5", "Elena Parra", "Ganadera El Roble", 80567890, "Bovino carne", "Ñuble", "demo4-sup"),
]

# ── Catálogo Encipharm (id, nombre, sku, principios, concentración, presentación, unidad, cantidad, precio, categoría, especie)
CATALOGO = [
    ("demo4-e1", "Enci-Ivermec 1%", "ENC-IVM-500", "ivermectina", "1%", "Frasco 500 ml", "ml", 500, 38000, "Antiparasitario", "Bovinos"),
    ("demo4-e2", "Enci-Doramec 1%", "ENC-DOR-500", "doramectina", "1%", "Frasco 500 ml", "ml", 500, 62000, "Antiparasitario", "Bovinos"),
    ("demo4-e3", "Enci-Tulatro 10%", "ENC-TUL-100", "tulatromicina", "10%", "Frasco 100 ml", "ml", 100, 52000, "Antibiótico", "Bovinos, porcinos"),
    ("demo4-e4", "Enci-Enrofloxacina 10%", "ENC-ENR-100", "enrofloxacina", "10%", "Frasco 100 ml", "ml", 100, 14500, "Antibiótico", "Aves, porcinos"),
    ("demo4-e5", "Enci-Oxitetra LA 20%", "ENC-OXI-500", "oxitetraciclina", "20%", "Frasco 500 ml", "ml", 500, 54000, "Antibiótico", "Bovinos"),
    ("demo4-e6", "Enci-Vitamina ADE", "ENC-ADE-100", "vitamina A; vitamina D3; vitamina E", None, "Frasco 100 ml", "ml", 100, 9800, "Vitaminas", "Bovinos, equinos"),
]

# ── Productos de la competencia ──────────────────────────────────────────────
# id, competidor, nombre, principios, concentración, presentación, unidad, cantidad, categoría, especie, equivalente
COMPETENCIA = [
    ("demo4-p1", "Zoetis", "Ivomec", "ivermectina", "1%", "Frasco 500 ml", "ml", 500, "Antiparasitario", "Bovinos", "demo4-e1"),
    ("demo4-p2", "Boehringer Ingelheim", "Ivomec Gold", "ivermectina", "1%", "Frasco 250 ml", "ml", 250, "Antiparasitario", "Bovinos", "demo4-e1"),
    ("demo4-p3", "Zoetis", "Dectomax", "doramectina", "1%", "Frasco 500 ml", "ml", 500, "Antiparasitario", "Bovinos", "demo4-e2"),
    ("demo4-p4", "Zoetis", "Draxxin", "tulatromicina", "10%", "Frasco 100 ml", "ml", 100, "Antibiótico", "Bovinos, porcinos", "demo4-e3"),
    ("demo4-p5", "Agrovet Market", "Tulaxin", "tulatromicina", "10%", "Frasco 50 ml", "ml", 50, "Antibiótico", "Bovinos", "demo4-e3"),
    ("demo4-p6", "Bayer", "Baytril", "enrofloxacina", "10%", "Frasco 100 ml", "ml", 100, "Antibiótico", "Aves, porcinos", "demo4-e4"),
    ("demo4-p7", "Drag Pharma", "Enrodrag", "enrofloxacina", "10%", "Frasco 100 ml", "ml", 100, "Antibiótico", "Aves", "demo4-e4"),
    ("demo4-p8", "Zoetis", "Terramicina LA", "oxitetraciclina", "20%", "Frasco 500 ml", "ml", 500, "Antibiótico", "Bovinos", "demo4-e5"),
    ("demo4-p9", "MSD Salud Animal", "Cydectin", "moxidectina", "1%", "Frasco 500 ml", "ml", 500, "Antiparasitario", "Bovinos", None),
    ("demo4-p10", "Virbac", "Vitaminas ADE inyectable", "vitamina A; vitamina D3; vitamina E", None, "Frasco 250 ml", "ml", 250, "Vitaminas", "Bovinos", "demo4-e6"),
]

# Historial de precios aprobados: producto -> [(días atrás, precio)]. El último es el vigente.
PRECIOS = {
    "demo4-p1": [(90, 41000), (45, 44000), (5, 46500)],
    "demo4-p2": [(30, 28000), (3, 29500)],
    "demo4-p3": [(60, 71000), (10, 74000)],
    "demo4-p4": [(40, 51000), (6, 55000)],
    "demo4-p5": [(15, 21000)],
    "demo4-p6": [(50, 14000), (8, 15200)],
    "demo4-p7": [(20, 12500)],
    "demo4-p8": [(25, 52000)],
    "demo4-p10": [(12, 16500)],
}
# Pendientes de aprobación (para probar la cola) y uno descartado: producto, vendedor, precio, fuente
PENDIENTES = [
    ("demo4-p1", "demo4-ana", 45900, "Cotización vista en Lechería Santa Clara"),
    ("demo4-p3", "demo4-beto", 73000, "Lista de precios del distribuidor"),
    ("demo4-p9", "demo4-ana", 49500, "Visita a Ganadera El Roble"),
    ("demo4-p6", "demo4-beto", 9900, "Precio fuera de rango (para descartar)"),
]


def seed_users(db):
    for uid, email, nombre, rol, zona, intel in USERS:
        upsert(
            db, User, uid, email=email, nombre=nombre, rol=rol, cargo=rol.capitalize(), rango=rol.capitalize(), zona=zona,
            password_hash=get_password_hash(PASSWORD), appMovil=True, webApp=True, accesoInteligencia=intel, activo=True,
            theme="dark", language="es",
        )
    db.flush()


def seed_commercial(db):
    for cid, contacto, empresa, body, rubro, region, seller in CLIENTS:
        upsert(
            db, Cliente, cid, nombre=contacto, empresa=empresa, rut=rut(body), rubro=rubro, region=region,
            email=f"contacto@{empresa.lower().replace(' ', '').replace('í', 'i').replace('é', 'e')}.cl",
            telefono="+56 9 5555 0000", estado="En proceso", vendedorUid=seller, ownerUid=seller,
        )
    db.flush()
    plan = [  # cliente, etapa, valor, prob, estado propuesta, monto
        ("demo4-c1", "negociacion", 18_500_000, 70, "enviada", 18_500_000),
        ("demo4-c2", "cotizacion", 9_200_000, 50, "borrador", 9_200_000),
        ("demo4-c3", "ganado", 14_000_000, 100, "aceptada", 14_000_000),
        ("demo4-c4", "perdido", 3_800_000, 10, "rechazada", 3_800_000),
        ("demo4-c5", "nuevo", 6_500_000, 20, "borrador", 6_500_000),
    ]
    seller_of = {c[0]: c[6] for c in CLIENTS}
    for i, (cid, stage, value, prob, state, amount) in enumerate(plan, start=1):
        upsert(db, Opportunity, f"demo4-o{i}", clienteId=cid, titulo=f"Programa sanitario {CLIENTS[i-1][2]}", etapa=stage,
               valorEstimado=value, probabilidad=prob, descripcion="Datos de prueba", vendedorUid=seller_of[cid])
        db.flush()
        upsert(db, Proposal, f"demo4-pr{i}", clienteId=cid, oportunidadId=f"demo4-o{i}", titulo=f"Oferta {CLIENTS[i-1][2]}",
               montoNeto=amount, descuentoPct=5 if state == "aceptada" else 0, estado=state, vendedorUid=seller_of[cid])
        upsert(db, Interaction, f"demo4-i{i}", clienteId=cid, tipo=["llamada", "visita", "reunion", "correo", "visita"][i - 1],
               fecha=NOW - timedelta(days=i * 3), resumen="Seguimiento comercial de prueba", resultado="Interesado",
               proximaAccion="Enviar cotización", vendedorUid=seller_of[cid])
    db.flush()


def seed_competencia(db, sup):
    for pid, nombre, sku, principios, conc, pres, unit, qty, price, cat, species in CATALOGO:
        upsert(db, ProductoEncipharm, pid, nombre=nombre, sku=sku, principiosActivos=principios, concentracion=conc,
               presentacion=pres, unidadMedida=unit, cantidadPresentacion=qty, precioLista=price, moneda="CLP",
               categoria=cat, especie=species, activo=True)
    for pid, comp, nombre, principios, conc, pres, unit, qty, cat, species, _ in COMPETENCIA:
        upsert(db, ProductoCompetencia, pid, competidor=comp, nombre=nombre, principiosActivos=principios, concentracion=conc,
               presentacion=pres, unidadMedida=unit, cantidadPresentacion=qty, categoria=cat, especie=species, creadoPor=sup)
    db.flush()
    db.query(EquivalenciaProducto).filter(EquivalenciaProducto.productoCompetenciaId.like("demo4-%")).delete()
    for p in COMPETENCIA:
        if p[10]:
            upsert(db, EquivalenciaProducto, f"{p[0]}:{p[10]}", productoCompetenciaId=p[0], productoEncipharmId=p[10])

    for pid, history in PRECIOS.items():
        for n, (days, price) in enumerate(history):
            upsert(db, PrecioCompetencia, f"demo4-pc-{pid}-{n}", productoId=pid, precio=price, moneda="CLP",
                   fuente=["Lista de precios del distribuidor", "Cotización de cliente", "Visita en terreno"][n % 3],
                   fechaPrecio=TODAY - timedelta(days=days), zona="Zona sur", estado="aprobado", reportadoPor=sup,
                   revisadoPor=sup, revisadoAt=NOW, createdAt=NOW - timedelta(days=days))
    for n, (pid, seller, price, source) in enumerate(PENDIENTES):
        discarded = n == len(PENDIENTES) - 1
        upsert(db, PrecioCompetencia, f"demo4-pend-{n}", productoId=pid, precio=price, moneda="CLP", fuente=source,
               fechaPrecio=TODAY - timedelta(days=1), estado="descartado" if discarded else "pendiente", reportadoPor=seller,
               revisadoPor=sup if discarded else None, revisadoAt=NOW if discarded else None, createdAt=NOW - timedelta(hours=n + 1))
    db.flush()


def seed_events(db):
    def event(n, client, seller, kind, start, hours, state, place, notes=None):
        upsert(db, Evento, f"demo4-ev{n}", clienteId=client, vendedorUid=seller, tipo=kind, inicio=start,
               fin=start + timedelta(hours=hours), estado=state, lugar=place, notas=notes)

    today9 = NOW.replace(hour=13, minute=0, second=0)  # 13:00 UTC ~ 09:00 en Chile
    event(1, "demo4-c1", "demo4-ana", "presencial", NOW + timedelta(minutes=40), 1, "planificada", "Plantel Los Pinos, Maule",
          "Debería avisar «en menos de 1 hora»")
    event(2, "demo4-c2", "demo4-ana", "virtual", NOW + timedelta(hours=20), 1, "planificada", "Videollamada",
          "Debería avisar «en menos de 24 horas»")
    event(3, "demo4-c3", "demo4-beto", "llamada", NOW + timedelta(days=2, hours=1), 1, "planificada", None)
    event(4, "demo4-c4", "demo4-beto", "presencial", NOW + timedelta(days=5), 2, "planificada", "Clínica Andes, Valparaíso")
    event(5, "demo4-c5", "demo4-sup", "presencial", NOW + timedelta(days=9), 3, "planificada", "Ganadera El Roble")
    event(6, "demo4-c1", "demo4-ana", "presencial", NOW - timedelta(days=3), 1, "realizada", "Plantel Los Pinos", "Ya realizada")
    event(7, "demo4-c2", "demo4-ana", "llamada", NOW - timedelta(days=6), 1, "cancelada", None, "Cancelada por el cliente")
    event(8, "demo4-c3", "demo4-beto", "virtual", today9 + timedelta(days=1), 1, "planificada", "Meet", "Mañana temprano")
    event(9, "demo4-c4", "demo4-ana", "presencial", NOW + timedelta(days=12), 1, "planificada", "Cliente de otro vendedor (agendado por el supervisor)")
    db.flush()


def seed_notifications(db):
    items = [
        ("demo4-sup", "propuesta_estado", "Tu propuesta «Oferta Porcinos San Rafael» pasó a aceptada", "Cambio hecho por Administrador.", "/propuestas"),
        ("demo4-ana", "cliente_asignado", "Te asignaron el cliente Lechería Santa Clara", "Asignado por Sofía Reyes.", "/clientes/demo4-c2"),
        ("demo4-beto", "cliente_asignado", "Te asignaron el cliente Clínica Veterinaria Andes", "Asignado por Sofía Reyes.", "/clientes/demo4-c4"),
    ]
    for n, (uid, kind, title, message, link) in enumerate(items):
        upsert(db, Notificacion, f"demo4-n{n}", usuarioId=uid, tipo=kind, titulo=title, mensaje=message, enlace=link,
               referencia=f"demo4-{n}", leida=False, createdAt=NOW - timedelta(hours=n + 2))
    db.flush()


def main() -> None:
    with SessionLocal() as db:
        seed_users(db)
        seed_commercial(db)
        seed_competencia(db, "demo4-sup")
        seed_events(db)
        seed_notifications(db)
        db.commit()
    print("Listo. Usuarios (clave %s): %s" % (PASSWORD, ", ".join(u[1] for u in USERS)))


if __name__ == "__main__":
    main()
