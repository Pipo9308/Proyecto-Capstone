import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from app.models_sql.rag import RagConversation
from app.models_sql.user import User
from app.services.rag_service import list_conversations, save_conversation_turn

def test_list_conversations_returns_only_authenticated_account(db_session):
    u1 = User(id="user-1", email="u1@enci.cl", nombre="U1", rol="admin", activo=True)
    u2 = User(id="user-2", email="u2@enci.cl", nombre="U2", rol="admin", activo=True)
    db_session.add(u1)
    db_session.add(u2)
    db_session.commit()

    c1 = RagConversation(id="own-old", usuarioId="user-1", rol="admin", updatedAt=datetime(2026, 1, 1, tzinfo=timezone.utc))
    c2 = RagConversation(id="other", usuarioId="user-2", rol="admin", updatedAt=datetime(2026, 3, 1, tzinfo=timezone.utc))
    c3 = RagConversation(id="own-new", usuarioId="user-1", rol="admin", updatedAt=datetime(2026, 2, 1, tzinfo=timezone.utc))
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    result = list_conversations(db_session, {"uid": "user-1", "rol": "admin"})
    assert [conversation["id"] for conversation in result] == ["own-new", "own-old"]

def test_save_conversation_rejects_another_account_for_any_role(db_session):
    u2 = User(id="user-2", email="u2@enci.cl", nombre="U2", rol="admin", activo=True)
    db_session.add(u2)
    db_session.commit()

    c = RagConversation(id="conversation-1", usuarioId="user-2", rol="admin", mensajes=[], createdAt=datetime.now(timezone.utc))
    db_session.add(c)
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        save_conversation_turn(
            db_session,
            {"uid": "user-1", "rol": "admin"},
            "Pregunta",
            "Respuesta",
            [],
            0,
            False,
            {"origen": "local"},
            "conversation-1",
        )
    assert error.value.status_code == 403

def test_save_new_conversation_persists_generated_title(db_session):
    u1 = User(id="user-1", email="user@enci.cl", nombre="U1", rol="vendedor", activo=True)
    db_session.add(u1)
    db_session.commit()

    save_conversation_turn(
        db_session,
        {"uid": "user-1", "rol": "vendedor", "email": "user@enci.cl"},
        "Que reglas existen para productos?",
        "Respuesta",
        [],
        10,
        False,
        {"origen": "deepseek"},
        "conversation-1",
        "Ingreso sanitario de productos",
    )

    c = db_session.query(RagConversation).filter(RagConversation.id == "conversation-1").first()
    assert c.titulo == "Ingreso sanitario de productos"
