"""Los reintentos de embeddings estan acotados.

`index_file` tenia un `while True`: un error persistente colgaba la request (y
todo el backend, por correr en el event loop) para siempre.
"""
import pytest

from app.rag import engine


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(engine, "EMBED_RETRY_DELAY_S", 0)


def test_returns_embeddings_on_first_try(monkeypatch):
    monkeypatch.setattr(engine, "_embed", lambda texts: [[0.1, 0.2]] * len(texts))
    assert engine._embed_with_retries(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]


def test_recovers_after_a_transient_failure(monkeypatch):
    calls = {"n": 0}

    def flaky(texts):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("timeout transitorio")
        return [[1.0]] * len(texts)

    monkeypatch.setattr(engine, "_embed", flaky)
    assert engine._embed_with_retries(["a"]) == [[1.0]]
    assert calls["n"] == 2


def test_gives_up_after_bounded_retries(monkeypatch):
    calls = {"n": 0}

    def always_fails(texts):
        calls["n"] += 1
        raise RuntimeError("proveedor caido")

    monkeypatch.setattr(engine, "_embed", always_fails)
    with pytest.raises(RuntimeError, match="proveedor caido"):
        engine._embed_with_retries(["a"])
    assert calls["n"] == engine.EMBED_MAX_RETRIES
