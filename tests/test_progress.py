"""
Tests del broker de progreso (modules/progress.py). Sin red, asyncio puro.
"""
import asyncio

import pytest

from modules.progress import ProgressBroker, broker, publish


def test_publish_records_history():
    b = ProgressBroker()
    b.publish(1, {"node": "username", "status": "done"})
    assert b.history(1) == [{"node": "username", "status": "done"}]


def test_history_is_capped():
    b = ProgressBroker(max_history=3)
    for i in range(5):
        b.publish(1, {"node": str(i), "status": "done"})
    hist = b.history(1)
    assert len(hist) == 3
    assert [h["node"] for h in hist] == ["2", "3", "4"]   # se quedan los últimos


async def test_subscribe_replays_then_streams_live():
    b = ProgressBroker()
    b.publish(7, {"node": "a", "status": "done"})          # evento previo
    gen = b.subscribe(7)
    first = await gen.__anext__()
    assert first["node"] == "a"                            # replay del historial
    b.publish(7, {"node": "b", "status": "running"})       # evento vivo
    nxt = await gen.__anext__()
    assert nxt["node"] == "b"
    await gen.aclose()


async def test_subscriber_cleaned_up_on_cancel():
    b = ProgressBroker()
    gen = b.subscribe(9)
    # el primer __anext__ bloquea esperando; al cancelar, el finally del
    # generador descarta la cola suscripta
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0)
    assert len(b._subs[9]) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(b._subs[9]) == 0


def test_is_terminal():
    b = ProgressBroker()
    assert b.is_terminal({"node": "_pipeline", "status": "completed"})
    assert b.is_terminal({"node": "_pipeline", "status": "error"})
    assert not b.is_terminal({"node": "_pipeline", "status": "running"})
    assert not b.is_terminal({"node": "username", "status": "done"})


def test_publish_helper_adds_timestamp():
    broker.clear(555)
    publish(555, "username", "done", found=3)
    ev = broker.history(555)[-1]
    assert ev["node"] == "username" and ev["status"] == "done"
    assert ev["found"] == 3 and "ts" in ev
    broker.clear(555)
