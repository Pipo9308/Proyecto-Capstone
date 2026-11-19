import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from app.core.odm import Session
from app.core.odm import or_

from app.models.cliente import ClienteCreate, ClienteCreateRequest
from app.models_sql.cliente import Cliente
from app.models_sql.user import User
from app.services import notificaciones


MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 1_000
MAX_CLIENTES_RESPONSE = 500
CSV_FIELDS = {
    "nombre",
    "empresa",
    "rut",
    "email",
    "telefono",
    "rubro",
    "region",
    "estado",
    "vendedorUid",
    "ownerUid",
}

EMAIL_ADAPTER = TypeAdapter(EmailStr)


def _safe_text(value: Any, fallback: str, max_length: int | None = None) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()
    else:
        text = fallback
    return text[:max_length] if max_length else text


def _safe_optional_text(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_length]


def _safe_phone(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("569") and len(digits) >= 11:
        return digits[3:11]
    if digits.startswith("9") and len(digits) >= 9:
        return digits[1:9]
    return digits[:8] if len(digits) >= 8 else None


def _safe_optional_uid(value: Any) -> str | None:
    return _safe_optional_text(value, 128)


def _safe_email(value: Any, cliente_id: str) -> str:
    if isinstance(value, str):
        try:
            return str(EMAIL_ADAPTER.validate_python(value.strip()))
        except ValidationError:
            pass

    clean_id = "".join(ch for ch in str(cliente_id).lower() if ch.isalnum()) or "legacy"
    return f"sin-correo-{clean_id[:48]}@enci.cl"


def _safe_estado(value: Any) -> str:
    return value if value in {"En proceso", "Completado", "Inactivo"} else "En proceso"


def _cliente_model_to_dict(cliente: Cliente) -> dict[str, Any]:
    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "empresa": cliente.empresa,
        "rut": cliente.rut,
        "email": cliente.email,
        "telefono": cliente.telefono,
        "rubro": cliente.rubro,
        "region": cliente.region,
        "estado": cliente.estado,
        "vendedorUid": cliente.vendedorUid,
        "ownerUid": cliente.ownerUid,
        "createdAt": cliente.createdAt,
        "updatedAt": cliente.updatedAt,
    }


def list_clientes(
    db: Session,
    search: str | None = None,
    estado: str | None = None,
    vendedor_uid: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if limit is not None:
        limit = min(max(limit, 1), MAX_CLIENTES_RESPONSE)
        
    query = db.query(Cliente).filter(Cliente.estado != "Eliminado")
    
    if vendedor_uid:
        query = query.filter(
            or_(Cliente.vendedorUid == vendedor_uid, Cliente.ownerUid == vendedor_uid)
        )
        
    if estado:
        query = query.filter(Cliente.estado.ilike(estado))
        
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Cliente.nombre.ilike(search_term),
                Cliente.empresa.ilike(search_term),
                Cliente.rut.ilike(search_term),
                Cliente.email.ilike(search_term),
                Cliente.rubro.ilike(search_term),
                Cliente.region.ilike(search_term),
            )
        )
        
    # Sin ORDER BY el orden era arbitrario: el cliente recien creado caia en la pagina 2 de la lista
    # (y, con tope, podia quedar fuera). Del mas nuevo al mas antiguo, con desempate estable.
    query = query.order_by(Cliente.createdAt.desc(), Cliente.id)

    if limit is not None:
        query = query.limit(limit)

    clientes = query.all()
    return [_cliente_model_to_dict(c) for c in clientes]


def get_cliente_or_404(db: Session, cliente_id: str) -> dict[str, Any]:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.estado != "Eliminado").first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return _cliente_model_to_dict(cliente)


def _normalized_email(value: str) -> str:
    return str(value or "").strip().lower()


def _ensure_unique_cliente_email(
    db: Session,
    email: str | None,
    exclude_cliente_id: str | None = None,
) -> None:
    normalized_email = _normalized_email(email)
    if not normalized_email:
        return
        
    query = db.query(Cliente).filter(Cliente.email == normalized_email, Cliente.estado != "Eliminado")
    if exclude_cliente_id:
        query = query.filter(Cliente.id != exclude_cliente_id)
        
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Ya existe un cliente activo con ese email",
                "codigo": "ERR_EMAIL_DUPLICADO",
                "detalles": {"campo": "email"},
            },
        )


