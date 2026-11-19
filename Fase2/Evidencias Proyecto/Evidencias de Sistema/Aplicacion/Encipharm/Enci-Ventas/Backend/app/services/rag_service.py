import hashlib
import html
import io
import logging
import re
import unicodedata
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile, status

from app.core.odm import Session

from app.core.config import get_settings
from app.models.rag import NO_CONTEXT_RESPONSE
from app.models_sql.rag import RagDocument, RagConversation, RagChunk
from app.services.clientes import list_clientes
from app.services.comercial import list_interactions, list_opportunities, list_proposals
from app.services.dashboard import build_dashboard
from app.services.storage_service import (
    delete_document_blob,
    download_document_bytes,
    get_extension,
    upload_document_bytes,
)

logger = logging.getLogger(__name__)
from app.services import notificaciones
from app.services.users import list_users

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
STOPWORDS = {
    "a",
    "al",
    "algo",
    "como",
    "con",
    "cual",
    "cuales",
    "cuando",
    "de",
    "del",
    "dime",
    "donde",
    "el",
    "en",
    "es",
    "esta",
    "estan",
    "hay",
    "la",
    "las",
    "lo",
    "los",
    "me",
    "muestra",
    "para",
    "por",
    "que",
    "quien",
    "quienes",
    "son",
    "su",
    "sus",
    "todos",
    "todas",
    "un",
    "una",
    "y",
}
INTERNAL_DATA_TERMS = {
    "cliente",
    "clientes",
    "contacto",
    "crm",
    "forecast",
    "interaccion",
    "interacciones",
    "llamada",
    "oportunidad",
    "oportunidades",
    "pipeline",
    "propuesta",
    "propuestas",
    "reunion",
    "seguimiento",
    "usuario",
    "usuarios",
    "vendedor",
    "vendedores",
    "venta",
    "ventas",
}
CONVERSATIONAL_QUESTIONS = {
    "adios",
    "buenas",
    "buenas noches",
    "buenas tardes",
    "buenos dias",
    "chao",
    "como estas",
    "como te encuentras",
    "gracias",
    "hasta luego",
    "hola",
    "hola como estas",
    "muchas gracias",
    "necesito ayuda",
    "saludos",
    "tengo una duda",
    "tengo una pregunta",
}


class UserRateLimiter:
    """Rate limiter en memoria por usuario autenticado."""

    def __init__(self):
        self.window_seconds = 60
        self.requests: dict[str, list[float]] = {}

    def check(self, uid: str, limit: int) -> None:
        now = monotonic()
        timestamps = [
            timestamp
            for timestamp in self.requests.get(uid, [])
            if now - timestamp < self.window_seconds
        ]
        if len(timestamps) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de consultas alcanzado. Intenta nuevamente en un minuto.",
            )
        timestamps.append(now)
        self.requests[uid] = timestamps


rag_chat_rate_limiter = UserRateLimiter()
_embedding_model = None


def sanitize_question(value: str) -> str:
    """Elimina HTML y normaliza espacios antes de consultar el indice."""

    without_tags = re.sub(r"<[^>]*>", " ", value)
    return normalize_text(html.unescape(without_tags))


def _tokens(value: str) -> set[str]:
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    words = re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]{3,}", value.lower())
    return {word for word in words if word not in STOPWORDS}


def _safe_value(value: Any) -> str:
    if value is None:
        return "N/D"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _source(documento: str, pagina: str, text: str) -> dict:
    clean_text = normalize_text(text)
    return {
        "texto": clean_text,
        "documento": documento,
        "pagina": pagina,
        "fragmento": clean_text[:500],
    }


def _score_chunk(question_tokens: set[str], chunk: dict) -> int:
    chunk_tokens = _tokens(f"{chunk.get('documento', '')} {chunk.get('pagina', '')} {chunk.get('texto', '')}")
    return len(question_tokens & chunk_tokens)


def _count_by(items: list[dict], key: str) -> str:
    counter = Counter(_safe_value(item.get(key)) for item in items)
    if not counter:
        return "sin registros"
    return ", ".join(f"{name}: {total}" for name, total in counter.most_common(8))


