"""
Tests de modules/search_email.py.

Foco: el clasificador HIBP (incluido el path no_api_key del fix P1) y la
lógica de risk_score. La red se mockea reemplazando httpx.AsyncClient.
"""
import httpx
import pytest

from config import config
import modules.search_email as se
from tests._helpers import mock_client_factory, json_handler, raising_client  # noqa: F401


# ─── check_hibp ─────────────────────────────────────────────────────────────

async def test_hibp_without_api_key_returns_no_api_key(monkeypatch):
    monkeypatch.setattr(config, "HIBP_API_KEY", "")
    result = await se.check_hibp("a@b.com")
    assert result["status"] == "no_api_key"
    assert result["total_breaches"] == 0


async def test_hibp_with_breaches(monkeypatch):
    monkeypatch.setattr(config, "HIBP_API_KEY", "KEY")
    payload = [
        {"Name": "Adobe", "Domain": "adobe.com", "BreachDate": "2013-10-04",
         "DataClasses": ["Emails", "Passwords"]},
        {"Name": "LinkedIn", "Domain": "linkedin.com", "BreachDate": "2012-05-05",
         "DataClasses": ["Emails"]},
    ]
    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(json_handler(200, payload)))
    result = await se.check_hibp("a@b.com")
    assert result["total_breaches"] == 2
    assert result["breaches"][0]["name"] == "Adobe"
    assert "status" not in result


async def test_hibp_404_means_clean(monkeypatch):
    monkeypatch.setattr(config, "HIBP_API_KEY", "KEY")
    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(json_handler(404, {})))
    result = await se.check_hibp("a@b.com")
    assert result["total_breaches"] == 0
    assert "status" not in result


async def test_hibp_401_invalid_key(monkeypatch):
    monkeypatch.setattr(config, "HIBP_API_KEY", "BAD")
    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(json_handler(401, {})))
    result = await se.check_hibp("a@b.com")
    assert result["status"] == "invalid_api_key"


# ─── search_email: lógica de risk_score (helpers mockeados) ─────────────────

async def test_risk_score_aggregation(monkeypatch):
    async def fake_gravatar(email):
        return {"display_name": "John"}

    async def fake_hibp(email):
        return {"breaches": [], "total_breaches": 2}

    async def fake_dork(email):
        return [{"title": "a", "url": "x"}, {"title": "b", "url": "y"}]

    monkeypatch.setattr(se, "check_gravatar", fake_gravatar)
    monkeypatch.setattr(se, "check_hibp", fake_hibp)
    monkeypatch.setattr(se, "google_dork_email", fake_dork)

    result = await se.search_email("a@b.com")
    # 2 breaches*15=30 (cap 60) + gravatar 10 + 2 mentions*5=10 (cap 30) = 50
    assert result["risk_score"] == 50
    assert result["gravatar"]["display_name"] == "John"
    assert len(result["web_mentions"]) == 2


async def test_risk_score_zero_when_nothing_found(monkeypatch):
    async def none_gravatar(email):
        return None

    async def empty_hibp(email):
        return {"breaches": [], "total_breaches": 0}

    async def empty_dork(email):
        return []

    monkeypatch.setattr(se, "check_gravatar", none_gravatar)
    monkeypatch.setattr(se, "check_hibp", empty_hibp)
    monkeypatch.setattr(se, "google_dork_email", empty_dork)

    result = await se.search_email("a@b.com")
    assert result["risk_score"] == 0
    assert result["gravatar"] is None