def _ensure_unique_cliente_rut(db: Session, rut: str | None, exclude_cliente_id: str | None = None) -> None:
    """Un RUT identifica a un solo cliente activo; el error dice cual es y quien lo tiene asignado."""
    if not rut:
        return
    query = db.query(Cliente).filter(Cliente.rut == rut, Cliente.estado != "Eliminado")
    if exclude_cliente_id:
        query = query.filter(Cliente.id != exclude_cliente_id)
    existing = query.first()
    if not existing:
        return
    owner = db.query(User).filter(User.id == (existing.vendedorUid or existing.ownerUid)).first()
    owner_name = owner.nombre if owner else "sin vendedor asignado"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": f"Ya existe un cliente con ese RUT: {existing.empresa} (asignado a {owner_name})",
            "codigo": "ERR_RUT_DUPLICADO",
            "detalles": {"campo": "rut", "clienteId": existing.id, "empresa": existing.empresa, "vendedor": owner_name},
        },
    )


def ensure_assignee_exists(db: Session, uid: str | None, field: str) -> None:
    """Asignar a un usuario inexistente terminaba en un error 500 de clave foranea.
    Se llama desde la API (input real); el servicio interno no lo exige."""
    if uid and not db.query(User.id).filter(User.id == uid, User.activo.is_(True)).first():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "El vendedor asignado no existe o esta inactivo",
                "codigo": "ERR_VENDEDOR_INVALIDO",
                "detalles": {"campo": field},
            },
        )


def _notify_assignment(db: Session, cliente: Cliente, *, previous_vendedor: str | None, user: dict[str, Any] | None) -> None:
    """Avisa al vendedor al que otro usuario le asigna (o reasigna) un cliente."""
    if not user or not cliente.vendedorUid or cliente.vendedorUid in (previous_vendedor, user.get("uid")):
        return
    notificaciones.crear(
        db, cliente.vendedorUid, notificaciones.TIPO_CLIENTE,
        f"Te asignaron el cliente {cliente.empresa}",
        mensaje=f"Asignado por {user.get('nombre') or 'un supervisor'}.",
        enlace=f"/clientes/{cliente.id}", referencia=f"{cliente.id}:{cliente.vendedorUid}",
    )


def create_cliente(db: Session, payload: ClienteCreate, user: dict[str, Any] | None = None) -> dict[str, Any]:
    _ensure_unique_cliente_email(db, payload.email)
    _ensure_unique_cliente_rut(db, payload.rut)

    data = payload.model_dump()
    if data.get("vendedorUid") and not data.get("ownerUid"):
        data["ownerUid"] = data["vendedorUid"]
    if data.get("ownerUid") and not data.get("vendedorUid"):
        data["vendedorUid"] = data["ownerUid"]
        
    # El email es opcional; si viene, se guarda en minuscula (asi se compara la unicidad).
    data["email"] = _normalized_email(_safe_email(data["email"], "legacy")) if data.get("email") else None
    data["nombre"] = _safe_text(data.get("nombre"), "Sin nombre", 120)
    data["empresa"] = _safe_text(data.get("empresa"), "Sin empresa", 160)
    data["estado"] = _safe_estado(data.get("estado"))
        
    nuevo_cliente = Cliente(**data)
    db.add(nuevo_cliente)
    db.flush()
    _notify_assignment(db, nuevo_cliente, previous_vendedor=None, user=user)
    db.commit()
    db.refresh(nuevo_cliente)
    
    # TODO: Implementar un audit nativo a SQL
    # if user:
    #     record_audit_event(
    #         db,
    #         user=user,
    #         action="create",
    #         resource="clientes",
    #         resource_id=nuevo_cliente.id,
    #     )
    return _cliente_model_to_dict(nuevo_cliente)


