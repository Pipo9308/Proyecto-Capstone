"""Datos sinteticos coherentes para Enci Ventas (6 meses de actividad comercial).

Desde Backend, en el contenedor:
    docker exec enci-backend-local uv run python scripts/seed_demo_sintetico.py          # sembrar
    docker exec enci-backend-local uv run python scripts/seed_demo_sintetico.py --borrar # quitar todo lo demo-

Todo lleva id con prefijo ``demo-``: es idempotente (usa un generador con semilla fija) y ``--borrar`` solo
toca esos ids. Los usuarios demo NO tienen clave conocida: el admin les genera una invitacion desde la web.
"""
import random
import sys
from datetime import date, datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.core.rut import compute_dv
from app.models_sql.cliente import Cliente
from app.models_sql.comercial import Interaction, Opportunity, Proposal
from app.models_sql.competencia import EquivalenciaProducto, PrecioCompetencia, ProductoCompetencia, ProductoEncipharm
from app.models_sql.evento import Evento
from app.models_sql.meta import MetaVenta
from app.models_sql.notificacion import Notificacion
from app.models_sql.user import User

NOW = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
TODAY = date.today()
R = random.Random(20261116)
D = "[DEMO] "  # marca visible en todo dato sintetico
VENTAS: dict[tuple[str, str], float] = {}  # (vendedor, AAAA-MM) -> venta aceptada, para fijar metas verosimiles
MODELS = [MetaVenta, Notificacion, Evento, Interaction, Proposal, Opportunity, PrecioCompetencia, EquivalenciaProducto,
          ProductoCompetencia, ProductoEncipharm, Cliente, User]

# id, correo, nombre, rol, zona, acceso a Inteligencia
USERS = [
    ("demo-sup", "carolina.vidal@enci.cl", "Carolina Vidal", "supervisor", "Zona centro", True),
    ("demo-v1", "matias.fuentes@enci.cl", "Matías Fuentes", "vendedor", "Zona norte", True),
    ("demo-v2", "daniela.rojas@enci.cl", "Daniela Rojas", "vendedor", "Zona centro", True),
    ("demo-v3", "ignacio.pavez@enci.cl", "Ignacio Pavez", "vendedor", "Zona centro", False),
    ("demo-v4", "camila.henriquez@enci.cl", "Camila Henríquez", "vendedor", "Zona sur", True),
    ("demo-v5", "rodrigo.saavedra@enci.cl", "Rodrigo Saavedra", "vendedor", "Zona sur", False),
    ("demo-v6", "fernanda.mella@enci.cl", "Fernanda Mella", "vendedor", "Zona oriente", True),
]
SELLERS = [u for u in USERS if u[3] == "vendedor"]
ZONE_REGIONS = {
    "Zona norte": ["Coquimbo", "Valparaíso", "Atacama"],
    "Zona centro": ["Metropolitana", "O'Higgins", "Maule"],
    "Zona sur": ["Ñuble", "Biobío", "La Araucanía", "Los Lagos", "Los Ríos"],
    "Zona oriente": ["Metropolitana", "O'Higgins", "Maule"],
}

# (rubro, prefijos de nombre, productos que suele comprar, ticket base CLP)
RUBROS = [
    ("Avícola", ["Avícola", "Planteles", "Huevos"], ["Aves"], 9_000_000),
    ("Bovino leche", ["Lechería", "Agrícola", "Predio"], ["Bovinos"], 12_000_000),
    ("Bovino carne", ["Ganadera", "Agropecuaria", "Fundo"], ["Bovinos"], 15_000_000),
    ("Porcino", ["Porcinos", "Criadero", "Agrícola"], ["Porcinos"], 18_000_000),
    ("Clínica", ["Clínica Veterinaria", "Veterinaria", "Centro Veterinario"], ["Caninos", "Felinos"], 2_500_000),
    ("Distribuidor", ["Distribuidora", "Comercial", "Agroinsumos"], ["Bovinos", "Aves"], 22_000_000),
    ("Equino", ["Haras", "Criadero", "Centro Ecuestre"], ["Equinos"], 3_500_000),
]
APELLIDOS = ["Soto", "Muñoz", "Rojas", "Díaz", "Pérez", "González", "Silva", "Contreras", "Lagos", "Parra", "Rivas",
             "Vargas", "Araya", "Tapia", "Fuentes", "Castillo", "Reyes", "Morales", "Sepúlveda", "Navarro"]
