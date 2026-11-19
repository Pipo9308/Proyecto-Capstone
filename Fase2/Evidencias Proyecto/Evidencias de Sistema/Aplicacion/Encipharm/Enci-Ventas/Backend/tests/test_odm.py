"""Capa de datos (app/core/odm.py) sobre el emulador de Firestore: consultas, unicidad, cambios y semantica SQL."""
import uuid
from datetime import date, datetime, timezone

import pytest

from app.core.db import Base
from app.core.odm import (
    JSON, Boolean, Column, Date, DateTime, Integer, IntegrityError, MultipleResultsFound, NoResultFound, String, Unique,
    func, or_,
)


def _now():
    return datetime.now(timezone.utc)


class Thing(Base):
    __tablename__ = "odm_things"
    __unique__ = (Unique("code", where=lambda d: d.get("active") is True),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(80), nullable=False)
    code = Column(String(20), nullable=True)
    email = Column(String(80), unique=True)
    n = Column(Integer, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    day = Column(Date, nullable=True)
    at = Column(DateTime, nullable=True)
    meta = Column(JSON, nullable=True)
    updatedAt = Column(DateTime, default=_now, onupdate=_now, nullable=False)


def add(db, **kw):
    kw.setdefault("name", "x")
    thing = Thing(**kw)
    db.add(thing)
    db.commit()
    return thing


# ── Guardar y leer ───────────────────────────────────────────────────────────

def test_guardar_y_leer_respeta_tipos(db_session):
    when = datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)
    thing = add(db_session, name="a", day=date(2026, 10, 5), at=when, meta={"k": [1, 2]}, n=3)

    db_session.close()
    loaded = db_session.query(Thing).filter(Thing.id == thing.id).one()

    assert loaded.day == date(2026, 10, 5) and isinstance(loaded.day, date)
    assert loaded.at == datetime(2026, 10, 1, 12, 30) and loaded.at.tzinfo is None  # ingenuo en UTC
    assert loaded.meta == {"k": [1, 2]} and loaded.n == 3 and loaded.active is True


def test_un_campo_obligatorio_nulo_falla(db_session):
    db_session.add(Thing(name=None))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_solo_se_escriben_los_campos_modificados_y_onupdate_los_refresca(db_session):
    thing = add(db_session, name="a", n=1)
    before = thing.updatedAt

    thing.n = 2
    db_session.commit()
    db_session.close()
    loaded = db_session.query(Thing).filter(Thing.id == thing.id).one()

    assert loaded.n == 2 and loaded.name == "a" and loaded.updatedAt > before


def test_refresh_trae_lo_que_otro_escribio(db_session):
    thing = add(db_session, name="a")
    from app.core.odm import new_session
    other = new_session()
    other.query(Thing).filter(Thing.id == thing.id).one().name = "cambiado"
    other.commit()

    db_session.refresh(thing)

    assert thing.name == "cambiado"


def test_rollback_descarta_lo_pendiente(db_session):
    thing = add(db_session, name="a")
    thing.name = "b"
    db_session.add(Thing(name="nuevo"))

    db_session.rollback()
    db_session.commit()
    db_session.close()

    assert [t.name for t in db_session.query(Thing).all()] == ["a"]


# ── Unicidad ─────────────────────────────────────────────────────────────────