def update_cliente(
    db: Session,
    cliente_id: str,
    changes: dict[str, Any],
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.estado != "Eliminado").first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    clean_changes = {
        key: value
        for key, value in changes.items()
        if value is not None
    }
    
    if clean_changes.get("email"):
        clean_changes["email"] = _normalized_email(str(clean_changes["email"]))
        _ensure_unique_cliente_email(db, clean_changes["email"], exclude_cliente_id=cliente_id)
    if clean_changes.get("rut"):
        _ensure_unique_cliente_rut(db, clean_changes["rut"], exclude_cliente_id=cliente_id)

    previous_vendedor = cliente.vendedorUid
    for key, value in clean_changes.items():
        if hasattr(cliente, key):
            setattr(cliente, key, value)

    cliente.updatedAt = datetime.now(timezone.utc)
    _notify_assignment(db, cliente, previous_vendedor=previous_vendedor, user=user)
    db.commit()
    db.refresh(cliente)

    return _cliente_model_to_dict(cliente)


def delete_cliente(db: Session, cliente_id: str, user: dict[str, Any] | None = None) -> None:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente or cliente.estado == "Eliminado":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )

    cliente.estado = "Eliminado"
    cliente.updatedAt = datetime.now(timezone.utc)
    db.commit()


def parse_clientes_csv(raw_content: bytes) -> tuple[list[ClienteCreate], list[dict[str, Any]], int]:
    rows, errores, total_rows = _parse_clientes_rows(raw_content)
    return [cliente for _, cliente in rows], errores, total_rows


def _parse_clientes_rows(raw_content: bytes) -> tuple[list[tuple[int, ClienteCreate]], list[dict[str, Any]], int]:
    """Filas validas con su numero real en el archivo (para reportar duplicados en la fila correcta)."""
    if len(raw_content) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="El archivo CSV supera el tamano maximo de 1 MB",
        )

    try:
        text = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV debe estar codificado en UTF-8",
        ) from error

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV no contiene encabezados",
        )

    unknown_fields = set(reader.fieldnames) - CSV_FIELDS
    if unknown_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Columnas no soportadas: {', '.join(sorted(unknown_fields))}",
        )

    clientes: list[tuple[int, ClienteCreate]] = []
    errores: list[dict[str, Any]] = []
    total_rows = 0

    for row_number, row in enumerate(reader, start=2):
        total_rows += 1
        if total_rows > MAX_CSV_ROWS:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"El archivo CSV supera el maximo de {MAX_CSV_ROWS} filas",
            )
        clean_row = {
            key: (value.strip() if isinstance(value, str) else value)
            for key, value in row.items()
            if key in CSV_FIELDS
        }
        clean_row = {
            key: value
            for key, value in clean_row.items()
            if value not in (None, "")
        }

        try:
            clientes.append((row_number, ClienteCreateRequest.model_validate(clean_row)))
        except ValidationError as exc:
            errores.append({
                "fila": row_number,
                "errores": [
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()
                ],
            })

    return clientes, errores, total_rows


def import_clientes_csv(
    db: Session,
    raw_content: bytes,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clientes, errores, total_rows = _parse_clientes_rows(raw_content)

    seen_emails: set[str] = set()
    seen_ruts: set[str] = set()
    existing = list_clientes(db, limit=None)
    existing_emails = {
        str(cliente.get("email") or "").strip().lower()
        for cliente in existing
        if cliente.get("email")
    }
    existing_ruts = {cliente["rut"] for cliente in existing if cliente.get("rut")}

    for index, cliente in clientes:
        email = (cliente.email or "").strip().lower()
        row_errors = []
        if email and email in seen_emails:
            row_errors.append("email: correo duplicado dentro del archivo")
        if email and email in existing_emails:
            row_errors.append("email: cliente ya existe en el CRM")
        if cliente.rut in seen_ruts:
            row_errors.append("rut: RUT duplicado dentro del archivo")
        if cliente.rut in existing_ruts:
            row_errors.append("rut: cliente con ese RUT ya existe en el CRM")
        if row_errors:
            errores.append({
                "fila": index,
                "errores": row_errors,
            })
        if email:
            seen_emails.add(email)
        seen_ruts.add(cliente.rut)

    imported_count = 0
    if not errores:
        for _, cliente in clientes:
            create_cliente(db, cliente, user=user)
            imported_count += 1

    return {
        "totalFilas": total_rows,
        "importados": imported_count,
        "fallidos": len(errores),
        "errores": errores,
    }