def _format_user(user: dict) -> str:
    return (
        f"Usuario: {user.get('nombre')} | rol: {user.get('rol')} | "
        f"cargo: {user.get('cargo')} | rango: {user.get('rango')} | zona: {user.get('zona')} | "
        f"activo: {user.get('activo')} | webApp: {user.get('webApp')} | appMovil: {user.get('appMovil')}"
    )


def _format_cliente(cliente: dict) -> str:
    return (
        f"Cliente: {cliente.get('nombre')} | empresa: {cliente.get('empresa')} | "
        f"rubro: {cliente.get('rubro')} | region: {cliente.get('region')} | estado: {cliente.get('estado')}"
    )


def _format_opportunity(opportunity: dict, client_name: str) -> str:
    return (
        f"Oportunidad: {opportunity.get('titulo')} | cliente: {client_name} | "
        f"etapa: {opportunity.get('etapa')} | valorEstimado: {opportunity.get('valorEstimado')} | "
        f"probabilidad: {opportunity.get('probabilidad')}"
    )


def _format_proposal(proposal: dict, client_name: str, opportunity_name: str) -> str:
    return (
        f"Propuesta: {proposal.get('titulo')} | cliente: {client_name} | "
        f"oportunidad: {opportunity_name} | estado: {proposal.get('estado')} | "
        f"montoNeto: {proposal.get('montoNeto')} | montoTotal: {proposal.get('montoTotal')} | "
        f"descuentoPct: {proposal.get('descuentoPct')}"
    )


def _format_interaction(interaction: dict, client_name: str) -> str:
    return (
        f"Interaccion: {interaction.get('tipo')} | cliente: {client_name} | "
        f"fecha: {_safe_value(interaction.get('fecha'))} | resumen: {interaction.get('resumen')} | "
        f"resultado: {interaction.get('resultado')} | proximaAccion: {interaction.get('proximaAccion')}"
    )


def is_internal_data_question(question: str) -> bool:
    """Detecta consultas que requieren datos comerciales internos y Firestore."""

    return bool(_tokens(question) & INTERNAL_DATA_TERMS)


def is_conversational_question(question: str) -> bool:
    """Detecta frases cotidianas breves que no requieren recuperar fuentes."""

    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", question.lower())
        if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized in CONVERSATIONAL_QUESTIONS


def select_context_chunks(
    question: str,
    internal_chunks: list[dict],
    document_chunks: list[dict],
    limit: int,
) -> list[dict]:
    """Prioriza corpus o datos internos segun la intencion de la consulta."""

    if is_internal_data_question(question):
        return [*internal_chunks, *document_chunks][: limit * 2]
    if document_chunks:
        return document_chunks[:limit]
    return internal_chunks[:limit]


