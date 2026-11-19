"""El asistente RAG solo habla de animales y del negocio: nunca da medicina para personas."""
from datetime import datetime, timezone

import pytest

from app.api import rag as rag_api
from app.core.security import create_access_token, get_password_hash
from app.models_sql.user import User
from app.services import llm_service, solo_animales as sa


@pytest.mark.parametrize("pregunta, bloqueada", [
    ("¿Qué dosis de ivermectina para mi hijo?", True),
    ("dame la dosis para una persona de 70 kg", True),
    ("Me inyecté la ivermectina del perro, ¿qué hago?", True),
    ("¿Qué dosis de ivermectina para un bovino de 400 kg?", False),
    ("dosis para el perro de mi hijo", False),
    ("¿Cuántas oportunidades abiertas tiene el vendedor?", False),
])
def test_input_filter(pregunta, bloqueada):
    assert sa.consulta_humana(pregunta) is bloqueada


def test_output_filter_allows_operator_warnings_only():
    assert sa.respuesta_humana("La dosis en humanos es de 0,2 mg/kg.") is True
    assert sa.respuesta_humana("Advertencia: no usar en personas.") is False


def test_prompt_forbids_human_medicine():
    assert "NUNCA des informacion medica" in llm_service.build_system_prompt()


@pytest.fixture
def vendedor(db_session):
    now = datetime.now(timezone.utc)
    user = User(id="v-1", email="v-1@test.cl", nombre="V", rol="vendedor", activo=True,
                password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True, createdAt=now, updatedAt=now)
    db_session.add(user)
    db_session.commit()
    return {"Authorization": "Bearer " + create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol}),
            "X-Enci-Client": "mobile"}


def _chat(client, headers, pregunta):
    return client.post("/rag/chat", json={"pregunta": pregunta}, headers=headers)


def test_human_question_gets_the_fixed_phrase_without_model_or_search(client, vendedor, monkeypatch):
    def no_debe_llamarse(*a, **k):
        pytest.fail("no debe buscar ni llamar al modelo")

    monkeypatch.setattr(rag_api, "call_deepseek", no_debe_llamarse)
    monkeypatch.setattr(rag_api, "search_similar_chunks", no_debe_llamarse)

    response = _chat(client, vendedor, "¿Qué dosis de ivermectina para mi hijo?")

    assert response.status_code == 200
    assert response.json()["respuesta"] == sa.FRASE_FIJA and response.json()["fuentes"] == []


def test_human_medicine_in_the_model_answer_is_replaced(client, vendedor, monkeypatch):
    chunk = {"documento": "ficha.pdf", "pagina": 1, "texto": "Ivermectina en bovinos.", "fragmento": "Ivermectina en bovinos."}
    monkeypatch.setattr(rag_api, "search_similar_chunks", lambda *a, **k: [chunk])

    async def modelo(*a, **k):
        return {"texto": "La dosis en humanos es de 0,2 mg/kg.", "tokens": 5, "modelo": "m"}

    monkeypatch.setattr(rag_api, "call_deepseek", modelo)

    response = _chat(client, vendedor, "¿Cómo actúa la ivermectina?")

    assert response.json()["respuesta"] == sa.FRASE_FIJA and response.json()["fuentes"] == []
