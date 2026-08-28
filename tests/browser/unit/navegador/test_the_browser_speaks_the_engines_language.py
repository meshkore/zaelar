"""V2-469 · the task browser presented es-ES to every site the US engine visited.

Measured in `cheapest-monitor__us` (23:43, worker session 79bfd2ce): Amazon.com product pages came back
in SPANISH («KOORUI 27 Pulgadas… Monitor de Computadora») and Best Buy answered «Select your Country» —
`launch_persistent_context` pinned `locale="es-ES"` + `timezone_id="Europe/Madrid"` for every engine.
V2-411 already fixed the SEARCH header for the same reason (a US search priced hotels in euros); the
browser the worker actually drives kept the pin. Locale and timezone follow the engine's language, paired
(the launch comment's own rule), with env escape hatches and Spanish as the fallback of always.
"""
import importlib

from widgets.navegador import owner


def _clean(monkeypatch):
    monkeypatch.delenv("NAVEGADOR_LOCALE", raising=False)
    monkeypatch.delenv("NAVEGADOR_TZ", raising=False)


def test_the_us_engine_gets_a_us_browser(monkeypatch):
    _clean(monkeypatch)
    from voice.engine.core import langs
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    loc, tz = owner._browser_locale()
    assert loc == "en-US" and tz == "America/New_York"


def test_the_spanish_engine_keeps_the_behaviour_of_always(monkeypatch):
    _clean(monkeypatch)
    from voice.engine.core import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    assert owner._browser_locale() == ("es-ES", "Europe/Madrid")


def test_an_unreadable_language_falls_back_to_spanish(monkeypatch):
    _clean(monkeypatch)
    from voice.engine.core import langs
    monkeypatch.setattr(langs, "current_code", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert owner._browser_locale() == ("es-ES", "Europe/Madrid")


def test_the_env_escape_hatches_win(monkeypatch):
    monkeypatch.setenv("NAVEGADOR_LOCALE", "fr-FR")
    monkeypatch.setenv("NAVEGADOR_TZ", "Europe/Paris")
    assert owner._browser_locale() == ("fr-FR", "Europe/Paris")


def test_the_launch_reads_it_instead_of_a_pin():
    from pathlib import Path
    src = Path("widgets/navegador/owner.py").read_text(encoding="utf-8")
    assert '_browser_locale()' in src
    assert 'locale="es-ES"' not in src.replace('("es-ES", "Europe/Madrid")', "")
