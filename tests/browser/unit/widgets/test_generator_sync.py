"""Tests for the generator's actions↔apply_action synchronization gate (V2-025)."""
from widgets import generator


def test_concise_id_strips_filler_and_caps():
    """A new widget's ID comes from the CONTENT words, not the entire instruction (§2026-07-15:
    'implementar en el widget youtube la capacidad…' produced the 40-character junk ID)."""
    # without verb/filler, at most 3 content words
    assert generator._concise_id("crea un widget del tiempo en Soria") == "tiempo-soria"
    got = generator._concise_id("Implementar en el widget youtube la capacidad de ampliarse a toda la pantalla")
    assert got == "youtube-ampliarse-toda"
    assert len(got) <= 40 and "implementar" not in got and "widget" not in got
    # fallback: if everything is filler, it does not crash (falls back to the raw slug)
    assert generator._concise_id("crea un widget") != ""


_APPLY = """
def apply_action(action, payload=None):
    p = payload or {}
    if action == "add_meeting":
        return {"ok": True}
    elif action in ("done", "snooze"):
        return {"ok": True}
    return {"ok": False}
"""


def test_apply_action_names_extracts_handled():
    names = generator._apply_action_names(_APPLY)
    assert names == {"add_meeting", "done", "snooze"}


def test_apply_action_names_none_without_fn():
    assert generator._apply_action_names("def view_data(q=''): return {}") is None


def test_sync_ok_when_matched():
    man = {"kind": "passive", "actions": {"add_meeting": {}, "done": {}, "snooze": {}}}
    assert generator._validate_actions_sync(man, _APPLY) is None


def test_sync_rejects_declared_without_handler():
    man = {"kind": "passive", "actions": {"add_meeting": {}, "done": {}, "snooze": {}, "fantasma": {}}}
    err = generator._validate_actions_sync(man, _APPLY)
    assert err and "fantasma" in err


def test_sync_rejects_handled_but_undeclared():
    man = {"kind": "passive", "actions": {"add_meeting": {}}}          # done/snooze handled but not declared
    err = generator._validate_actions_sync(man, _APPLY)
    assert err and ("done" in err or "snooze" in err)


def test_sync_rejects_declared_actions_without_apply_action():
    man = {"kind": "passive", "actions": {"x": {}}}
    err = generator._validate_actions_sync(man, "def view_data(q=''): return {}")
    assert err and "apply_action" in err


def test_sync_skips_backed_widgets():
    # backed → routed through the owner's mailbox, not data.py:apply_action → not our gate to enforce
    man = {"kind": "backed", "actions": {"whatever": {}}}
    assert generator._validate_actions_sync(man, "def view_data(q=''): return {}") is None


def test_sync_failopen_on_unparseable_dispatch():
    # a dict-dispatch style we can't scan statically → empty handled set → skip (fail-open, never false-reject)
    src = "_H = {'a': lambda p: p}\ndef apply_action(action, payload=None):\n    return _H.get(action, lambda p: {})(payload)\n"
    man = {"kind": "passive", "actions": {"a": {}, "b": {}}}
    assert generator._validate_actions_sync(man, src) is None
