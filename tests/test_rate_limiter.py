"""
Test unitario del _RateLimiter (app.py) con reloj falso.

Ventana deslizante en memoria, por clave (IP). No toca la app ni la DB.
"""
import pytest

import app as appmod
from app import _RateLimiter


def test_blocks_after_max_calls(monkeypatch):
    monkeypatch.setattr(appmod.time, "monotonic", lambda: 1000.0)
    rl = _RateLimiter(max_calls=2, period=60)
    assert rl.is_allowed("ip-a") is True
    assert rl.is_allowed("ip-a") is True
    assert rl.is_allowed("ip-a") is False     # tercera bloqueada


def test_keys_are_independent(monkeypatch):
    monkeypatch.setattr(appmod.time, "monotonic", lambda: 1000.0)
    rl = _RateLimiter(max_calls=1, period=60)
    assert rl.is_allowed("ip-a") is True
    assert rl.is_allowed("ip-a") is False
    assert rl.is_allowed("ip-b") is True       # otra IP no se ve afectada


def test_window_slides(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(appmod.time, "monotonic", lambda: clock["t"])
    rl = _RateLimiter(max_calls=1, period=60)
    assert rl.is_allowed("ip-a") is True
    assert rl.is_allowed("ip-a") is False
    clock["t"] = 61.0                          # pasó la ventana
    assert rl.is_allowed("ip-a") is True
