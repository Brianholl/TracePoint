"""
Tests de modules/image_social_search.py.

Foco: los retornos tempranos que son contrato crítico (incluido el fix P1 de
URLs locales). No requieren red: el módulo decide antes de hacer requests.
"""
import pytest

from modules.image_social_search import search_social_by_image


async def test_no_image_returns_error():
    result = await search_social_by_image()
    assert result["error"] == "No image provided"
    assert result["found_profiles"] == []


async def test_local_url_is_unavailable():
    # Las URLs locales (/uploads/...) no son alcanzables por motores externos.
    result = await search_social_by_image(image_url="/uploads/foto.jpg")
    assert result["error"] == "reverse_image_unavailable_local"
    assert result["found_profiles"] == []
