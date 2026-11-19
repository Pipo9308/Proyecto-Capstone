"""PDF adjuntos de propuestas (RQ-07): limites, permisos, enlace de descarga firmado que vence."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.api import propuesta_archivos as attachments_api
from app.core.config import get_settings
from app.core.security import ALGORITHM, create_access_token, get_password_hash
from app.models_sql.comercial import Proposal
from app.models_sql.propuesta_archivo import PropuestaArchivo
from app.models_sql.user import User
from app.services import propuesta_archivos as service

PDF = b"%PDF-1.4\n" + b"contenido de la propuesta " * 50


@pytest.fixture
def blobs(monkeypatch):
    """Almacenamiento en memoria."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(service, "upload_blob_bytes", lambda path, content, content_type: store.__setitem__(path, content) or path)
    monkeypatch.setattr(service, "delete_document_blob", lambda path: store.pop(path, None))
    monkeypatch.setattr(attachments_api, "iter_blob_chunks", lambda path: iter([store[path][:20], store[path][20:]]))
    return store


def _add_user(db, uid, rol="vendedor"):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=True,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _headers(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner(db_session):
    return _add_user(db_session, "vend-1")


@pytest.fixture
def proposal(db_session, owner):
    row = Proposal(
        id="prop-1", clienteId="c-1", oportunidadId="o-1", titulo="Propuesta", montoNeto=1000.0, descuentoPct=0.0,
        estado="borrador", vendedorUid=owner.id,
    )
    db_session.add(row)
    db_session.commit()
    return row


def attach(client, user, name="propuesta.pdf", content=PDF, proposal_id="prop-1"):
    return client.post(f"/propuestas/{proposal_id}/archivos", files={"file": (name, content, "application/pdf")}, headers=_headers(user))


# ── Subir y listar ───────────────────────────────────────────────────────────

def test_owner_attaches_a_pdf_and_it_appears_in_the_list(client, blobs, owner, proposal):
    response = attach(client, owner)

    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "propuesta.pdf" and body["tamanoBytes"] == len(PDF) and body["subidoPor"] == owner.id
    listed = client.get("/propuestas/prop-1/archivos", headers=_headers(owner)).json()
    assert [a["id"] for a in listed] == [body["id"]] and listed[0]["subidoPorNombre"] == "Vend-1"
    assert list(blobs) == [f"propuestas/prop-1/{body['id']}.pdf"]


def test_only_pdfs_are_accepted(client, blobs, owner, proposal):
    assert attach(client, owner, "malo.pdf", b"no es un pdf").status_code == 422
    assert attach(client, owner, "hoja.xlsx", PDF).status_code == 422
    assert blobs == {}


def test_empty_files_are_rejected(client, blobs, owner, proposal):
    assert attach(client, owner, content=b"").status_code == 422


def test_the_size_limit_is_20_mb(client, blobs, owner, proposal, monkeypatch):
    assert get_settings().PROPUESTA_MAX_ARCHIVO_BYTES == 20 * 1024 * 1024
    monkeypatch.setattr(get_settings(), "PROPUESTA_MAX_ARCHIVO_BYTES", 1000)

    response = attach(client, owner, content=PDF + b"x" * 1000)

    assert response.status_code == 413


def test_a_proposal_admits_a_limited_number_of_files(client, blobs, owner, proposal, monkeypatch):
    monkeypatch.setattr(get_settings(), "PROPUESTA_MAX_ARCHIVOS", 2)
    assert attach(client, owner, "a.pdf").status_code == 201
    assert attach(client, owner, "b.pdf").status_code == 201

    blocked = attach(client, owner, "c.pdf")

    assert blocked.status_code == 409 and blocked.json()["codigo"] == "ERR_LIMITE_ADJUNTOS"
    assert len(blobs) == 2


def test_file_names_are_cleaned_and_never_decide_the_storage_path(client, blobs, owner, proposal):
    body = attach(client, owner, "../../etc/propuesta final.pdf").json()

    assert body["nombre"] == "propuesta final.pdf"
    assert all(path.startswith("propuestas/prop-1/") and ".." not in path for path in blobs)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("C:\\Users\\ana\\oferta.pdf", "oferta.pdf"),
        ("a/b/c.pdf", "c.pdf"),
        ("ofe\x00rta\x1f.pdf", "oferta.pdf"),
        ("", "adjunto.pdf"),
        ("x" * 300 + ".pdf", ("x" * 300 + ".pdf")[:200]),
    ],
)
def test_display_name(raw, expected):
    assert service._display_name(raw) == expected


def test_unknown_proposals_are_404(client, blobs, owner):
    assert attach(client, owner, proposal_id="no-existe").status_code == 404
    assert client.get("/propuestas/no-existe/archivos", headers=_headers(owner)).status_code == 404


# ── Permisos: dueño, supervisor y admin ──────────────────────────────────────

def test_another_seller_cannot_see_attach_download_or_delete(client, blobs, owner, proposal, db_session):
    intruso = _add_user(db_session, "vend-2")
    uploaded = attach(client, owner).json()
    base = "/propuestas/prop-1/archivos"

    assert attach(client, intruso).status_code == 403
    assert client.get(base, headers=_headers(intruso)).status_code == 403
    assert client.get(f"{base}/{uploaded['id']}/enlace", headers=_headers(intruso)).status_code == 403
    assert client.delete(f"{base}/{uploaded['id']}", headers=_headers(intruso)).status_code == 403
    assert len(blobs) == 1


