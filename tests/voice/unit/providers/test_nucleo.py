"""Tests for the nucleo provider (V2-004 · T65) — registration, build, and testable surface without starting a real stream."""
from voice.engine.llm import build_llm
from voice.engine.llm.providers import nucleo


def test_registered_and_builds():
    obj = build_llm("nucleo")
    assert isinstance(obj, nucleo.NucleoLLM)
    assert obj.label == "zaelar.nucleo"
    assert obj.model == "nucleo-flash"


def test_set_briefing_is_noop():
    obj = nucleo.NucleoLLM()
    # duo uses set_briefing; in nucleo, the startup memory comes from the prompt → this is a no-op and must not raise
    assert obj.set_briefing("cualquier cosa") is None


def test_last_user_text_from_ctx():
    class _Item:
        def __init__(self, role, text):
            self.role = role
            self.text_content = text
    class _Ctx:
        items = [_Item("assistant", "hola"), _Item("user", "  enséñame la agenda  ")]
    assert nucleo._last_user_text(_Ctx()) == "enséñame la agenda"


def test_widget_fallback_emits_show(monkeypatch):
    import widgets.runtime as rt
    monkeypatch.setattr(rt, "identify", lambda text, **context: {"match": "agenda"})
    events = []
    nucleo._widget_fallback("enséñame la agenda", lambda kind, action, extra=None: events.append((action, extra)))
    # V2-039: widget events carry provenance (`src`) — the provider fallback marks them as 'flash'.
    assert ("show", {"id": "agenda", "src": "flash"}) in events


def test_widget_fallback_close_all(monkeypatch):
    events = []
    nucleo._widget_fallback("cierra todos los widgets", lambda kind, action, extra=None: events.append((action, extra)))
    assert ("close", {"src": "flash"}) in events
