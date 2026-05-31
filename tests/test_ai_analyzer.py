"""
Tests de modules/ai_analyzer.py.

Foco: degradación elegante sin API key y manejo de respuestas de OpenRouter
(200 / 401 / timeout). La llamada HTTP se mockea reemplazando httpx.AsyncClient.
"""
import httpx
import pytest

from config import config
import modules.ai_analyzer as ai
from tests._helpers import mock_client_factory, json_handler, raising_client

SEARCH_DATA = {
    "query_type": "username",
    "query_value": "jdoe",
    "results": {"profiles": []},
}


async def test_no_api_key_returns_unavailable(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    result = await ai.analyze_results(SEARCH_DATA)
    assert "unavailable" in result.lower()


async def test_successful_analysis(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "KEY")
    payload = {"choices": [{"message": {"content": "PERFIL OSINT GENERADO"}}]}
    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(json_handler(200, payload)))
    result = await ai.analyze_results(SEARCH_DATA)
    assert "PERFIL OSINT GENERADO" in result
    # El prefijo identifica el modelo de texto por defecto
    assert "DeepSeek" in result


async def test_invalid_key_message(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "BAD")
    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(json_handler(401, {})))
    result = await ai.analyze_results(SEARCH_DATA)
    assert "Invalid API key" in result


async def test_timeout_message(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "KEY")

    def boom(request):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(boom))
    result = await ai.analyze_results(SEARCH_DATA)
    assert "timed out" in result.lower()


# ─── _build_prompt: contrato del prompt OSINT (función pura) ────────────────

def test_build_prompt_username_section():
    data = {
        "query_type": "username",
        "query_value": "jdoe",
        "results": {
            "profiles": [
                {"platform": "GitHub", "url": "https://github.com/jdoe", "status": "found"},
                {"platform": "Reddit", "url": "https://reddit.com/u/jdoe", "status": "not_found"},
            ],
        },
    }
    prompt = ai._build_prompt(data)
    assert "Username Search Results" in prompt
    assert "Profiles found: 1" in prompt          # solo el 'found' cuenta
    assert "GitHub: https://github.com/jdoe" in prompt
    assert "Resumen ejecutivo" in prompt           # bloque de instrucciones presente
    # anti-tokenmaxxing: la regla de no inflar viaja en el prompt
    assert "Nunca infles para completar" in prompt


def test_build_prompt_email_section_with_breaches():
    data = {
        "query_type": "email",
        "query_value": "a@b.com",
        "results": {
            "email": "a@b.com",
            "risk_score": 45,
            "hibp": {"total_breaches": 1, "breaches": [
                {"name": "Adobe", "date": "2013-10-04", "data_classes": ["Emails"]}]},
            "web_mentions": [],
        },
    }
    prompt = ai._build_prompt(data)
    assert "Email Search Results" in prompt
    assert "Risk Score: 45/100" in prompt
    assert "Adobe" in prompt


def test_build_prompt_phone_section():
    data = {
        "query_type": "phone",
        "query_value": "+14155550100",
        "results": {"phone": "+14155550100", "valid": True, "country": "United States",
                    "carrier": "", "location": "California", "timezones": ["America/Los_Angeles"]},
    }
    prompt = ai._build_prompt(data)
    assert "Phone Search Results" in prompt
    assert "Valid: True" in prompt
    assert "America/Los_Angeles" in prompt