@pytest.mark.parametrize("rol", ["supervisor", "admin"])
def test_supervisor_and_admin_can_manage_attachments(client, blobs, owner, proposal, db_session, rol):
    jefe = _add_user(db_session, f"jefe-{rol}", rol)
    uploaded = attach(client, owner).json()

    assert attach(client, jefe, "jefe.pdf").status_code == 201
    assert len(client.get("/propuestas/prop-1/archivos", headers=_headers(jefe)).json()) == 2
    assert client.get(f"/propuestas/prop-1/archivos/{uploaded['id']}/enlace", headers=_headers(jefe)).status_code == 200
    assert client.delete(f"/propuestas/prop-1/archivos/{uploaded['id']}", headers=_headers(jefe)).status_code == 204


def test_requires_login(client, blobs, proposal):
    assert client.post("/propuestas/prop-1/archivos", files={"file": ("a.pdf", PDF)}).status_code == 401
    assert client.get("/propuestas/prop-1/archivos").status_code == 401


# ── Descarga con enlace firmado ──────────────────────────────────────────────

def test_the_signed_link_downloads_the_file_without_a_session(client, blobs, owner, proposal):
    uploaded = attach(client, owner, "Propuesta Ñandú.pdf").json()
    link = client.get(f"/propuestas/prop-1/archivos/{uploaded['id']}/enlace", headers=_headers(owner)).json()

    response = client.get(link["url"])  # sin Authorization

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"] and "%C3%91and%C3%BA" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"


def test_the_link_expires(client, blobs, owner, proposal, db_session):
    uploaded = attach(client, owner).json()
    expired = jwt.encode(
        {"typ": "descarga_adjunto", "aid": uploaded["id"], "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        get_settings().JWT_SECRET, algorithm=ALGORITHM,
    )

    response = client.get("/propuestas/archivos/descarga", params={"token": expired})

    assert response.status_code == 410 and response.json()["codigo"] == "ERR_ENLACE_EXPIRADO"


def test_the_link_lasts_a_few_minutes(client, blobs, owner, proposal):
    uploaded = attach(client, owner).json()

    link = client.get(f"/propuestas/prop-1/archivos/{uploaded['id']}/enlace", headers=_headers(owner)).json()

    remaining = datetime.fromisoformat(link["expiraEn"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=9) < remaining <= timedelta(minutes=10)


def test_a_session_token_is_not_a_valid_download_link(client, blobs, owner, proposal):
    uploaded = attach(client, owner).json()
    session_token = create_access_token(data={"sub": owner.email, "uid": owner.id, "aid": uploaded["id"]})

    assert client.get("/propuestas/archivos/descarga", params={"token": session_token}).status_code == 403


def test_forged_or_garbage_links_are_rejected(client, blobs, owner, proposal):
    uploaded = attach(client, owner).json()
    forged = jwt.encode({"typ": "descarga_adjunto", "aid": uploaded["id"]}, "otro-secreto-que-no-es-el-real-123456", algorithm=ALGORITHM)

    assert client.get("/propuestas/archivos/descarga", params={"token": forged}).status_code == 403
    assert client.get("/propuestas/archivos/descarga", params={"token": "basura-que-no-es-un-jwt"}).status_code == 403
    assert client.get("/propuestas/archivos/descarga").status_code == 422


def test_a_link_for_a_deleted_file_is_404(client, blobs, owner, proposal):
    uploaded = attach(client, owner).json()
    link = client.get(f"/propuestas/prop-1/archivos/{uploaded['id']}/enlace", headers=_headers(owner)).json()
    client.delete(f"/propuestas/prop-1/archivos/{uploaded['id']}", headers=_headers(owner))

    assert client.get(link["url"]).status_code == 404


# ── Borrado ──────────────────────────────────────────────────────────────────

def test_deleting_removes_the_record_and_the_file(client, blobs, owner, proposal, db_session):
    uploaded = attach(client, owner).json()

    response = client.delete(f"/propuestas/prop-1/archivos/{uploaded['id']}", headers=_headers(owner))

    assert response.status_code == 204
    assert db_session.query(PropuestaArchivo).count() == 0 and blobs == {}
    assert client.delete(f"/propuestas/prop-1/archivos/{uploaded['id']}", headers=_headers(owner)).status_code == 404


def test_an_attachment_cannot_be_reached_through_another_proposal(client, blobs, owner, proposal, db_session):
    otra = Proposal(id="prop-2", clienteId="c-1", oportunidadId="o-1", titulo="Otra", montoNeto=1.0, descuentoPct=0.0, estado="borrador", vendedorUid=owner.id)
    db_session.add(otra)
    db_session.commit()
    uploaded = attach(client, owner).json()

    assert client.get(f"/propuestas/prop-2/archivos/{uploaded['id']}/enlace", headers=_headers(owner)).status_code == 404
    assert client.delete(f"/propuestas/prop-2/archivos/{uploaded['id']}", headers=_headers(owner)).status_code == 404


def test_the_request_size_middleware_allows_pdfs_up_to_the_limit():
    from app.core.rate_limit import RequestSizeLimitMiddleware

    middleware = RequestSizeLimitMiddleware(None, max_body_bytes=1_000_000, path_limits={"/propuestas/*/archivos": 21_000_000})

    assert middleware._limit_for("/propuestas/abc-123/archivos") == 21_000_000
    assert middleware._limit_for("/propuestas") == 1_000_000
    assert middleware._limit_for("/otra/ruta") == 1_000_000
