"""Metas mensuales: el supervisor las fija; el vendedor solo ve la suya."""
from datetime import datetime, timezone

from app.core.security import create_access_token, get_password_hash
from app.models_sql.user import User


def _add_user(db, uid, rol):
    now = datetime.now(timezone.utc)
    user = User(id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=True,
                password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now)
    db.add(user)
    db.commit()
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


def test_supervisor_fija_meta_y_cada_vendedor_ve_la_suya(client, db_session):
    sup = _add_user(db_session, "sup", "supervisor")
    ana = _add_user(db_session, "ana", "vendedor")
    _add_user(db_session, "beto", "vendedor")

    for uid, monto in (("ana", 10_000_000), ("beto", 5_000_000)):
        r = client.put("/metas", json={"vendedorUid": uid, "mes": "2026-11", "monto": monto}, headers=sup)
        assert r.status_code == 200
    client.put("/metas", json={"vendedorUid": "ana", "mes": "2026-11", "monto": 12_000_000}, headers=sup)

    assert {m["vendedorUid"]: m["monto"] for m in client.get("/metas?mes=2026-11", headers=sup).json()} == {
        "ana": 12_000_000, "beto": 5_000_000}
    assert [m["vendedorUid"] for m in client.get("/metas?mes=2026-11", headers=ana).json()] == ["ana"]
    assert client.get("/metas?mes=2026-10", headers=sup).json() == []


def test_vendedor_no_puede_fijar_metas_ni_mes_invalido(client, db_session):
    sup = _add_user(db_session, "sup", "supervisor")
    ana = _add_user(db_session, "ana", "vendedor")
    body = {"vendedorUid": "ana", "mes": "2026-11", "monto": 1}
    assert client.put("/metas", json=body, headers=ana).status_code == 403
    assert client.put("/metas", json={**body, "mes": "2026-13"}, headers=sup).status_code == 422
    assert client.put("/metas", json={**body, "monto": -5}, headers=sup).status_code == 422
    assert client.put("/metas", json={**body, "vendedorUid": "nadie"}, headers=sup).status_code == 404
