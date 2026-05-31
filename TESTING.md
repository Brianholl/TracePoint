# Testing

Suite de tests con `pytest`. **Regla de oro: el suite no toca la red real** —
toda llamada HTTP se mockea con `httpx.MockTransport` (ver `tests/_helpers.py`).

## Correr los tests

```bash
# en el venv del proyecto
pip install -r requirements-dev.txt
pytest                       # suite completa (rápida, sin red)
pytest -p no:warnings        # silenciando deprecaciones del código
```

## Cobertura

```bash
pytest --cov=app --cov=database --cov=modules --cov-report=term-missing
```

CI (`.github/workflows/tests.yml`) corre en Python 3.12 y 3.13 y exige un piso
de cobertura del **38%** (ratchet anti-regresión; la cobertura actual ronda el
40%). El objetivo sube a medida que
se cubren los módulos pendientes (`social_*`, `search_deepweb`, `google_dorker`,
`search_name`, `holehe_checker`, `breach_checker`, `url_tools`, `report_generator`).

## Mapa de tests

| Archivo | Cubre |
|---|---|
| `test_check_platform.py` | Clasificador de plataformas (11 tipos) — el núcleo. ~100% de `check_platform` |
| `test_search_username_fanout.py` | Agregación del fan-out `search_username` |
| `test_search_email.py` | HIBP (incl. `no_api_key`) + `risk_score` |
| `test_search_phone.py` | Validación `phonenumbers` |
| `test_social_twitter.py` | Parser de Nitter |
| `test_image_social_search.py` | Retornos tempranos (incl. URL local) |
| `test_ai_analyzer.py` | Degradación sin key + 200/401/timeout + `_build_prompt` |
| `test_orchestrator.py` | Pipeline `execute_search` / `execute_deep_search` |
| `test_rate_limiter.py` | `_RateLimiter` (ventana deslizante) |
| `test_routes.py` | Rutas ASGI: registro, login, rate limit 429, 404 |

## Cómo agregar un test que toca HTTP

`check_platform` y `_scrape_nitter_tweets` reciben el client por parámetro:
inyectales `static_client` / `redirect_client` de `tests/_helpers.py`. Si el
módulo crea su propio `httpx.AsyncClient`, reemplazalo con
`monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory(handler))`.
