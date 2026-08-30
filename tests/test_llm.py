from hr_agent import llm
from hr_agent.config import Settings


def _settings(**env):
    base = {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "LLM_API_KEY": ""}
    base.update(env)
    return Settings(_env_file=None, **base)


def test_gemini_provider_resolves_gemini_key():
    s = _settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="g-key")
    assert s.provider == "gemini"
    assert s.resolved_llm_api_key == "g-key"
    assert s.resolved_llm_base_url is None


def test_groq_provider_resolves_groq_key_and_base_url():
    s = _settings(LLM_PROVIDER="groq", GROQ_API_KEY="q-key")
    assert s.resolved_llm_api_key == "q-key"
    assert s.resolved_llm_base_url == "https://api.groq.com/openai/v1"


def test_openai_compatible_uses_explicit_base_url():
    s = _settings(
        LLM_PROVIDER="openai_compatible",
        LLM_API_KEY="o-key",
        LLM_BASE_URL="https://openrouter.ai/api/v1",
    )
    assert s.resolved_llm_api_key == "o-key"
    assert s.resolved_llm_base_url == "https://openrouter.ai/api/v1"


def test_llm_available_reflects_configured_provider(monkeypatch):
    monkeypatch.setattr(llm, "settings", _settings(LLM_PROVIDER="groq"))
    assert llm.llm_available() is False
    monkeypatch.setattr(llm, "settings", _settings(LLM_PROVIDER="groq", GROQ_API_KEY="q"))
    assert llm.llm_available() is True


def test_missing_credentials_message_names_the_right_env_var(monkeypatch):
    monkeypatch.setattr(llm, "settings", _settings(LLM_PROVIDER="groq"))
    assert "GROQ_API_KEY" in llm.missing_credentials_message()
    monkeypatch.setattr(llm, "settings", _settings(LLM_PROVIDER="gemini"))
    assert "GEMINI_API_KEY" in llm.missing_credentials_message()
