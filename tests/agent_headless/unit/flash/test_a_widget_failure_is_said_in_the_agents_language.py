"""Demo pass 48 (2026-09-29), V6: a YouTube play_result failed and its `message` — «No hay resultados de búsqueda ahora
mismo.», product copy written in Spanish — was spoken verbatim into an English session; demo pass 69, V2: the same
when the composer came back empty. V2-851 F2: a refusal is ONE line of the turn's mouth (`reply.of_op`), and card
copy in the OTHER language is never that line — the session's own generic refusal is; in the same language the
card's sentence is said as it is.

Disarm: drop the `foreign` check in `reply.of_op` → the English test goes red.
"""
from nucleo.turn import reply as R


def _line(res) -> list[str]:
    return [t for _o, t in R.owed([R.of_op("youtube", "play_result", res)], "On it.")]


def test_card_copy_in_another_language_is_never_his_line(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    lines = _line({"ok": False, "error": "no_results", "message": "No hay resultados de búsqueda ahora mismo."})
    assert len(lines) == 1 and "No hay resultados" not in lines[0], lines


def test_card_copy_in_his_language_is_said_as_it_is(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    lines = _line({"ok": False, "error": "x", "message": "No hay resultados de búsqueda ahora mismo (2)."})
    assert len(lines) == 1 and "No hay resultados de búsqueda ahora mismo (2)." in lines[0], lines
