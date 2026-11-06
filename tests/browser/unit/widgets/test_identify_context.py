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
