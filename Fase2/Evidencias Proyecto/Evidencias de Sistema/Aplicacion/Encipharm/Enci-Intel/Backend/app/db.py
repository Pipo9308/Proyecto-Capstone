import os

from app.firestore_db import create_async_database

# Con FIRESTORE_EMULATOR_HOST el cliente apunta al emulador local y no pide credenciales.
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID")
FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH")
if not FIREBASE_PROJECT_ID:
    raise RuntimeError("FIREBASE_PROJECT_ID no definido (ver .env.example).")


class Database:
    db = None


db = Database()


def connect_to_db():
    if FIREBASE_CREDENTIALS_PATH:
        # Credenciales de la cuenta de servicio: se toman de este archivo (ver .env.example).
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", FIREBASE_CREDENTIALS_PATH)
    db.db = create_async_database(FIREBASE_PROJECT_ID)


def close_db_connection():
    # El cliente de Firestore no mantiene recursos que haya que cerrar a mano al apagar el proceso.
    db.db = None


def get_db():
    return db.db
