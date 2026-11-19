"""Rate limiter: cuenta con Redis y FALLA CERRADO si Redis no esta disponible.

Antes fallaba abierto (`except: return True`): con Redis caido el chat con LLM
de pago quedaba sin limite.
"""
import pytest
from fastapi import HTTPException

from app.api import rate_limiter


class FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    def execute(self):
        for op in self._ops:
            if op[0] == "incr":
                self._store[op[1]] = int(self._store.get(op[1], 0)) + 1


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}

    def get(self, key):
        return self.store.get(key)

    def pipeline(self):
        return FakePipeline(self.store)


class BrokenRedis:
    def get(self, key):
        raise ConnectionError("redis caido")

    def pipeline(self):
        raise ConnectionError("redis caido")


@pytest.fixture
def redis_ok(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limiter, "_redis", fake)
    return fake


class TestCounting:
    def test_first_request_is_allowed(self, redis_ok):
        assert rate_limiter.check_and_increment("u1") is True

    def test_requests_up_to_the_limit_are_allowed(self, redis_ok):
        assert all(rate_limiter.check_and_increment("u1", limit=3) for _ in range(3))

    def test_request_over_the_limit_is_blocked(self, redis_ok):
        for _ in range(3):
            rate_limiter.check_and_increment("u1", limit=3)
        assert rate_limiter.check_and_increment("u1", limit=3) is False

    def test_users_have_independent_counters(self, redis_ok):
        rate_limiter.check_and_increment("u1", limit=1)
        assert rate_limiter.check_and_increment("u1", limit=1) is False
        assert rate_limiter.check_and_increment("u2", limit=1) is True

    @pytest.mark.parametrize("window", ["minute", "hour", "day"])
    def test_all_windows_work(self, redis_ok, window):
        assert rate_limiter.check_and_increment("u1", limit=1, window=window) is True
        assert rate_limiter.check_and_increment("u1", limit=1, window=window) is False


class TestFailClosed:
    def test_without_redis_client_it_rejects_with_503(self, monkeypatch):
        monkeypatch.setattr(rate_limiter, "_redis", None)
        with pytest.raises(HTTPException) as exc:
            rate_limiter.check_and_increment("u1")
        assert exc.value.status_code == 503

    def test_redis_errors_reject_with_503_instead_of_allowing(self, monkeypatch):
        monkeypatch.setattr(rate_limiter, "_redis", BrokenRedis())
        with pytest.raises(HTTPException) as exc:
            rate_limiter.check_and_increment("u1")
        assert exc.value.status_code == 503

    def test_chat_endpoint_answers_503_when_limiter_is_down(self, client, user_headers, monkeypatch):
        monkeypatch.setattr(rate_limiter, "_redis", BrokenRedis())
        resp = client.post("/api/v1/chat/query", json={"question": "hola"}, headers=user_headers)
        assert resp.status_code == 503