NOMBRES = ["María", "Jorge", "Paula", "Tomás", "Elena", "Luis", "Marcela", "Pablo", "Verónica", "Andrés", "Claudia",
           "Felipe", "Patricia", "Cristián", "Natalia", "Héctor"]
LUGARES = ["Osorno", "Chillán", "Rancagua", "Talca", "Los Ángeles", "Temuco", "La Serena", "Curicó", "Puerto Montt",
           "Linares", "San Fernando", "Ovalle", "Valdivia", "Casablanca", "Melipilla", "Quillota"]
SUFIJOS = ["Los Pinos", "El Roble", "Santa Clara", "San Rafael", "Los Andes", "Las Palmas", "El Sauce", "Santa Rosa",
           "La Esperanza", "Los Álamos", "Don Alberto", "El Mirador", "Santa Elena", "Los Quillayes"]

# id, nombre, sku, principios, conc, presentacion, unidad, cantidad, precio, categoria, especie
CATALOGO = [
    ("demo-e01", "Enci-Ivermec 1%", "DEMO-IVM-500", "ivermectina", "1%", "Frasco 500 ml", "ml", 500, 38000, "Antiparasitario", "Bovinos"),
    ("demo-e02", "Enci-Doramec 1%", "DEMO-DOR-500", "doramectina", "1%", "Frasco 500 ml", "ml", 500, 62000, "Antiparasitario", "Bovinos"),
    ("demo-e03", "Enci-Moxi 1%", "DEMO-MOX-500", "moxidectina", "1%", "Frasco 500 ml", "ml", 500, 58000, "Antiparasitario", "Bovinos"),
    ("demo-e04", "Enci-Albendazol 10%", "DEMO-ALB-1L", "albendazol", "10%", "Frasco 1 L", "ml", 1000, 24000, "Antiparasitario", "Bovinos"),
    ("demo-e05", "Enci-Fenbenda 10%", "DEMO-FEN-1L", "fenbendazol", "10%", "Frasco 1 L", "ml", 1000, 21500, "Antiparasitario", "Bovinos, porcinos"),
    ("demo-e06", "Enci-Tulatro 10%", "DEMO-TUL-100", "tulatromicina", "10%", "Frasco 100 ml", "ml", 100, 52000, "Antibiótico", "Bovinos, porcinos"),
    ("demo-e07", "Enci-Enrofloxacina 10%", "DEMO-ENR-100", "enrofloxacina", "10%", "Frasco 100 ml", "ml", 100, 14500, "Antibiótico", "Aves, porcinos"),
    ("demo-e08", "Enci-Oxitetra LA 20%", "DEMO-OXI-500", "oxitetraciclina", "20%", "Frasco 500 ml", "ml", 500, 54000, "Antibiótico", "Bovinos"),
    ("demo-e09", "Enci-Florfenicol 30%", "DEMO-FLO-100", "florfenicol", "30%", "Frasco 100 ml", "ml", 100, 31000, "Antibiótico", "Bovinos, porcinos"),
    ("demo-e10", "Enci-Ceftio 5%", "DEMO-CEF-100", "ceftiofur", "5%", "Frasco 100 ml", "ml", 100, 46000, "Antibiótico", "Bovinos, porcinos"),
    ("demo-e11", "Enci-Penistrep", "DEMO-PEN-100", "penicilina; estreptomicina", None, "Frasco 100 ml", "ml", 100, 8900, "Antibiótico", "Bovinos, equinos"),
    ("demo-e12", "Enci-Amoxi LA 15%", "DEMO-AMO-100", "amoxicilina", "15%", "Frasco 100 ml", "ml", 100, 17800, "Antibiótico", "Bovinos, porcinos"),
    ("demo-e13", "Enci-Vitamina ADE", "DEMO-ADE-100", "vitamina A; vitamina D3; vitamina E", None, "Frasco 100 ml", "ml", 100, 9800, "Vitaminas", "Bovinos, equinos"),
    ("demo-e14", "Enci-Complejo B", "DEMO-CBC-100", "vitamina B1; vitamina B6; vitamina B12", None, "Frasco 100 ml", "ml", 100, 7600, "Vitaminas", "Bovinos, equinos, caninos"),
    ("demo-e15", "Enci-Selenio E", "DEMO-SEL-100", "selenio; vitamina E", None, "Frasco 100 ml", "ml", 100, 8400, "Vitaminas", "Bovinos, ovinos"),
    ("demo-e16", "Enci-Calcio Mag", "DEMO-CAL-500", "gluconato de calcio; magnesio", None, "Frasco 500 ml", "ml", 500, 12500, "Minerales", "Bovinos"),
    ("demo-e17", "Enci-Meloxicam 2%", "DEMO-MEL-50", "meloxicam", "2%", "Frasco 50 ml", "ml", 50, 13900, "Antiinflamatorio", "Bovinos, porcinos, caninos"),
    ("demo-e18", "Enci-Ketoprofeno 10%", "DEMO-KET-50", "ketoprofeno", "10%", "Frasco 50 ml", "ml", 50, 11200, "Antiinflamatorio", "Bovinos, equinos"),
    ("demo-e19", "Enci-Dexa 0,2%", "DEMO-DEX-50", "dexametasona", "0,2%", "Frasco 50 ml", "ml", 50, 6900, "Antiinflamatorio", "Bovinos, equinos, caninos"),
    ("demo-e20", "Enci-Oxitocina 10 UI", "DEMO-OXT-50", "oxitocina", "10 UI/ml", "Frasco 50 ml", "ml", 50, 7400, "Reproductivo", "Bovinos, porcinos"),
    ("demo-e21", "Enci-Cloprostenol", "DEMO-CLO-20", "cloprostenol", "0,25 mg/ml", "Frasco 20 ml", "ml", 20, 15800, "Reproductivo", "Bovinos"),
    ("demo-e22", "Enci-Lidocaína 2%", "DEMO-LID-50", "lidocaína", "2%", "Frasco 50 ml", "ml", 50, 5200, "Anestésico", "Equinos, caninos"),
    ("demo-e23", "Enci-Sulfa Trimetoprim", "DEMO-SUL-100", "sulfadoxina; trimetoprima", None, "Frasco 100 ml", "ml", 100, 9300, "Antibiótico", "Bovinos, aves"),
    ("demo-e24", "Enci-Coccistop", "DEMO-COC-1L", "toltrazuril", "2,5%", "Frasco 1 L", "ml", 1000, 34000, "Antiparasitario", "Aves, porcinos"),
    ("demo-e25", "Enci-Levamisol 7,5%", "DEMO-LEV-500", "levamisol", "7,5%", "Frasco 500 ml", "ml", 500, 16500, "Antiparasitario", "Bovinos, ovinos"),
    ("demo-e26", "Enci-Amprolio Soluble", "DEMO-AMP-1K", "amprolio", "20%", "Sobre 1 kg", "g", 1000, 18200, "Antiparasitario", "Aves"),
    ("demo-e27", "Enci-Tilosina 20%", "DEMO-TIL-100", "tilosina", "20%", "Frasco 100 ml", "ml", 100, 12800, "Antibiótico", "Bovinos, porcinos"),
    ("demo-e28", "Enci-Probiótico Aves", "DEMO-PRO-1K", "lactobacillus; bacillus", None, "Sobre 1 kg", "g", 1000, 14900, "Suplemento", "Aves"),
    ("demo-e29", "Enci-Electrolitos", "DEMO-ELE-1K", "sales electrolíticas; glucosa", None, "Sobre 1 kg", "g", 1000, 6700, "Suplemento", "Bovinos, aves"),
    ("demo-e30", "Enci-Spot On Perros", "DEMO-FIP-3", "fipronil", "10%", "Caja 3 pipetas", "dosis", 3, 11500, "Antiparasitario", "Caninos"),
]