def build_internal_context_chunks(db, question: str, user: dict, limit: int = 16) -> list[dict]:
    """Construye contexto corporativo visible para responder preguntas internas amplias."""

    vendedor_uid = user.get("uid") if user.get("rol") == "vendedor" else None
    clientes = list_clientes(db, vendedor_uid=vendedor_uid, limit=120)
    opportunities = list_opportunities(db, user=user, limit=120)
    proposals = list_proposals(db, user=user, limit=120)
    interactions = list_interactions(db, user=user, limit=80)
    dashboard = build_dashboard(db, vendedor_uid=vendedor_uid)
    client_names = {
        cliente.get("id"): cliente.get("nombre") or cliente.get("empresa") or "Cliente no identificado"
        for cliente in clientes
    }
    opportunity_names = {
        opportunity.get("id"): opportunity.get("titulo") or "Oportunidad no identificada"
        for opportunity in opportunities
    }

    chunks = [
        _source(
            "CRM metricas",
            "dashboard",
            "Metricas internas: "
            + "; ".join(
                f"{key}: {value}"
                for key, value in dashboard.items()
                if key not in {"forecastMensual", "embudoVentas"}
            ),
        ),
        _source(
            "CRM clientes",
            "resumen",
            f"Total clientes visibles: {len(clientes)}. Por estado: {_count_by(clientes, 'estado')}. "
            f"Por region: {_count_by(clientes, 'region')}. Por rubro: {_count_by(clientes, 'rubro')}.",
        ),
        _source(
            "CRM oportunidades",
            "resumen",
            f"Total oportunidades visibles: {len(opportunities)}. Por etapa: {_count_by(opportunities, 'etapa')}.",
        ),
        _source(
            "CRM propuestas",
            "resumen",
            f"Total propuestas visibles: {len(proposals)}. Por estado: {_count_by(proposals, 'estado')}.",
        ),
    ]

    if user.get("rol") in {"supervisor", "admin"}:
        users = list_users(db, activo=None, limit=500)
        chunks.append(
            _source(
                "CRM usuarios",
                "resumen",
                f"Total usuarios registrados: {len(users)}. Por rol: {_count_by(users, 'rol')}. "
                f"Por zona: {_count_by(users, 'zona')}.",
            )
        )
        chunks.extend(
            _source("CRM usuarios", crm_user.get("nombre") or "usuario", _format_user(crm_user))
            for crm_user in users
        )
    else:
        chunks.append(_source("CRM usuarios", user.get("nombre") or "usuario actual", _format_user(user)))

    chunks.extend(
        _source("CRM clientes", cliente.get("nombre") or cliente.get("empresa") or "cliente", _format_cliente(cliente))
        for cliente in clientes
    )
    chunks.extend(
        _source(
            "CRM oportunidades",
            opportunity.get("titulo") or "oportunidad",
            _format_opportunity(
                opportunity,
                client_names.get(opportunity.get("clienteId"), "Cliente no identificado"),
            ),
        )
        for opportunity in opportunities
    )
    chunks.extend(
        _source(
            "CRM propuestas",
            proposal.get("titulo") or "propuesta",
            _format_proposal(
                proposal,
                client_names.get(proposal.get("clienteId"), "Cliente no identificado"),
                opportunity_names.get(proposal.get("oportunidadId"), "Oportunidad no identificada"),
            ),
        )
        for proposal in proposals
    )
    chunks.extend(
        _source(
            "CRM interacciones",
            f"{interaction.get('tipo') or 'interaccion'} con "
            f"{client_names.get(interaction.get('clienteId'), 'cliente no identificado')}",
            _format_interaction(
                interaction,
                client_names.get(interaction.get("clienteId"), "Cliente no identificado"),
            ),
        )
        for interaction in interactions
    )

    question_tokens = _tokens(question)
    if not question_tokens:
        return chunks[:limit]

    scored = [(_score_chunk(question_tokens, chunk), index, chunk) for index, chunk in enumerate(chunks)]
    minimum_score = 1 if is_internal_data_question(question) else 2
    relevant = [item for item in scored if item[0] >= minimum_score]
    if not relevant:
        return []

    relevant.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [chunk for _score, _index, chunk in relevant[:limit]]


def sanitize_filename(file_name: str) -> str:
    """Normaliza nombres de archivo para evitar rutas y caracteres inseguros."""

    path_name = Path(file_name or "documento").name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(path_name).stem).strip("._-") or "documento"
    suffix = Path(path_name).suffix.lower()
    return f"{stem[:80]}{suffix}"