def test_unique_en_columna_y_null_no_choca(db_session):
    add(db_session, email="a@x.cl")
    add(db_session, email=None)
    add(db_session, email=None)  # NULL no choca con NULL

    db_session.add(Thing(name="dup", email="a@x.cl"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_unique_parcial_solo_cuenta_los_que_cumplen_la_condicion(db_session):
    first = add(db_session, code="K1", active=True)
    add(db_session, code="K1", active=False)  # inactivo: no cuenta

    db_session.add(Thing(name="otro", code="K1", active=True))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    first.active = False  # al darse de baja libera el valor
    db_session.commit()
    add(db_session, code="K1", active=True)


def test_cambiar_un_valor_unico_libera_el_anterior_y_borrar_tambien(db_session):
    thing = add(db_session, email="a@x.cl")

    thing.email = "b@x.cl"
    db_session.commit()
    add(db_session, email="a@x.cl")  # el viejo quedo libre
    db_session.delete(thing)
    db_session.commit()
    add(db_session, email="b@x.cl")  # borrar libera


def test_dos_sesiones_no_pueden_crear_el_mismo_valor_unico(db_session):
    from app.core.odm import new_session
    one, two = new_session(), new_session()
    one.add(Thing(name="uno", email="same@x.cl"))
    two.add(Thing(name="dos", email="same@x.cl"))

    one.commit()
    with pytest.raises(IntegrityError):
        two.commit()


# ── Consultas ────────────────────────────────────────────────────────────────

def test_filtros_basicos_y_semantica_null(db_session):
    add(db_session, name="a", n=1)
    add(db_session, name="b", n=2)
    add(db_session, name="c", n=None)

    names = lambda q: sorted(t.name for t in q)  # noqa: E731
    q = db_session.query(Thing)
    assert names(q.filter(Thing.n == 2)) == ["b"]
    assert names(db_session.query(Thing).filter(Thing.n != 2)) == ["a"]  # NULL != 2 no coincide (como SQL)
    assert names(db_session.query(Thing).filter(Thing.n.is_(None))) == ["c"]
    assert names(db_session.query(Thing).filter(Thing.n >= 1, Thing.n < 2)) == ["a"]
    assert names(db_session.query(Thing).filter(or_(Thing.n == 1, Thing.name == "c"))) == ["a", "c"]
    assert db_session.query(Thing).filter(Thing.n.in_([1, 2])).count() == 2


def test_in_con_mas_de_30_valores(db_session):
    for i in range(35):
        add(db_session, name=f"n{i}", n=i)

    assert db_session.query(Thing).filter(Thing.n.in_(list(range(35)))).count() == 35


def test_ilike_con_comodines_y_escape(db_session):
    add(db_session, name="Zoetis Chile")
    add(db_session, name="Agrovet 100%")
    add(db_session, name="Agrovet 100x")

    def found(pattern, **kw):
        return sorted(t.name for t in db_session.query(Thing).filter(Thing.name.ilike(pattern, **kw)))

    assert found("%ZOET%") == ["Zoetis Chile"]
    assert found("agrovet 100%", ) == ["Agrovet 100%", "Agrovet 100x"]
    assert found("%100\\%%", escape="\\") == ["Agrovet 100%"]  # el % escapado es literal
    assert found("zoetis_chile") == ["Zoetis Chile"]  # _ = un caracter


def test_func_lower_igual(db_session):
    add(db_session, name="Zoetis")

    assert db_session.query(Thing).filter(func.lower(Thing.name) == "zoetis").count() == 1
    assert db_session.query(Thing).filter(func.lower(Thing.name) == "otro").count() == 0


def test_order_by_limit_offset_y_nulos(db_session):
    for name, n in (("a", 3), ("b", None), ("c", 1), ("d", 2)):
        add(db_session, name=name, n=n)

    assert [t.name for t in db_session.query(Thing).order_by(Thing.n.asc())] == ["b", "c", "d", "a"]  # NULL primero
    assert [t.name for t in db_session.query(Thing).order_by(Thing.n.desc(), Thing.name)] == ["a", "d", "c", "b"]
    assert [t.name for t in db_session.query(Thing).order_by(Thing.name).offset(1).limit(2)] == ["b", "c"]


def test_filtro_por_fecha_date_y_datetime(db_session):
    add(db_session, name="a", day=date(2026, 10, 1), at=datetime(2026, 10, 1, 8))
    add(db_session, name="b", day=date(2026, 10, 10), at=datetime(2026, 10, 10, 8))

    assert [t.name for t in db_session.query(Thing).filter(Thing.day >= date(2026, 10, 5))] == ["b"]
    cutoff = datetime(2026, 10, 5, tzinfo=timezone.utc)  # con zona, contra datos ingenuos
    assert [t.name for t in db_session.query(Thing).filter(Thing.at < cutoff)] == ["a"]


def test_first_one_one_or_none(db_session):
    add(db_session, name="a")
    add(db_session, name="a")

    assert db_session.query(Thing).filter(Thing.name == "zzz").first() is None
    with pytest.raises(NoResultFound):
        db_session.query(Thing).filter(Thing.name == "zzz").one()
    with pytest.raises(MultipleResultsFound):
        db_session.query(Thing).filter(Thing.name == "a").one()
    assert db_session.query(Thing).filter(Thing.name == "zzz").one_or_none() is None


def test_consulta_de_columnas_devuelve_filas(db_session):
    thing = add(db_session, name="a", n=7)

    row = db_session.query(Thing.id, Thing.n).filter(Thing.id == thing.id).first()

    assert row.id == thing.id and row.n == 7 and row[1] == 7
    assert [tuple(r) for r in db_session.query(Thing.id).all()] == [(thing.id,)]


def test_delete_y_update_masivos(db_session):
    for i in range(5):
        add(db_session, name=f"n{i}", n=i)

    assert db_session.query(Thing).filter(Thing.n < 2).update({"active": False}) == 2
    assert db_session.query(Thing).filter(Thing.active.is_(False)).count() == 2
    assert db_session.query(Thing).filter(Thing.n >= 3).delete() == 2
    assert db_session.query(Thing).count() == 3


def test_mas_de_450_escrituras_en_un_commit(db_session):
    db_session.add_all(Thing(name=f"n{i}") for i in range(520))
    db_session.commit()

    assert db_session.query(Thing).count() == 520


def test_los_objetos_se_reutilizan_dentro_de_la_sesion(db_session):
    thing = add(db_session, name="a")

    assert db_session.query(Thing).filter(Thing.id == thing.id).first() is thing
    assert db_session.get(Thing, thing.id) is thing
