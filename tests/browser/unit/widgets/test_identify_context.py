"""Tests of context-based TIE-BREAKING in widget routing (V2-078, operator idea): when scores are TIED,
the target widget is resolved by the priority **open > recently used > catalog** — generic, without
hardcoded phrases. Covers `runtime.identify` (tiebreak + score), `state.push_recent_widgets` (MRU), and the
ordering/annotation of `brief.for_prompt`."""
from widgets import runtime


def _row(wid: str, kw: str) -> dict:
    """Row from the identify index (V2-082 contract: alias/name) for a fictitious widget with ONE extra alias
(to force controlled ties). The name (id) is included as an implicit alias, just as in `_aliases_of`."""
    aliases = [runtime._norm(wid), runtime._norm(kw)]
    return {"w": {"id": wid, "title": wid}, "aliases": aliases,
            "alias_tokens": {t for a in aliases for t in a.split()}}


def test_tie_broken_by_open(monkeypatch):
    # Two widgets with the SAME keyword → "cita" ties them both.
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # Without context: ambiguous, with no match.
    r = runtime.identify("una cita")
    assert r["match"] is None and r["ambiguous"] is True and r["score"] > 0
    # With 'agenda' OPEN: agenda wins.
    r = runtime.identify("una cita", open_ids=["agenda"])
    assert r["match"] == "agenda" and r["ambiguous"] is False


def test_open_beats_recent(monkeypatch):
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # 'mensajeria' open, 'agenda' recent → the OPEN one wins (1st layer).
    r = runtime.identify("una cita", open_ids=["mensajeria"], recent_ids=["agenda"])
    assert r["match"] == "mensajeria"


def test_recent_breaks_tie_when_nothing_open(monkeypatch):
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # Nothing open, but 'agenda' recently used → it wins by the 2nd layer.
    r = runtime.identify("una cita", recent_ids=["agenda"])
    assert r["match"] == "agenda"


def test_recent_normalises_instance_ids(monkeypatch):
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # Instance ids (navegador::t1) are normalized to the base id.
    r = runtime.identify("una cita", recent_ids=["agenda::t9"])
    assert r["match"] == "agenda"


def test_unambiguous_name_ignores_context(monkeypatch):
    # 'agenda' wins by score (id-hit=3) even though 'mensajeria' is open → context only breaks TIES.
    monkeypatch.setattr(runtime, "_identify_index",
                        lambda: [_row("agenda", "cita"), _row("mensajeria", "mensaje")])
    r = runtime.identify("abre la agenda", open_ids=["mensajeria"])
    assert r["match"] == "agenda"


def test_push_recent_widgets_mru(tmp_path, monkeypatch):
    # Real MRU behavior against state: deduplication, most recent first, cap.
    from memory import state
    seen = {}

    def _read():
        return dict(seen.get("v", dict(state._DEFAULT)))

    def _write(d):
        seen["v"] = dict(d)

    monkeypatch.setattr(state, "read", _read)
    monkeypatch.setattr(state, "write", _write)
    state.push_recent_widgets("agenda")
    state.push_recent_widgets(["mensajeria", "clock"])
    state.push_recent_widgets("agenda")           # Reuse → moves to the front, without duplication.
    out = _read()["recent_widgets"]
    assert out[0] == "agenda"
    assert out.count("agenda") == 1
    assert set(out) == {"agenda", "mensajeria", "clock"}
    # Cap: never grows without limit.
    for i in range(20):
        state.push_recent_widgets(f"w{i}")
    assert len(_read()["recent_widgets"]) <= state._RECENT_CAP


def test_for_prompt_orders_and_marks():
    from widgets import brief
    txt = brief.for_prompt(open_ids=["agenda"], recent_ids=["clock"])
    # The open widget is marked EN PANTALLA; the recent one, recently used.
    assert "EN PANTALLA" in txt and "usado hace poco" in txt
    lines = [l for l in txt.splitlines() if l.startswith("- ")]
    ids = [l.split()[1] for l in lines]
    assert ids and ids[0] == "agenda"                 # the open widget comes first
    assert ids.index("clock") < ids.index("mensajeria")  # the recent one comes before any catalog item
