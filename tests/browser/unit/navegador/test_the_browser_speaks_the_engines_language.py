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


def test_the_profile_travels_with_the_locale(monkeypatch, tmp_path):
    """A browser that PRESENTS en-US must not carry cookies acquired while presenting es-ES: the site
    remembers the contradiction longer than the declaration. Measured 2026-08-29 in `cheapest-monitor__us`
    (worker session 085b1384): the launch already declared en-US and Amazon still served «Deliver to
    Spain» prices in EUR from the persistent profile's cookies — the worker burned ~80s fighting the
    currency and gave up. es-ES keeps the legacy `profile` name so the operator's saved logins stay."""
    _clean(monkeypatch)
    from widgets.navegador import owner as O
    monkeypatch.setattr(O.store, "data_dir", lambda wid: str(tmp_path))
    from voice.engine.core import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    assert O._profile_dir().endswith("/profile"), "Spanish keeps the profile of always"
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    d = O._profile_dir()
    assert d.endswith("/profile-en-US"), f"en-US gets its own profile, got {d}"
