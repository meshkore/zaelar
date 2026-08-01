"""Tests del provider nucleo (V2-004 · T65) — registro, build, superficie testeable sin arrancar un stream real."""
from voice.engine.llm import build_llm
from voice.engine.llm.providers import nucleo


def test_registered_and_builds():
    obj = build_llm("nucleo")
    assert isinstance(obj, nucleo.NucleoLLM)
    assert obj.label == "zaelar.nucleo"
    assert obj.model == "nucleo-flash"


def test_set_briefing_is_noop():
    obj = nucleo.NucleoLLM()
    # duo usa set_briefing; en nucleo la memoria de arranque sale del prompt → aquí es no-op, no debe lanzar
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
    # V2-039: los eventos de widget llevan procedencia (`src`) — el fallback del provider marca 'flash'.
    assert ("show", {"id": "agenda", "src": "flash"}) in events


def test_widget_fallback_close_all(monkeypatch):
    events = []
    nucleo._widget_fallback("cierra todos los widgets", lambda kind, action, extra=None: events.append((action, extra)))
    assert ("close", {"src": "flash"}) in events
