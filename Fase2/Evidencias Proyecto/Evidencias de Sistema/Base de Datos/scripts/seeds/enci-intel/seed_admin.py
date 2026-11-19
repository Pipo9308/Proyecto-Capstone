"""Crea (o actualiza) el usuario admin de Enci-Intel.

POST /auth/register ya no permite elegir rol (todo self-registro nace
"pendiente"), asi que el primer admin se crea con este script.

    ADMIN_EMAIL=admin@encintel.cl ADMIN_PASSWORD=... python scripts/seed_admin.py
o dentro del contenedor:
    docker exec -e ADMIN_PASSWORD=... enci_backend python scripts/seed_admin.py
"""

import asyncio
import os
import sys

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.firestore_db import create_async_database  # noqa: E402


async def main():
    email = os.environ.get("ADMIN_EMAIL", "admin@encintel.cl")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        sys.exit("Falta ADMIN_PASSWORD")

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db = create_async_database(os.environ.get("FIREBASE_PROJECT_ID"))
    try:
        result = await db.users.update_one(
            {"email": email},
            {"$set": {"hashed_password": hashed, "rol": "admin", "estado": "activo"}},
            upsert=True,
        )
        print(f"Admin {'creado' if result.upserted_id else 'actualizado'}: {email}")
    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