# competidor, nombre comercial, indice del producto Encipharm equivalente (0 = sin equivalente), factor de precio
COMPETIDORES = ["Zoetis", "Boehringer Ingelheim", "Bayer", "MSD Salud Animal", "Elanco", "Virbac", "Drag Pharma",
                "Agrovet Market", "Laboratorio Chile", "Ceva"]
COMPETENCIA = [
    ("Zoetis", "Ivomec", 1, 1.22), ("Boehringer Ingelheim", "Ivomec Gold", 1, 1.30), ("Drag Pharma", "Ivermax", 1, 0.96),
    ("Zoetis", "Dectomax", 2, 1.19), ("MSD Salud Animal", "Cydectin", 3, 1.15), ("Agrovet Market", "Albenvet 10%", 4, 0.93),
    ("Zoetis", "Valbazen", 4, 1.28), ("Laboratorio Chile", "Fenbenvet", 5, 0.98), ("Zoetis", "Draxxin", 6, 1.14),
    ("Agrovet Market", "Tulaxin", 6, 0.88), ("Bayer", "Baytril", 7, 1.10), ("Drag Pharma", "Enrodrag", 7, 0.91),
    ("Zoetis", "Terramicina LA", 8, 1.05), ("Elanco", "Oxitet LA", 8, 0.97), ("Ceva", "Florfenicol Ceva", 9, 1.08),
    ("Zoetis", "Excenel", 10, 1.17), ("Laboratorio Chile", "Penistrep Lab", 11, 0.95), ("Virbac", "Amoxivir LA", 12, 1.12),
    ("Virbac", "ADE inyectable", 13, 1.18), ("Drag Pharma", "Vitadrag ADE", 13, 0.90), ("Bayer", "Catosal", 14, 1.21),
    ("Agrovet Market", "Seleniovet", 15, 0.94), ("Virbac", "Calcio Virbac", 16, 1.09), ("Boehringer Ingelheim", "Metacam", 17, 1.33),
    ("Elanco", "Ketofen", 18, 1.11), ("Laboratorio Chile", "Dexalab", 19, 0.92), ("Ceva", "Oxitocina Ceva", 20, 1.06),
    ("Bayer", "Estrumate", 21, 1.20), ("Drag Pharma", "Lidodrag", 22, 0.96), ("Zoetis", "Trimetropin Zoetis", 23, 1.13),
    ("Elanco", "Baycox", 24, 1.25), ("Zoetis", "Levamisol Z", 25, 1.04), ("Ceva", "Ampronet", 26, 1.07),
    ("Elanco", "Tylan 200", 27, 1.16), ("Ceva", "Probioceva", 28, 1.10), ("Boehringer Ingelheim", "Frontline Spot On", 30, 1.35),
    ("MSD Salud Animal", "Bravecto Spot", 30, 1.42), ("Agrovet Market", "Electrovet", 29, 0.89),
    ("Zoetis", "Rimadyl Inyectable", 0, 1.0), ("MSD Salud Animal", "Banamine", 0, 1.0),
]


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


