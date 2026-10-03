"""A card the operator closed AFTER an errand began is not reopened by that errand's worker (demo pass 82).

I4 «alright close the pictures» closed the viewer; two minutes later, mid «play some madonna», the image errand's
worker ran `show imagenes` and the viewer sat on screen until the end of the demo. His close is his decision.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo import canvas_closes, worker_api
from nucleo.workers.session import SessionRecord


@pytest.fixture(autouse=True)
def _clean():
    canvas_closes._reset_for_tests()
    yield
    canvas_closes._reset_for_tests()


def _show(rec):
    return asyncio.run(worker_api._exec_allow("show_widget", {"id": "imagenes"}, rec))


def test_his_close_after_the_errand_began_refuses_the_workers_show():
    rec = SessionRecord(task_id="31", goal="red Ferrari F40 photos")
    rec.started = time.time() - 120
    canvas_closes.note({"id": "imagenes", "src": "flash"})
    r = _show(rec)
    assert r["ok"] is False and "CLOSED" in r["error"]


def test_a_close_from_before_the_errand_does_not_bind_it():
    canvas_closes.note({"id": "imagenes", "src": "user"})
    rec = SessionRecord(task_id="32", goal="red Ferrari F40 photos")
    rec.started = time.time() + 1
    assert _show(rec)["ok"] is True


def test_a_workers_own_close_is_not_his():
    rec = SessionRecord(task_id="33", goal="x")
    rec.started = time.time() - 60
    canvas_closes.note({"id": "imagenes", "src": "worker:33"})
    assert _show(rec)["ok"] is True


def test_the_record_is_fed_by_the_one_place_every_close_passes():
    """`voice.observer.emit("widget", "close", …)` is the door; the module is never called by hand."""
    from voice.observer import emit
    emit("widget", "close", extra={"id": "map", "src": "user"})
    assert canvas_closes.closed_after("map", time.time() - 5)
