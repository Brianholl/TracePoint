"""
Tests de modules/search_phone.py.

phonenumbers es determinista y offline → ideal para tests. La parte de red
(scraping de Google sobre números válidos) se mockea.
"""
import httpx
import phonenumbers
import pytest

import modules.search_phone as sp
from tests._helpers import mock_client_factory, static_client  # noqa: F401


async def test_invalid_format_sets_error():
    result = await sp.search_phone("no-soy-un-telefono")
    assert result["valid"] is False
    assert result["error"] == "Invalid phone number format"


async def test_parseable_but_invalid_number_stays_invalid():
    # Parsea como país +1 pero no es un número válido → sin red, sin 'error'
    result = await sp.search_phone("+1234")
    assert result["valid"] is False


async def test_valid_number_is_classified(monkeypatch):
    # Número de ejemplo válido garantizado por la librería
    example = phonenumbers.example_number("US")
    e164 = phonenumbers.format_number(example, phonenumbers.PhoneNumberFormat.E164)

    # La búsqueda en Google se mockea con una respuesta vacía
    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(
        lambda req: httpx.Response(200, text="<html></html>")
    ))

    result = await sp.search_phone(e164)
    assert result["valid"] is True
    assert result["formatted"].startswith("+1")
    assert result["country"]
    assert result["web_results"] == []