def borrar(db):
    for model in MODELS:
        n = db.query(model).filter(model.id.like("demo-%")).delete()
        print(f"{model.__tablename__}: {n} borrados")
    db.commit()


def seed_users(db):
    for uid, email, nombre, rol, zona, intel in USERS:
        upsert(db, User, uid, email=email, nombre=D + nombre, rol=rol, cargo=rol.capitalize(), rango=rol.capitalize(),
               zona=zona, password_hash=None, appMovil=True, webApp=True, accesoInteligencia=intel, activo=True,
               theme="dark", language="es", createdAt=NOW - timedelta(days=200))
    db.flush()


def seed_clientes(db):
    clientes = []
    for i in range(1, 49):
        seller = SELLERS[(i - 1) % len(SELLERS)]
        rubro, prefijos, especies, ticket = R.choice(RUBROS)
        base = f"{R.choice(prefijos)} {R.choice(SUFIJOS)}"
        if R.random() < 0.35:
            base = f"{base} {R.choice(LUGARES)}"
        contacto = f"{R.choice(NOMBRES)} {R.choice(APELLIDOS)}"
        slug = "".join(ch for ch in base.lower() if ch.isalnum())
        cid = f"demo-c{i:02d}"
        region = R.choice(ZONE_REGIONS[seller[4]])
        created = NOW - timedelta(days=R.randint(15, 200))
        upsert(db, Cliente, cid, nombre=contacto, empresa=D + base, rut=rut(76_100_000 + i * 7_919), email=f"contacto@{slug[:20]}.cl",
               telefono=f"+56 9 {R.randint(5000, 9999)} {R.randint(1000, 9999)}", rubro=rubro, region=region,
               estado=R.choice(["En proceso", "En proceso", "Completado", "Inactivo"]), vendedorUid=seller[0], ownerUid=seller[0],
               createdAt=created, updatedAt=created)
        clientes.append((cid, base, seller[0], ticket, rubro))
    db.flush()
    return clientes


