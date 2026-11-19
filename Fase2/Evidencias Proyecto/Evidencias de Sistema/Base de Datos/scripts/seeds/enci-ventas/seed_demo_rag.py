"""Documentos RAG y conversaciones sinteticas (todo marcado [DEMO], ids con prefijo ``demo-``).

Desde Backend, en el contenedor:
    docker exec enci-backend-local sh -c "cd /app && PYTHONPATH=/app uv run python scripts/seed_demo_rag.py"
    ... scripts/seed_demo_rag.py --borrar

Los documentos NO tienen archivo en el almacenamiento (gcsPath vacio): el chat los usa, pero "Reindexar" los
perderia. Los embeddings se calculan en local (fastembed), sin claves.
"""
import hashlib
import sys
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.models_sql.rag import RagChunk, RagConversation, RagDocument
from app.services.rag_service import add_chunks_to_index, chunk_text, normalize_text

NOW = datetime.now(timezone.utc)
ADMIN = {"uid": "seed-user-admin", "email": "admin@enci.cl"}

DOCS = {
    "demo-doc-01": ("[DEMO] Protocolo antiparasitario en bovinos.txt", """[DEMO] Documento sintético de demostración.
Protocolo antiparasitario en bovinos. Las lactonas macrocíclicas (ivermectina, doramectina, moxidectina) controlan nematodos gastrointestinales, piojos y sarna. La ivermectina al 1 % se aplica por vía subcutánea a 1 ml cada 50 kg de peso vivo. Respetar el período de resguardo antes de faena: 35 días para ivermectina y 50 días para doramectina. No usar en vacas lecheras en producción cuya leche sea para consumo humano.
Los benzimidazoles (albendazol 10 %, fenbendazol 10 %) se administran por vía oral: albendazol a 7,5 mg/kg. Rotar principios activos cada año para retrasar la resistencia. Dosificar según el animal más pesado del grupo y verificar la calibración de la pistola dosificadora. Realizar un conteo de huevos por gramo antes y 14 días después del tratamiento para confirmar eficacia."""),
    "demo-doc-02": ("[DEMO] Guía de antibióticos para enfermedad respiratoria bovina.txt", """[DEMO] Documento sintético de demostración.
Enfermedad respiratoria bovina (BRD). Tulatromicina 10 %: dosis única de 1 ml cada 40 kg por vía subcutánea, resguardo de 49 días. Florfenicol 30 %: 1 ml cada 15 kg, dos aplicaciones con 48 horas de intervalo, resguardo de 44 días. Oxitetraciclina de larga acción 20 %: una aplicación de 1 ml cada 10 kg por vía intramuscular profunda.
Criterios: tratar ante fiebre sobre 40 °C, depresión y secreción nasal. Registrar el tratamiento, el lote y la fecha. Si no hay mejoría en 72 horas, cambiar de principio activo y consultar al veterinario. El uso de antibióticos debe tener receta y respetar la normativa del SAG."""),
    "demo-doc-03": ("[DEMO] Manejo sanitario en planteles avícolas.txt", """[DEMO] Documento sintético de demostración.
Manejo sanitario en planteles avícolas. Para coccidiosis se usan anticoccidiales en el alimento o toltrazuril al 2,5 % en el agua de bebida, 7 mg/kg durante dos días seguidos. La enrofloxacina al 10 % se administra a 10 mg/kg por día durante 3 a 5 días en infecciones bacterianas; no usar en aves de postura cuyos huevos se destinen a consumo.
Bioseguridad: vacío sanitario de 14 días entre planteles, pediluvios con desinfectante y control de roedores. Los probióticos mejoran la integridad intestinal después de un tratamiento antibiótico. Mantener registro de mortalidad diaria; un aumento sobre 0,3 % diario exige revisión veterinaria."""),
    "demo-doc-04": ("[DEMO] Plan sanitario porcino.txt", """[DEMO] Documento sintético de demostración.
Plan sanitario porcino. Lechones: hierro inyectable el día 3 de vida, castración antes de los 10 días. Destete a las 3 a 4 semanas con dieta de transición. Tratamiento de diarreas con enrofloxacina o sulfa más trimetoprima según antibiograma. Las infecciones respiratorias se manejan con tulatromicina o tilosina 20 %.
Antiparasitario: fenbendazol en el alimento a las hembras antes del parto y a los lechones al destete. Desinfección de maternidades con vacío de 5 días. Vacunar contra parvovirus y erisipela según el calendario del plantel."""),
    "demo-doc-05": ("[DEMO] Vitaminas y minerales en bovinos de leche.txt", """[DEMO] Documento sintético de demostración.
Suplementación en vacas lecheras. Vitaminas A, D3 y E inyectables en el preparto: 10 ml por animal 30 días antes de la fecha de parto. El selenio con vitamina E previene retención de placenta y mastitis. La hipocalcemia posparto (fiebre de leche) se trata con gluconato de calcio endovenoso lento, 500 ml, vigilando el ritmo cardíaco.
El complejo B apoya el apetito y la recuperación tras cuadros febriles. Mantener la relación calcio fósforo de la ración entre 1,5 y 2 a 1. Los análisis de sangre al secado permiten ajustar la dosis."""),
    "demo-doc-06": ("[DEMO] Argumentario de ventas línea Encipharm.txt", """[DEMO] Documento sintético de demostración.
Argumentario comercial. Encipharm ofrece equivalentes genéricos de los principales productos del mercado a un precio por mililitro menor que el de las marcas líderes. Enci-Ivermec 1 % compite con Ivomec; Enci-Tulatro 10 % con Draxxin; Enci-Enrofloxacina 10 % con Baytril.
Objeciones frecuentes: calidad (responder con los registros del SAG y los certificados de lote), eficacia (equivalencia de principio activo y concentración) y continuidad de abastecimiento (stock en bodega central y despacho en 48 horas a las zonas norte, centro, sur y oriente). Descuentos por volumen: 5 % sobre 5 millones, 8 % sobre 10 millones y 10 % sobre 20 millones, sujetos a aprobación del supervisor."""),
    "demo-doc-07": ("[DEMO] Preguntas frecuentes de clientes.txt", """[DEMO] Documento sintético de demostración.
Preguntas frecuentes. ¿Cuánto demora un despacho? De 24 a 48 horas hábiles en la zona centro y hasta 5 días en la zona sur. ¿Hay muestras? El vendedor puede entregar muestras de hasta dos presentaciones por cliente nuevo. ¿Cómo se paga? Transferencia a 30 días para clientes con contrato y contado para clientes nuevos.
¿Qué hago si un lote presenta un problema? Informar al vendedor con el número de lote; se retira el producto y se repone sin costo tras la revisión de calidad. ¿Los productos tienen registro SAG? Sí, todos los productos veterinarios comercializados cuentan con su registro vigente."""),
    "demo-doc-08": ("[DEMO] Manejo de equinos y pequeños animales.txt", """[DEMO] Documento sintético de demostración.
Equinos: desparasitación cada 8 a 12 semanas con ivermectina o moxidectina según el conteo de huevos; antiinflamatorios como ketoprofeno 10 % a 2,2 mg/kg por vía endovenosa en cólicos y cojeras. Anestesia local con lidocaína 2 %.
Caninos y felinos: antipulgas y garrapatas con fipronil en pipeta mensual; meloxicam 2 % como antiinflamatorio a dosis ajustada por peso; complejo B en convalecencia. Todo tratamiento en pequeños animales requiere indicación del médico veterinario."""),
}

