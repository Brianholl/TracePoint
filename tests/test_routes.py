"""
Tests de integración de rutas (app.py) vía httpx.ASGITransport.

Usa una DB SQLite temporal (parcheando database.engine/async_session) y
neutraliza las tareas de fondo (execute_search) para no tocar la red.
"""
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import database


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    sm = async_sessionmaker(eng, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "async_session", sm)
    async with eng.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)

    import app as appmod

    async def noop(*args, **kwargs):
        return None

    # las rutas crean asyncio.create_task(execute_*); las dejamos inertes
    monkeypatch.setattr(appmod, "execute_search", noop)
    monkeypatch.setattr(appmod, "execute_deep_search", noop)
    appmod._search_limiter._calls.clear()
    appmod._deep_search_limiter._calls.clear()

    transport = httpx.ASGITransport(app=appmod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        yield ac
    await eng.dispose()


async def test_register_page_renders_for_first_user(client):
    resp = await client.get("/auth/register")
    assert resp.status_code == 200


async def test_register_creates_user_and_redirects(client):
    resp = await client.post("/auth/register", data={
        "dni": "12345678", "display_name": "John Doe", "password": "secret123",
    })
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/2fa/setup"
    assert "session" in resp.cookies


async def test_login_wrong_password_rejected(client):
    await client.post("/auth/register", data={
        "dni": "999", "display_name": "X", "password": "good-pass",
    })
    resp = await client.post("/auth/login", data={"dni": "999", "password": "wrong"})
    assert resp.status_code == 200          # re-renderiza login con error, no redirige


async def test_login_correct_redirects_home(client):
    await client.post("/auth/register", data={
        "dni": "777", "display_name": "Y", "password": "right-pass",
    })
    resp = await client.post("/auth/login", data={"dni": "777", "password": "right-pass"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


async def test_search_is_rate_limited(client):
    payload = {"query_type": "username", "query_value": "jdoe", "visibility": "public"}
    for _ in range(10):                     # _search_limiter = 10/min
        ok = await client.post("/search/run", data=payload)
        assert ok.status_code == 303
    blocked = await client.post("/search/run", data=payload)
    assert blocked.status_code == 429


async def test_missing_result_is_404(client):
    resp = await client.get("/results/999999")
    assert resp.status_code == 404


async def test_sse_replays_history_and_closes_on_terminal(client):
    # El endpoint SSE es un GET streaming → testeable con el mismo ASGITransport.
    from modules.progress import broker
    sid = 313131
    broker.clear(sid)
    broker.publish(sid, {"node": "username", "status": "done", "found": 3})
    broker.publish(sid, {"node": "_pipeline", "status": "completed"})

    body = ""
    async with client.stream("GET", f"/events/search/{sid}") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for chunk in resp.aiter_text():
            body += chunk

    assert "username" in body
    assert "completed" in body
    assert body.count("data:") == 2     # replay completo y cierre limpio
    broker.clear(sid)
