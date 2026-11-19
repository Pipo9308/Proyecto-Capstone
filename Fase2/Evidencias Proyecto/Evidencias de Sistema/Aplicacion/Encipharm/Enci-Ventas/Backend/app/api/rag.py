import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.auth import require_role
from app.core.config import get_settings
from app.models.rag import (
    RagChatRequest,
    RagChatResponse,
    RagConversationResponse,
    RagDocumentResponse,
    RagResponseDiagnostics,
    RagSource,
    RagUploadAccepted,
)
from app.core.db import SessionLocal, get_db
from app.core.odm import Session
from app.services import solo_animales
from app.services.llm_service import (
    build_system_prompt,
    build_user_prompt,
    call_deepseek,
    generate_conversation_title,
    generate_conversation_titles,
    normalize_conversation_title,
)
from app.services.rag_service import (
    build_internal_context_chunks,
    content_hash,
    delete_document,
    ensure_not_duplicate,
    process_document,
    register_uploaded_document,
    sanitize_filename,
    is_conversational_question,
    is_internal_data_question,
    list_conversations,
    list_documents,
    no_context_payload,
    rag_chat_rate_limiter,
    read_upload_bytes,
    reindex_documents,
    sanitize_question,
    save_conversation_turn,
    search_similar_chunks,
    select_context_chunks,
    validate_document_file,
)
from app.services.storage_service import upload_document_bytes


