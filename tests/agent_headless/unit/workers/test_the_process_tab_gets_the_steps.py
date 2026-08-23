"""A diary nobody writes to reads exactly like a task that is doing nothing.

Measured on the operator's session `ed9df756` (2026-08-21 17:21-17:30): the worker opened Google Maps
Directions, dismissed the overlay, took a screenshot, read it, took a snapshot and clicked twice, then
extracted «2h08 / 210 km por AP-2». The Proceso tab said «trabajando» for two and a half minutes.

Nothing failed. `nucleo/workers/progress.phrase()` — the module written for exactly this — DID compose its
sentences, and they DID land in `rec.phase`. But `rec.phase` is one line, the one from RIGHT NOW; the tab reads
`rec.phases`, the ring, and the only door into that ring was `hbnote`, i.e. whatever the worker chose to narrate
about itself. Two entries in the whole errand, both at the end.

These tests go through `WorkerSession._on_event`, the real path. Calling `record_phase` directly would pass with
the wiring deleted, which is the exact shape of this bug.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from nucleo import dispatch  # noqa: E402
from nucleo.workers import session as wsession  # noqa: E402


@pytest.fixture
def live(monkeypatch):
    """A registered session and a WorkerSession bound to it — the shape production has when a phase arrives.

    The registry is swapped for an EMPTY one: a unit test that walked the real `_SESSIONS` would read (and grow)
    whatever the operator's engine had running in this process.
    """
    rec = wsession.SessionRecord(task_id="t1", kind="web", goal="ruta Zaragoza→Valls")
    rec.surface = ""
    monkeypatch.setattr(dispatch, "_SESSIONS", {"t1": rec})
    ws = wsession.WorkerSession.__new__(wsession.WorkerSession)
    ws._rec = rec
    ws._bus = lambda *a, **k: None
    ws._emit_chip = lambda *a, **k: None
    ws._emit_step = lambda *a, **k: None
    return ws, rec


def _phase(ws, label, *, quiet=True):
    ws._on_event(types.SimpleNamespace(type="phase", data={"label": label, "quiet": quiet}))


def test_a_step_phrase_reaches_the_diary(live):
    """THE CASE THAT JUSTIFIES THE FILE. `progress.phrase()` produced this sentence for every browser step and
    the tab never saw one of them."""
    ws, rec = live
    _phase(ws, "entrando en google.com/maps…")
    assert [p["s"] for p in rec.phases] == ["entrando en google.com/maps…"]


def test_the_whole_errand_reads_like_a_sentence(live):
    """The operator asked for a chronological diary, not a spinner: «accediendo a Google Maps… rellenando los
    campos… extrayendo la ruta». Replays the real step sequence of `ed9df756`."""
    ws, rec = live
    for s in ("entrando en google.com/maps…", "cerrando un aviso…", "mirando la página…",
              "pulsando «Cómo llegar»…", "recogiendo resultados…"):
        _phase(ws, s)
    assert len(rec.phases) == 5
    assert rec.phases[0]["s"].startswith("entrando") and rec.phases[-1]["s"].startswith("recogiendo")
    assert rec.phases[0]["t"] <= rec.phases[-1]["t"], "el diario tiene que ir en orden de tiempo"


def test_the_same_line_twice_is_not_progress(live):
    """Three `scroll` in a row produce «recorriendo la página» three times, and three identical lines look like
    progress without being any. Deduped against the PREVIOUS one only — coming back to a page later is a real
    step and has to show."""
    ws, rec = live
    _phase(ws, "recorriendo la página…")
    _phase(ws, "recorriendo la página…")
    _phase(ws, "mirando la página…")
    _phase(ws, "recorriendo la página…")
    assert [p["s"] for p in rec.phases] == ["recorriendo la página…", "mirando la página…", "recorriendo la página…"]


def test_a_QUIET_phase_still_reaches_the_diary(live):
    """Sensitivity, and it is the whole bug: `quiet` decides whether the OBSERVABILITY row is duplicated next to
    a richer `step`. It says nothing about the diary — and every browser step carries a step, so `quiet` is true
    exactly when the operator most needs the line."""
    ws, rec = live
    _phase(ws, "abriendo una página…", quiet=True)
    assert len(rec.phases) == 1, "una fase silenciosa para el panel no es una fase invisible para el operador"


def test_an_empty_label_does_not_write_a_blank_line(live):
    """`_tool_phase` returns "" on purpose when the phase belongs to somebody else (hbnote sets a richer one).
    An empty line in the diary is a step the operator cannot read."""
    ws, rec = live
    _phase(ws, "")
    assert rec.phases == []


def test_the_ring_is_bounded(live):
    """This is what the operator MIRA, not the audit — that lives whole in observability with its evidence."""
    ws, rec = live
    for i in range(dispatch.PHASES_KEPT + 10):
        _phase(ws, f"paso {i}…")
    assert len(rec.phases) == dispatch.PHASES_KEPT
    assert rec.phases[-1]["s"] == f"paso {dispatch.PHASES_KEPT + 9}…"


def test_hbnote_still_writes_the_same_diary(live):
    """The two doors share ONE rule on purpose. Two copies of a dedup drift, and a drifting dedup fails by going
    quiet — which is the failure mode this whole file is about."""
    _, rec = live
    dispatch.session_phase("t1", "componiendo el informe")
    dispatch.session_phase("t1", "componiendo el informe")
    assert [p["s"] for p in rec.phases] == ["componiendo el informe"]
    assert rec.phase == "componiendo el informe", "hbnote sigue fijando la fase de AHORA, además del diario"


def test_the_wiring_is_in_the_event_handler():
    """Guard on the wiring. A test that called `record_phase` directly would pass with this line deleted — which
    is precisely how the feature shipped inert: every piece existed and nobody joined two of them."""
    import inspect
    src = inspect.getsource(wsession.WorkerSession._on_event)
    i = src.index('ev.type == "phase"')
    assert "record_phase" in src[i:i + 1600], "el diario dejó de escribirse desde el stream del backend"