CONVERSACIONES = [
    ("demo-rc-01", "demo-v2", "daniela.rojas@enci.cl", "vendedor", "[DEMO] Dosis de ivermectina en bovinos",
     "¿Qué dosis de ivermectina 1 % uso en bovinos y cuál es el resguardo?",
     "Según el protocolo antiparasitario, la ivermectina al 1 % se aplica por vía subcutánea a 1 ml cada 50 kg de peso vivo, con un resguardo de 35 días antes de la faena. No debe usarse en vacas lecheras cuya leche sea para consumo humano.", "demo-doc-01"),
    ("demo-rc-02", "demo-v1", "matias.fuentes@enci.cl", "vendedor", "[DEMO] Objeción de calidad",
     "Un cliente dice que los genéricos son de menor calidad. ¿Qué le respondo?",
     "El argumentario sugiere responder con los registros del SAG y los certificados de lote, y destacar la equivalencia de principio activo y concentración. También puedes mencionar el stock en bodega central y el despacho en 48 horas.", "demo-doc-06"),
    ("demo-rc-03", "demo-v4", "camila.henriquez@enci.cl", "vendedor", "[DEMO] Tratamiento respiratorio",
     "¿Cómo se trata la enfermedad respiratoria bovina con tulatromicina?",
     "Tulatromicina 10 %: dosis única de 1 ml cada 40 kg por vía subcutánea, con resguardo de 49 días. Si no hay mejoría en 72 horas, cambiar de principio activo y consultar al veterinario.", "demo-doc-02"),
]