router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/chat", response_model=RagChatResponse)
async def chat_with_rag(
    payload: RagChatRequest,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    """Responde preguntas usando exclusivamente fragmentos recuperados del corpus interno."""

    settings = get_settings()
    rag_chat_rate_limiter.check(user["uid"], settings.RAG_CHAT_RATE_LIMIT_PER_MINUTE)
    pregunta = sanitize_question(payload.pregunta)
    if not pregunta:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La pregunta no puede estar vacia")

    bloqueada = solo_animales.consulta_humana(pregunta)  # se responde con la frase fija, sin buscar ni llamar al modelo
    conversational_question = is_conversational_question(pregunta)
    document_chunks = [] if (conversational_question or bloqueada) else await run_in_threadpool(
        search_similar_chunks,
        db,
        pregunta,
        settings.MAX_CONTEXT_CHUNKS,
    )
    internal_chunks = []
    if not conversational_question and not bloqueada and (is_internal_data_question(pregunta) or not document_chunks):
        internal_chunks = await run_in_threadpool(
            build_internal_context_chunks,
            db,
            pregunta,
            user,
            settings.MAX_CONTEXT_CHUNKS * 3,
        )
    chunks = select_context_chunks(
        pregunta,
        internal_chunks,
        document_chunks,
        settings.MAX_CONTEXT_CHUNKS,
    )

    if chunks and not bloqueada:
        llm_response = await call_deepseek(build_system_prompt(), build_user_prompt(pregunta, chunks))
        respuesta = llm_response["texto"]
        tokens_usados = llm_response["tokens"]
        fuentes = [
            {
                "documento": chunk["documento"],
                "pagina": chunk.get("pagina"),
                "fragmento": chunk.get("fragmento") or chunk["texto"][:500],
            }
            for chunk in chunks
        ]
        sin_contexto = False
        diagnostico = RagResponseDiagnostics(
            origen="deepseek",
            proveedor="DeepSeek",
            modelo=llm_response.get("modelo", settings.DEEPSEEK_MODEL),
            fragmentos_documentales=len(document_chunks),
            fragmentos_internos=len(internal_chunks),
        )
    else:
        respuesta, fuentes, tokens_usados, sin_contexto = no_context_payload(pregunta)
        diagnostico = RagResponseDiagnostics(
            origen="local",
            proveedor="Motor local Enci",
            fragmentos_documentales=0,
            fragmentos_internos=0,
        )

    if bloqueada or solo_animales.respuesta_humana(respuesta):
        solo_animales.registrar("pregunta bloqueada" if bloqueada else "respuesta reemplazada", pregunta if bloqueada else respuesta)
        respuesta, fuentes, sin_contexto = solo_animales.FRASE_FIJA, [], True

    conversation_title = None
    if not payload.conversacion_id:
        try:
            conversation_title = await generate_conversation_title(pregunta)
        except (HTTPException, ValueError, KeyError, TypeError):
            conversation_title = normalize_conversation_title("", pregunta)

    conversation_id = await run_in_threadpool(
        save_conversation_turn,
        db,
        user,
        pregunta,
        respuesta,
        fuentes,
        tokens_usados,
        sin_contexto,
        diagnostico.model_dump(),
        payload.conversacion_id,
        conversation_title,
    )

    return RagChatResponse(
        respuesta=respuesta,
        fuentes=[RagSource(**source) for source in fuentes],
        conversacion_id=conversation_id,
        tokens_usados=tokens_usados,
        timestamp=datetime.now(timezone.utc),
        diagnostico=diagnostico,
        titulo_conversacion=conversation_title,
    )


@router.get("/conversations", response_model=list[RagConversationResponse])
async def get_rag_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    """Lista conversaciones RAG segun alcance de rol."""

    conversations = await run_in_threadpool(list_conversations, db, user, limit)
    conversations_without_title = []
    for conversation in conversations:
        if conversation.get("titulo"):
            continue
        first_question = next(
            (
                message.get("texto", "")
                for message in conversation.get("mensajes", [])
                if message.get("tipo") == "pregunta" and message.get("texto")
            ),
            "",
        )
        if first_question:
            conversations_without_title.append((conversation, first_question))

    if conversations_without_title:
        try:
            generated_titles = await generate_conversation_titles(
                [question for _conversation, question in conversations_without_title]
            )
            for (conversation, _question), title in zip(
                conversations_without_title,
                generated_titles,
                strict=True,
            ):
                # (Mock updating for now, or just let it be memory)
                conversation["titulo"] = title
        except (HTTPException, ValueError, KeyError, TypeError):
            pass

    return conversations


def get_rag_session_factory():
    """Sesiones propias para el procesamiento en segundo plano (la de la peticion ya se cerro)."""
    return SessionLocal


@router.post("/documents/upload", response_model=RagUploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_rag_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
    session_factory=Depends(get_rag_session_factory),
):
    """Guarda el documento y lo indexa en segundo plano.

    Responde enseguida (202); el estado pasa por subido -> procesando -> listo | error y se ve
    en GET /rag/documents. Un archivo repetido (mismo contenido o nombre) se rechaza con 409.
    """

    content = await read_upload_bytes(file)
    _extension, content_type = validate_document_file(file.filename or "", content)
    safe_name = sanitize_filename(file.filename or "documento")
    ensure_not_duplicate(db, safe_name, content_hash(content))
    path = await run_in_threadpool(upload_document_bytes, safe_name, content, content_type)
    document = register_uploaded_document(db, str(uuid.uuid4()), safe_name, file.filename or "documento", path, content, user)
    background_tasks.add_task(process_document, session_factory, document.id, safe_name, content, user)
    return RagUploadAccepted(
        id=document.id, documento=safe_name, estado="subido",
        mensaje="Documento recibido: se esta indexando. Estara disponible para preguntas en unos minutos.",
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_document(
    document_id: str,
    user: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Elimina el documento: sale del indice (el chat deja de citarlo) y del almacenamiento."""

    await run_in_threadpool(delete_document, db, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/reindex")
async def reindex_rag_documents(user: dict = Depends(require_role("admin")), db: Session = Depends(get_db)):
    """Reconstruye el indice vectorial desde los documentos activos almacenados."""

    chunks = await run_in_threadpool(reindex_documents, db, user)
    return {"mensaje": "Documentos reindexados exitosamente", "chunks_indexados": chunks}


@router.get("/documents", response_model=list[RagDocumentResponse])
async def get_rag_documents(user: dict = Depends(require_role("admin")), db: Session = Depends(get_db)):
    """Lista documentos disponibles en el corpus RAG."""

    return await run_in_threadpool(list_documents, db)
