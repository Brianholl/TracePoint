"""
Tests de integración de modules/orchestrator.py.

Aísla la orquestación de la DB y de la red: monkeypatchea get_session,
update_search y todos los módulos de búsqueda con stubs. Verifica que el
pipeline arma search_data y cierra la búsqueda con el estado correcto.
"""
import pytest

import modules.orchestrator as orch


def aret(value):
    """Fabrica un coroutine-stub que ignora args y devuelve `value`."""
    async def _f(*args, **kwargs):
        return value
    return _f


@pytest.fixture
def captured(monkeypatch):
    """Neutraliza DB + report y captura los kwargs de cada update_search."""
    calls = []

    async def fake_get_session():
        yield "SESSION"

    async def fake_update(session, search_id, **kwargs):
        kwargs["search_id"] = search_id
        calls.append(kwargs)

    monkeypatch.setattr(orch, "get_session", fake_get_session)
    monkeypatch.setattr(orch, "update_search", fake_update)
    monkeypatch.setattr(orch, "get_all_configured", lambda: [])
    monkeypatch.setattr(orch, "generate_report", lambda data: "/reports/r.html")
    monkeypatch.setattr(orch, "analyze_results", aret("AI BRIEF"))
    return calls


async def test_username_search_completes(captured, monkeypatch):
    monkeypatch.setattr(orch, "search_username", aret(
        {"profiles": [{"platform": "GitHub", "status": "found", "url": "u"}],
         "total_found": 1, "total_unverified": 0}))
    monkeypatch.setattr(orch, "analyze_social_profiles", aret({}))        # falsy → no se agrega
    monkeypatch.setattr(orch, "search_deepweb", aret({"tor_connected": False}))

    await orch.execute_search(1, "username", "jdoe", None)

    assert len(captured) == 1
    rec = captured[0]
    assert rec["status"] == "completed"
    assert rec["search_id"] == 1
    assert rec["results"]["total_found"] == 1
    assert rec["ai_analysis"] == "AI BRIEF"
    assert rec["report_path"] == "/reports/r.html"


async def test_search_error_is_recorded(captured, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("scraper kaput")
    monkeypatch.setattr(orch, "search_username", boom)

    await orch.execute_search(2, "username", "jdoe", None)

    assert captured[0]["status"] == "error"
    assert "scraper kaput" in captured[0]["error"]


async def test_email_search_completes(captured, monkeypatch):
    monkeypatch.setattr(orch, "search_email", aret({"email": "a@b.com", "risk_score": 30}))
    monkeypatch.setattr(orch, "check_holehe", aret({}))                   # falsy → no se agrega

    await orch.execute_search(3, "email", "a@b.com", None)

    rec = captured[0]
    assert rec["status"] == "completed"
    assert rec["results"]["email"] == "a@b.com"


async def test_emits_progress_events(captured, monkeypatch):
    from modules.progress import broker
    broker.clear(42)
    monkeypatch.setattr(orch, "search_username", aret(
        {"profiles": [], "total_found": 3, "total_unverified": 0}))
    monkeypatch.setattr(orch, "analyze_social_profiles", aret({}))
    monkeypatch.setattr(orch, "search_deepweb", aret({"tor_connected": False}))

    await orch.execute_search(42, "username", "jdoe", None)

    hist = broker.history(42)
    nodes = [e["node"] for e in hist]
    assert "username" in nodes and "ai" in nodes
    assert hist[0] == {**hist[0], "node": "_pipeline", "status": "running"}
    assert broker.is_terminal(hist[-1]) and hist[-1]["status"] == "completed"
    # el evento 'done' de username arrastra el conteo
    uname_done = next(e for e in hist if e["node"] == "username" and e["status"] == "done")
    assert uname_done["found"] == 3
    broker.clear(42)


async def test_emits_error_event_on_failure(captured, monkeypatch):
    from modules.progress import broker
    broker.clear(43)

    async def boom(*a, **k):
        raise RuntimeError("falló")
    monkeypatch.setattr(orch, "search_username", boom)

    await orch.execute_search(43, "username", "jdoe", None)

    hist = broker.history(43)
    assert broker.is_terminal(hist[-1]) and hist[-1]["status"] == "error"
    broker.clear(43)


async def test_deep_search_completes(captured, monkeypatch):
    monkeypatch.setattr(orch, "search_username", aret(
        {"profiles": [], "total_found": 0, "total_unverified": 0}))
    monkeypatch.setattr(orch, "analyze_social_profiles", aret({}))
    monkeypatch.setattr(orch, "scrape_instagram", aret({"error": "x"}))   # error → no se agrega
    monkeypatch.setattr(orch, "scrape_twitter", aret({"profile": None}))  # sin profile → no se agrega
    monkeypatch.setattr(orch, "search_deepweb", aret({"tor_connected": False}))

    await orch.execute_deep_search(4, [("username", "jdoe")], None)

    rec = captured[0]
    assert rec["status"] == "completed"
    assert "username_jdoe" in rec["results"]