def borrar(db):
    for model, field in ((RagChunk, "documentoId"), (RagDocument, "id"), (RagConversation, "id")):
        n = db.query(model).filter(getattr(model, field).like("demo-%")).delete()
        print(f"{model.__tablename__}: {n} borrados")
    db.commit()


def main() -> None:
    with SessionLocal() as db:
        if "--borrar" in sys.argv:
            return borrar(db)
        for doc_id, (nombre, texto) in DOCS.items():
            content = texto.encode("utf-8")
            db.query(RagChunk).filter(RagChunk.documentoId == doc_id).delete()
            chunks = chunk_text(normalize_text(texto))
            add_chunks_to_index(db, chunks, [{"documento": nombre, "pagina": 1}] * len(chunks), doc_id)
            existing = db.get(RagDocument, doc_id)
            row = existing or RagDocument(id=doc_id)
            row.nombre = row.nombreOriginal = nombre
            row.descripcion = "[DEMO] Documento sintético"
            row.gcsPath = None
            row.chunks_count = len(chunks)
            row.subidoPor = ADMIN["uid"]
            row.subidoPorEmail = ADMIN["email"]
            row.tamano_bytes = len(content)
            row.activo = True
            row.estado = "listo"
            row.contentHash = hashlib.sha256(content).hexdigest()
            row.createdAt = row.updatedAt = NOW - timedelta(days=12)
            db.add(row)
            db.commit()
        for n, (cid, uid, email, rol, titulo, pregunta, respuesta, doc_id) in enumerate(CONVERSACIONES):
            ts = (NOW - timedelta(days=n + 1)).isoformat()
            fuente = {"documento": DOCS[doc_id][0], "pagina": "1", "fragmento": DOCS[doc_id][1][:160]}
            row = db.get(RagConversation, cid) or RagConversation(id=cid)
            row.usuarioId, row.usuarioEmail, row.rol, row.titulo = uid, email, rol, titulo
            row.mensajes = [
                {"tipo": "pregunta", "texto": pregunta, "timestamp": ts},
                {"tipo": "respuesta", "texto": respuesta, "timestamp": ts, "fuentes": [fuente], "tokens_usados": 0,
                 "sin_contexto": False, "diagnostico": None},
            ]
            row.createdAt = row.updatedAt = NOW - timedelta(days=n + 1)
            db.add(row)
            db.commit()
    print(f"Listo: {len(DOCS)} documentos RAG y {len(CONVERSACIONES)} conversaciones [DEMO].")


if __name__ == "__main__":
    main()
