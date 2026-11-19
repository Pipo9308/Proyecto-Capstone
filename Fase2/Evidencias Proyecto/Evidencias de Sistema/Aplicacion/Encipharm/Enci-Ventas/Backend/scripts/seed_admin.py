import sys
import os
from datetime import datetime, timezone

# Add Backend root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal
from app.models_sql.user import User
from app.core.security import get_password_hash

def seed_admin():
    db = SessionLocal()
    email = "admin@enci.cl"
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        user = User(
            id="seed-user-admin",
            email=email,
            password_hash=get_password_hash(password),
            nombre="Administrador Enci",
            rol="admin",
            cargo="Administrador",
            rango="Admin",
            zona="Central",
            activo=True,
            webApp=True,
            appMovil=True,
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        print(f"Admin creado: {email}")
    else:
        user.rol = "admin"
        user.password_hash = get_password_hash(password)
        user.webApp = True
        user.appMovil = True
        db.commit()
        print(f"Admin actualizado: {email}")
        
    db.close()

if __name__ == "__main__":
    seed_admin()