def normalize_text(text: str) -> str:
    """Limpia caracteres de control y espacios redundantes."""

    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Divide texto en chunks por palabra, con overlap para preservar contexto."""

    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for index in range(0, len(words), step):
        chunk = " ".join(words[index:index + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _load_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Indice semantico no disponible",
            ) from error
        _embedding_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    return _embedding_model


def reset_index_collection(db: Session) -> None:
    """Recrea la coleccion vectorial local para reindexaciones completas."""
    db.query(RagChunk).delete()
    db.commit()


def add_chunks_to_index(db: Session, chunks: list[str], metadata: list[dict], doc_id: str) -> None:
    """Genera embeddings y persiste los fragmentos en Firestore (con su vector)."""
    if not chunks:
        return
    embeddings = [list(e) for e in _load_embedding_model().embed(chunks)]
    rag_chunks = []
    for index, chunk_text in enumerate(chunks):
        meta = metadata[index]
        rag_chunks.append(RagChunk(
            documentoId=doc_id,
            documentoNombre=meta.get("documento"),
            pagina=meta.get("pagina"),
            texto=chunk_text,
            embedding=embeddings[index]
        ))
    db.add_all(rag_chunks)
    db.commit()


def search_similar_chunks(db: Session, query: str, n_results: int | None = None) -> list[dict]:
    """Combina similitud semantica y coincidencias lexicas para recuperar documentos."""
    settings = get_settings()
    try:
        query_embedding = list(list(_load_embedding_model().embed([query]))[0])
    except HTTPException:
        return []

    result_limit = n_results or settings.MAX_CONTEXT_CHUNKS
    candidate_limit = max(result_limit * 4, 20)

    results = db.nearest(RagChunk, "embedding", query_embedding, candidate_limit)

    if not results:
        return []

    query_tokens = _tokens(query)
    candidates = []

    for chunk, distance in results:
        similarity = 1 - distance
        document_name = chunk.documentoNombre or ""
        document = chunk.texto

        name_tokens = _tokens(document_name)
        content_tokens = _tokens(document)
        token_count = max(1, len(query_tokens))
        name_coverage = len(query_tokens & name_tokens) / token_count
        content_coverage = len(query_tokens & content_tokens) / token_count
        hybrid_score = similarity + (name_coverage * 0.45) + (content_coverage * 0.15)

        if similarity >= settings.SIMILARITY_THRESHOLD or name_coverage > 0 or content_coverage >= 0.5:
            candidates.append({
                "texto": document,
                "documento": document_name,
                "pagina": str(chunk.pagina),
                "fragmento": document[:500],
                "similarity": round(similarity, 4),
                "hybrid_score": round(hybrid_score, 4),
            })

    if not candidates:
        return []

    candidates.sort(key=lambda chunk: chunk["hybrid_score"], reverse=True)
    relevance_floor = candidates[0]["hybrid_score"] - 0.25
    unique_chunks = []
    seen = set()
    for candidate in candidates:
        if candidate["hybrid_score"] < relevance_floor:
            continue
        deduplication_key = (
            candidate["documento"],
            candidate["pagina"],
            normalize_text(candidate["texto"]).lower(),
        )
        if deduplication_key in seen:
            continue
        seen.add(deduplication_key)
        candidate.pop("hybrid_score")
        unique_chunks.append(candidate)
        if len(unique_chunks) >= result_limit:
            break
    return unique_chunks


async def read_upload_bytes(file: UploadFile) -> bytes:
    """Lee el archivo multipart y valida el limite de tamano (RAG_MAX_UPLOAD_BYTES, 25 MB)."""

    settings = get_settings()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Archivo vacio")
    if len(content) > settings.RAG_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el tamano maximo de {settings.RAG_MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    return content


def validate_document_file(file_name: str, content: bytes) -> tuple[str, str]:
    """Valida extension y firma real del archivo antes de procesarlo."""

    extension = get_extension(file_name)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Formato no permitido")
    if extension == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El archivo PDF no es valido")
    if extension == ".docx":
        try:
            with ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="El archivo DOCX no es valido",
                    )
        except BadZipFile as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El archivo DOCX no es valido",
            ) from error
    if extension == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El archivo TXT debe estar codificado en UTF-8",
            ) from error
    return extension, MIME_BY_EXTENSION[extension]


def extract_text_by_page(file_name: str, content: bytes) -> list[tuple[int, str]]:
    """Extrae texto por pagina aproximada segun el formato del documento."""

    extension = get_extension(file_name)
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise HTTPException(status_code=503, detail="Extractor PDF no disponible") from error
        reader = PdfReader(io.BytesIO(content))
        return [
            (page_index + 1, normalize_text(page.extract_text() or ""))
            for page_index, page in enumerate(reader.pages)
        ]
    if extension == ".docx":
        try:
            from docx import Document
        except ImportError as error:
            raise HTTPException(status_code=503, detail="Extractor DOCX no disponible") from error
        document = Document(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return [(1, normalize_text(text))]
    return [(1, normalize_text(content.decode("utf-8")))]


def index_document_content(db: Session, file_name: str, content: bytes, doc_id: str, user: dict) -> int:
    """Extrae, fragmenta e indexa el contenido documental validado."""

    metadata = []
    chunks = []
    for page, page_text in extract_text_by_page(file_name, content):
        for chunk in chunk_text(page_text):
            chunks.append(chunk)
            metadata.append(
                {
                    "documento": file_name,
                    "pagina": page,
                    "subido_por": user.get("uid", ""),
                    "fecha": datetime.now(timezone.utc).isoformat(),
                }
            )
    add_chunks_to_index(db, chunks, metadata, doc_id)
    return len(chunks)


def save_conversation_turn(
    db: Session,
    user: dict,
    pregunta: str,
    respuesta: str,
    fuentes: list[dict],
    tokens_usados: int,
    sin_contexto: bool,
    diagnostico: dict | None = None,
    conversacion_id: str | None = None,
    titulo: str | None = None,
) -> str:
    """Persiste pregunta y respuesta usando SQLAlchemy."""
    
    now = datetime.now(timezone.utc)
    message_timestamp = now
    conversation_id = conversacion_id or str(uuid.uuid4())
    
    conversation = db.query(RagConversation).filter(RagConversation.id == conversation_id).first()
    
    if conversation:
        if conversation.usuarioId != user.get("uid"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos para esta conversacion")
        
        messages = list(conversation.mensajes) if conversation.mensajes else []
        conversation_title = conversation.titulo or titulo
    else:
        messages = []
        conversation_title = titulo
        conversation = RagConversation(
            id=conversation_id,
            usuarioId=user.get("uid"),
            usuarioEmail=user.get("email", ""),
            rol=user.get("rol", "vendedor"),
            titulo=conversation_title,
            createdAt=now,
        )
        db.add(conversation)

    messages.extend([
        {"tipo": "pregunta", "texto": pregunta, "timestamp": message_timestamp.isoformat()},
        {
            "tipo": "respuesta",
            "texto": respuesta,
            "timestamp": message_timestamp.isoformat(),
            "fuentes": fuentes,
            "tokens_usados": tokens_usados,
            "sin_contexto": sin_contexto,
            "diagnostico": diagnostico,
        },
    ])
    
    conversation.mensajes = messages
    conversation.updatedAt = now
    conversation.titulo = conversation_title
    
    db.commit()
    return conversation_id


def register_document(db: Session, doc_id: str, file_name: str, original_name: str, gcs_path: str, chunks: int, size: int, user: dict) -> None:
    """Registra metadatos auditables del documento en PostgreSQL."""
    now = datetime.now(timezone.utc)
    doc = RagDocument(
        id=doc_id,
        nombre=file_name,
        nombreOriginal=original_name,
        descripcion="",
        gcsPath=gcs_path,
        chunks_count=chunks,
        subidoPor=user.get("uid"),
        subidoPorEmail=user.get("email", ""),
        tamano_bytes=size,
        activo=True,
        createdAt=now,
        updatedAt=now,
    )
    db.add(doc)
    db.commit()


def list_documents(db: Session) -> list[dict]:
    """Lista documentos RAG activos e inactivos ordenados por fecha."""
    docs = db.query(RagDocument).order_by(RagDocument.createdAt.desc()).all()
    return [
        {
            "id": d.id,
            "nombre": d.nombre,
            "nombreOriginal": d.nombreOriginal,
            "descripcion": d.descripcion,
            "gcsPath": d.gcsPath,
            "chunks_count": d.chunks_count,
            "indexadoEn": d.createdAt.isoformat() if d.createdAt else None,
            "subidoPor": d.subidoPor,
            "subidoPorEmail": d.subidoPorEmail,
            "tamano_bytes": d.tamano_bytes,
            "activo": d.activo,
            "estado": d.estado,
            "error": d.errorMensaje,
        }
        for d in docs
    ]


def list_conversations(db: Session, user: dict, limit: int = 50) -> list[dict]:
    """Lista exclusivamente las conversaciones pertenecientes a la cuenta autenticada."""
    conversations = db.query(RagConversation).filter(RagConversation.usuarioId == user.get("uid")).order_by(RagConversation.updatedAt.desc()).limit(limit).all()
    
    return [
        {
            "id": c.id,
            "usuarioId": c.usuarioId,
            "usuarioEmail": c.usuarioEmail,
            "rol": c.rol,
            "titulo": c.titulo,
            "mensajes": c.mensajes,
            "createdAt": c.createdAt,
            "updatedAt": c.updatedAt,
        }
        for c in conversations
    ]


def upload_and_index_document(db: Session, file_name: str, content: bytes, content_type: str, user: dict) -> dict:
    """Sube documento a GCS, lo indexa y registra auditoria."""

    doc_id = str(uuid.uuid4())
    safe_name = sanitize_filename(file_name)
    gcs_path = upload_document_bytes(safe_name, content, content_type)
    # rag_chunks.documentoId tiene FK a rag_documentos: el documento se registra
    # primero y sus chunks despues; si la indexacion falla se revierte el registro.
    register_document(db, doc_id, safe_name, file_name, gcs_path, 0, len(content), user)
    try:
        chunks = index_document_content(db, safe_name, content, doc_id, user)
    except Exception:
        db.rollback()
        db.query(RagChunk).filter(RagChunk.documentoId == doc_id).delete()
        db.query(RagDocument).filter(RagDocument.id == doc_id).delete()
        db.commit()
        raise
    document = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    document.chunks_count = chunks
    document.updatedAt = datetime.now(timezone.utc)
    db.commit()
    return {"documento": safe_name, "chunks_indexados": chunks}


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def ensure_not_duplicate(db: Session, safe_name: str, hash_value: str) -> None:
    """Avisa si el archivo ya estaba subido: mismo contenido (aunque cambie el nombre) o mismo nombre."""
    existing = db.query(RagDocument).filter(RagDocument.contentHash == hash_value, RagDocument.activo.is_(True)).first()
    reason = "contenido"
    if existing is None:
        existing = db.query(RagDocument).filter(RagDocument.nombre == safe_name, RagDocument.activo.is_(True)).first()
        reason = "nombre"
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": f"Ya existe un documento con el mismo {reason}: {existing.nombre}",
                "codigo": "ERR_DOCUMENTO_DUPLICADO",
                "detalles": {"motivo": reason, "documento": existing.nombre, "documentoId": existing.id},
            },
        )


def register_uploaded_document(
    db: Session, doc_id: str, safe_name: str, original_name: str, path: str, content: bytes, user: dict
) -> RagDocument:
    """Registra el documento recien subido (estado "subido"); la indexacion corre despues."""
    now = datetime.now(timezone.utc)
    doc = RagDocument(
        id=doc_id, nombre=safe_name, nombreOriginal=original_name, descripcion="", gcsPath=path, chunks_count=0,
        subidoPor=user.get("uid"), subidoPorEmail=user.get("email", ""), tamano_bytes=len(content), activo=True,
        estado="subido", contentHash=content_hash(content), createdAt=now, updatedAt=now,
    )
    db.add(doc)
    db.commit()
    return doc


def _failure_reason(error: Exception) -> str:
    if isinstance(error, HTTPException):
        detail = error.detail
        text = detail.get("error") if isinstance(detail, dict) else detail
        return str(text)[:500]
    return f"{type(error).__name__}: {error}"[:500]


def process_document(session_factory, doc_id: str, safe_name: str, content: bytes, user: dict) -> None:
    """Indexa un documento ya subido y deja su estado en "listo" o "error" (con el motivo).

    Corre en segundo plano con su propia sesion: la de la peticion ya se cerro.
    """
    with session_factory() as db:
        doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
        if doc is None:
            return
        doc.estado = "procesando"
        db.commit()
        try:
            chunks = index_document_content(db, safe_name, content, doc_id, user)
            doc.chunks_count = chunks
            if chunks == 0:
                doc.estado = "error"
                doc.errorMensaje = "No se pudo extraer texto del documento (¿es un PDF escaneado?)."
            else:
                doc.estado = "listo"
                doc.errorMensaje = None
        except Exception as error:
            db.rollback()
            db.query(RagChunk).filter(RagChunk.documentoId == doc_id).delete()
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            doc.estado = "error"
            doc.chunks_count = 0
            doc.errorMensaje = _failure_reason(error)
        doc.updatedAt = datetime.now(timezone.utc)
        ok = doc.estado == "listo"
        notificaciones.notificar_admins(
            db, notificaciones.TIPO_DOCUMENTO,
            f"Documento listo: {doc.nombre}" if ok else f"Falló la indexación de {doc.nombre}",
            mensaje=None if ok else doc.errorMensaje,
            enlace="/configuracion", referencia=f"{doc_id}:{doc.estado}",
        )
        db.commit()


def delete_document(db: Session, doc_id: str) -> None:
    """Quita el documento del indice (el chat deja de citarlo), del almacenamiento y de la lista."""
    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    db.query(RagChunk).filter(RagChunk.documentoId == doc_id).delete()
    path = doc.gcsPath
    db.delete(doc)
    db.commit()
    if path:
        try:
            delete_document_blob(path)
        except Exception:
            # El documento ya no existe para el sistema; un blob huerfano no debe fallar la baja.
            logger.warning("No se pudo borrar el blob %s", path)


def reindex_documents(db: Session, user: dict) -> int:
    """Reconstruye el indice vectorial desde documentos activos en GCS."""

    reset_index_collection(db)
    indexed_chunks = 0
    for document in list_documents(db):
        if not document.get("activo", True) or not document.get("gcsPath"):
            continue
        content = download_document_bytes(document["gcsPath"])
        chunks = index_document_content(db, document["nombre"], content, document["id"], user)
        indexed_chunks += chunks
        
        doc = db.query(RagDocument).filter(RagDocument.id == document["id"]).first()
        if doc:
            doc.chunks_count = chunks
            doc.estado = "listo" if chunks else "error"
            doc.errorMensaje = None if chunks else "No se pudo extraer texto del documento."
            doc.updatedAt = datetime.now(timezone.utc)
            db.commit()
            
    return indexed_chunks


def no_context_payload(question: str = "") -> tuple[str, list[dict], int, bool]:
    """Responde interacciones cotidianas y orienta consultas fuera del alcance del asistente."""

    normalized_question = "".join(
        character
        for character in unicodedata.normalize("NFKD", question.lower())
        if not unicodedata.combining(character)
    )
    tokens = _tokens(question)
    if "como estas" in normalized_question or "como te encuentras" in normalized_question:
        response = (
            "Estoy bien y listo para ayudarte. Mi funcion es responder consultas tecnicas y comerciales de Enci, "
            "incluyendo el corpus documental y los datos internos disponibles para tu cuenta."
        )
    elif tokens & {"hola", "buenas", "saludos"}:
        response = (
            "Hola. Soy el Asistente Enci y estoy listo para ayudarte. "
            "Puedes consultarme sobre productos, documentos, sanidad animal, clientes, oportunidades e interacciones."
        )
    elif tokens & {"duda", "pregunta", "ayuda", "consultar"}:
        response = (
            "Claro, escribe tu duda con tus propias palabras. Puedes preguntar, por ejemplo, por un producto, "
            "una norma sanitaria, un cliente, una oportunidad o la ultima interaccion registrada."
        )
    elif tokens & {"gracias", "agradecido", "agradecida"}:
        response = "De nada. Cuando quieras, puedes hacer otra consulta tecnica o comercial sobre Enci."
    elif tokens & {"adios", "chao", "hasta", "luego"}:
        response = "Hasta luego. Quedo disponible para tus proximas consultas tecnicas o comerciales de Enci."
    else:
        response = NO_CONTEXT_RESPONSE
    return response, [], 0, True
