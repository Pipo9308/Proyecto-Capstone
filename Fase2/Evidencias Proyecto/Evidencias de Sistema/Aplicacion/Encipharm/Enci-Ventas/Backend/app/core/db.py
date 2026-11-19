"""Acceso a datos de Ventas: Cloud Firestore a traves de app/core/odm.py (ver ahi sus diferencias con SQL)."""
from app.core.odm import Document as Base
from app.core.odm import Session, new_session

__all__ = ["Base", "Session", "SessionLocal", "get_db"]

# Cada llamada abre una sesion nueva (sirve como fabrica: `with SessionLocal() as db:`).
SessionLocal = new_session


def get_db():
    db = new_session()
    try:
        yield db
    finally:
        db.close()
