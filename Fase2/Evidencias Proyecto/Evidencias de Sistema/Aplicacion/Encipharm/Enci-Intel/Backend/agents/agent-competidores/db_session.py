import os
import sys
from pathlib import Path

# Los agentes corren como procesos aparte (python main.py): se agrega Backend al path para reutilizar la capa Firestore.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.firestore_db import SyncDatabase  # noqa: E402


def get_db() -> SyncDatabase:
    if os.getenv("FIREBASE_CREDENTIALS_PATH"):
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", os.environ["FIREBASE_CREDENTIALS_PATH"])
    return SyncDatabase(os.getenv("FIREBASE_PROJECT_ID"))
