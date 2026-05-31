"""
Test de agregación de search_username (modules/search_usernames.py:206-231).

Cubre el fan-out: monkeypatchea check_platform con un stub determinista (sin
red) y verifica el conteo, el filtrado de None, la captura de excepciones y el
orden alfabético de los perfiles.
"""
import pytest

import modules.search_usernames as su
from modules.search_usernames import PLATFORMS, search_username

_RAISES = "Steam"   # type 'text'  → debe ir a errors
_NONE = "Flickr"    # type '404'   → debe excluirse de profiles


async def fake_check(client, username, platform):
    name = platform["name"]
    if name == _RAISES:
        raise RuntimeError("boom")
    if name == _NONE:
        return None
    status = "found" if platform.get("type") == "404" else "unverified"
    return {"platform": name, "url": "https://x/" + name, "status": status}


async def test_fanout_aggregation(monkeypatch):
    monkeypatch.setattr(su, "check_platform", fake_check)
    result = await search_username("jdoe")

    expected_found = sum(
        1 for p in PLATFORMS if p.get("type") == "404" and p["name"] not in (_RAISES, _NONE)
    )
    expected_unverified = sum(
        1 for p in PLATFORMS if p.get("type") != "404" and p["name"] != _RAISES
    )

    assert result["total_found"] == expected_found
    assert result["total_unverified"] == expected_unverified
    assert len(result["errors"]) == 1

    names = [p["platform"] for p in result["profiles"]]
    assert _NONE not in names                      # None se descarta
    assert _RAISES not in names                    # la excepción no entra a profiles
    assert names == sorted(names, key=str.lower)   # orden alfabético estable