def seed_comercial(db, clientes):
    resumenes = {
        "visita": ["Visita al plantel: revisión del plan sanitario", "Recorrido de predio y toma de pedido", "Visita técnica por brote respiratorio"],
        "llamada": ["Seguimiento de cotización enviada", "Consulta por stock y plazos de despacho", "Coordinación de visita"],
        "reunion": ["Reunión de negociación de condiciones de pago", "Presentación de línea antiparasitaria", "Revisión de resultados del trimestre"],
        "correo": ["Envío de ficha técnica y lista de precios", "Reenvío de cotización con ajuste de descuento"],
    }
    resultados = ["Interesado", "Pide cotización", "Evalúa con su veterinario", "Compara con otro proveedor", "Cerrado", "Sin respuesta"]
    acciones = ["Enviar cotización", "Llamar en una semana", "Agendar visita técnica", "Enviar muestras", "Confirmar pedido"]
    n_opp = n_prop = n_int = 0
    for cid, empresa, seller, ticket, rubro in clientes:
        for _ in range(R.choice([1, 1, 2, 2, 3])):
            n_opp += 1
            age = R.randint(2, 175)
            created = NOW - timedelta(days=age)
            # Las oportunidades viejas ya se cerraron; las recientes siguen abiertas.
            if age > 90:
                stage = R.choices(["ganado", "perdido", "negociacion"], [60, 30, 10])[0]
            elif age > 30:
                stage = R.choices(["ganado", "perdido", "negociacion", "cotizacion", "contactado"], [25, 15, 25, 25, 10])[0]
            else:
                stage = R.choices(["nuevo", "contactado", "cotizacion", "negociacion", "ganado"], [20, 25, 25, 20, 10])[0]
            prob = {"nuevo": 15, "contactado": 30, "cotizacion": 50, "negociacion": 75, "ganado": 100, "perdido": 0}[stage]
            value = round(ticket * R.uniform(0.4, 1.6), -4)
            oid = f"demo-o{n_opp:03d}"
            upsert(db, Opportunity, oid, clienteId=cid, titulo=f"{D}Programa sanitario {empresa}", etapa=stage, valorEstimado=value,
                   probabilidad=prob, descripcion=f"{D}Plan anual de productos para {rubro.lower()}", vendedorUid=seller,
                   createdAt=created, updatedAt=created + timedelta(days=R.randint(1, max(2, age // 2))))
            db.flush()
            if stage != "nuevo":
                n_prop += 1
                estado = {"contactado": "borrador", "cotizacion": R.choice(["borrador", "enviada"]), "negociacion": "enviada",
                          "ganado": "aceptada", "perdido": "rechazada"}[stage]
                if estado == "aceptada":
                    key = (seller, (created + timedelta(days=2)).strftime("%Y-%m"))
                    VENTAS[key] = VENTAS.get(key, 0) + value
                upsert(db, Proposal, f"demo-pr{n_prop:03d}", clienteId=cid, oportunidadId=oid, titulo=f"{D}Oferta {empresa}",
                       montoNeto=value, descuentoPct=R.choice([0, 0, 3, 5, 8, 10]), estado=estado, vendedorUid=seller,
                       notas="[DEMO] Datos sintéticos de demostración", createdAt=created + timedelta(days=2),
                       updatedAt=created + timedelta(days=R.randint(3, max(4, age // 2 + 2))))
            for _ in range(R.randint(1, 3)):
                n_int += 1
                tipo = R.choice(list(resumenes))
                fecha = created + timedelta(days=R.randint(0, max(1, age - 1)), hours=R.randint(8, 17))
                upsert(db, Interaction, f"demo-i{n_int:03d}", clienteId=cid, tipo=tipo, fecha=min(fecha, NOW),
                       resumen=D + R.choice(resumenes[tipo]), resultado=R.choice(resultados), proximaAccion=R.choice(acciones),
                       vendedorUid=seller, createdAt=min(fecha, NOW), updatedAt=min(fecha, NOW))
    db.flush()
    return n_opp, n_prop, n_int


def seed_competencia(db):
    for pid, nombre, sku, principios, conc, pres, unit, qty, price, cat, species in CATALOGO:
        upsert(db, ProductoEncipharm, pid, nombre=D + nombre, sku=sku, principiosActivos=principios, concentracion=conc,
               presentacion=pres, unidadMedida=unit, cantidadPresentacion=qty, precioLista=price, moneda="CLP",
               categoria=cat, especie=species, activo=True)
    db.flush()
    n_price = 0
    for n, (comp, nombre, eq, factor) in enumerate(COMPETENCIA, start=1):
        pid = f"demo-p{n:02d}"
        base = CATALOGO[eq - 1] if eq else None
        upsert(db, ProductoCompetencia, pid, competidor=comp, nombre=D + nombre,
               principiosActivos=base[3] if base else "ketoprofeno; flunixino", concentracion=base[4] if base else None,
               presentacion=base[5] if base else "Frasco 100 ml", unidadMedida=base[6] if base else "ml",
               cantidadPresentacion=base[7] if base else 100, categoria=base[9] if base else "Antiinflamatorio",
               especie=base[10] if base else "Bovinos, equinos", creadoPor="demo-sup")
        if base:
            upsert(db, EquivalenciaProducto, f"{pid}:{base[0]}", productoCompetenciaId=pid, productoEncipharmId=base[0])
        # Historial de 3 a 5 reportes con tendencia al alza (inflación de ~1 % mensual) y ruido.
        list_price = base[8] if base else 18_000
        reportes = R.randint(3, 5)
        for k in range(reportes):
            days = (reportes - 1 - k) * R.randint(25, 40) + R.randint(1, 6)
            price = round(list_price * factor * (1 - 0.01 * days / 30) * R.uniform(0.97, 1.03), -2)
            seller = R.choice(SELLERS)
            n_price += 1
            upsert(db, PrecioCompetencia, f"demo-pc{n_price:03d}", productoId=pid, precio=price, moneda="CLP",
                   fuente=D + R.choice(["Lista de precios del distribuidor", "Cotización de cliente", "Visita en terreno"]),
                   fechaPrecio=TODAY - timedelta(days=days), zona=seller[4], estado="aprobado", reportadoPor=seller[0],
                   revisadoPor="demo-sup", revisadoAt=NOW - timedelta(days=max(days - 1, 0)),
                   createdAt=NOW - timedelta(days=days))
    # Cola de revisión: unos pendientes recientes para que el supervisor tenga algo que aprobar.
    for k in range(6):
        pid_n = R.randint(1, 38)
        eq = COMPETENCIA[pid_n - 1][2]
        list_price = CATALOGO[eq - 1][8] if eq else 18_000
        seller = R.choice(SELLERS)
        upsert(db, PrecioCompetencia, f"demo-pend{k + 1}", productoId=f"demo-p{pid_n:02d}",
               precio=round(list_price * COMPETENCIA[pid_n - 1][3] * R.uniform(0.95, 1.05), -2), moneda="CLP",
               fuente=D + "Cotización vista en visita", fechaPrecio=TODAY - timedelta(days=R.randint(0, 3)), zona=seller[4],
               estado="pendiente", reportadoPor=seller[0], createdAt=NOW - timedelta(hours=R.randint(2, 70)))
    db.flush()


def seed_eventos(db, clientes):
    tipos = ["presencial", "presencial", "virtual", "llamada"]
    lugares = {"presencial": "Visita al plantel", "virtual": "Videollamada", "llamada": None}
    n = 0
    for offset in list(range(-45, 0, 3)) + list(range(1, 30, 2)):
        cid, empresa, seller, _, _ = R.choice(clientes)
        tipo = R.choice(tipos)
        start = (NOW + timedelta(days=offset)).replace(hour=R.choice([9, 10, 11, 14, 15, 16]), minute=0, second=0)
        past = offset < 0
        n += 1
        upsert(db, Evento, f"demo-ev{n:02d}", clienteId=cid, vendedorUid=seller, tipo=tipo, inicio=start,
               fin=start + timedelta(hours=R.choice([1, 1, 2])),
               estado=R.choices(["realizada", "cancelada"], [85, 15])[0] if past else "planificada",
               lugar=lugares[tipo] and f"{lugares[tipo]} — {empresa}", notas="[DEMO] Datos sintéticos de demostración")
    db.flush()


def seed_notificaciones(db, clientes):
    for k, (cid, empresa, seller, _, _) in enumerate(R.sample(clientes, 8)):
        upsert(db, Notificacion, f"demo-n{k + 1:02d}", usuarioId=seller, tipo="cliente_asignado",
               titulo=f"{D}Te asignaron el cliente {empresa}", mensaje="Asignado por Carolina Vidal.", enlace=f"/clientes/{cid}",
               referencia=f"demo-{k}", leida=k > 4, createdAt=NOW - timedelta(hours=3 + k * 9))
    db.flush()


def seed_metas(db):
    """Meta mensual por vendedor para el mes actual y los 5 anteriores: unos cumplen y otros no."""
    n = 0
    for uid, *_ in SELLERS:
        reales = [v for (s, _), v in VENTAS.items() if s == uid] or [10_000_000]
        promedio = sum(reales) / len(reales)
        for back in range(6):
            y, m = divmod(TODAY.year * 12 + TODAY.month - 1 - back, 12)
            mes = f"{y}-{m + 1:02d}"
            real = VENTAS.get((uid, mes), 0)
            monto = real * R.uniform(0.85, 1.3) if back else promedio * R.uniform(1.0, 1.35)
            n += 1
            upsert(db, MetaVenta, f"{uid}:{mes}", vendedorUid=uid, mes=mes, monto=round(max(monto, 5_000_000), -5),
                   fijadaPor="demo-sup", updatedAt=NOW)
    db.flush()
    return n


def seed_hoy(db, clientes):
    """Actividad de hoy (para 'vendedores activos hoy' y la agenda del dia) y avisos para supervisor y admin."""
    for n, (cid, empresa, seller, _, _) in enumerate(R.sample(clientes, 8), start=1):
        when = NOW - timedelta(hours=R.randint(1, 8))
        upsert(db, Interaction, f"demo-ih{n:02d}", clienteId=cid, tipo=R.choice(["visita", "llamada", "reunion"]),
               fecha=when, resumen=D + "Seguimiento del día", resultado="Interesado", proximaAccion="Enviar cotización",
               vendedorUid=seller, createdAt=when, updatedAt=when)
    for n, (cid, empresa, seller, _, _) in enumerate(R.sample(clientes, 4), start=1):
        start = NOW.replace(hour=R.choice([13, 15, 17]), minute=0, second=0) + timedelta(days=0)
        upsert(db, Evento, f"demo-evh{n}", clienteId=cid, vendedorUid=seller, tipo="presencial", inicio=start,
               fin=start + timedelta(hours=1), estado="planificada", lugar=f"{D}Visita — {empresa}",
               notas="[DEMO] Visita de hoy")
    for n, uid in enumerate(["demo-sup", "seed-user-admin"]):
        upsert(db, Notificacion, f"demo-na{n}", usuarioId=uid, tipo="propuesta_estado",
               titulo=f"{D}Una propuesta pasó a aceptada", mensaje="Dato sintético de demostración.",
               enlace="/propuestas", referencia=f"demo-na{n}", leida=False, createdAt=NOW - timedelta(hours=n + 1))
    db.flush()


def main() -> None:
    with SessionLocal() as db:
        if "--borrar" in sys.argv:
            borrar(db)
            return
        seed_users(db)
        clientes = seed_clientes(db)
        n_opp, n_prop, n_int = seed_comercial(db, clientes)
        seed_competencia(db)
        seed_metas(db)
        seed_eventos(db, clientes)
        seed_notificaciones(db, clientes)
        seed_hoy(db, clientes)
        db.commit()
    print(f"Listo: {len(USERS)} usuarios, {len(clientes)} clientes, {n_opp} oportunidades, {n_prop} propuestas, "
          f"{n_int} interacciones, {len(CATALOGO)} productos Encipharm, {len(COMPETENCIA)} de competencia.")


if __name__ == "__main__":
    main()
