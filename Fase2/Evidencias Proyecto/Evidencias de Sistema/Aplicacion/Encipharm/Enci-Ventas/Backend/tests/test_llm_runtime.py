import asyncio

from app.services import llm_runtime


def _run(monkeypatch, saved=None, error=None):
    class FakeIntel:
        async def get_llm_settings(self):
            if error:
                raise error
            return saved

    monkeypatch.setattr(llm_runtime, "EnciIntelService", FakeIntel)
    monkeypatch.setitem(llm_runtime._cache, "at", 0.0)
    return asyncio.run(llm_runtime.llm_overrides())


def test_saved_values_become_settings_overrides(monkeypatch):
    saved = {"api_key": "k", "base_url": "https://x.test", "model": "m", "competencia_model": "", "otro": "ignorado"}

    assert _run(monkeypatch, saved) == {"DEEPSEEK_API_KEY": "k", "DEEPSEEK_BASE_URL": "https://x.test", "DEEPSEEK_MODEL": "m"}


def test_intel_down_falls_back_to_environment(monkeypatch):
    assert _run(monkeypatch, error=RuntimeError("caido")) == {}


def test_result_is_cached(monkeypatch):
    _run(monkeypatch, {"model": "m"})
    monkeypatch.setattr(llm_runtime, "EnciIntelService", None)  # si se volviera a consultar, fallaria

    assert asyncio.run(llm_runtime.llm_overrides()) == {"DEEPSEEK_MODEL": "m"}


def test_anthropic_provider_and_key_are_passed_to_settings(monkeypatch):
    saved = {"proveedor": "anthropic", "anthropic_api_key": "sk-ant", "model": "claude-x"}

    assert _run(monkeypatch, saved) == {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant", "DEEPSEEK_MODEL": "claude-x"}
