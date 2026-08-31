"""Tests for the browser's login-wall detector (INI-016, auth) — the fix that prevents inventing credentials
(bug 2026-07-10: the loop typed user@gmail.com into Google's login). DETERMINISTIC, with no network or model."""
from widgets.navegador import agent


def test_login_url_is_detected():
    # KNOWN login URLs → login wall (without needing to inspect the DOM).
    assert agent._looks_like_login("https://accounts.google.com/v3/signin/identifier?x=1", "")
    assert agent._looks_like_login("https://es.wallapop.com/login", "")
    assert agent._looks_like_login("https://www.linkedin.com/checkpoint/lg/login", "")
    assert agent._looks_like_login("https://appleid.apple.com/sign-in", "")


def test_password_field_is_detected():
    # Any URL with a PASSWORD field + login terminology in the snapshot → login wall.
    els = '[3] textbox "Contraseña"\n[4] button "Iniciar sesión"'
    assert agent._looks_like_login("https://ejemplo.com/x", els)


def test_home_and_results_are_not_login():
    # Home page with a simple «Iniciar sesión» button (WITHOUT a password field) → NOT a login page (does not trigger false positives).
    assert not agent._looks_like_login("https://www.youtube.com/", '[1] button "Iniciar sesión"')
    # Search results page → NOT a login page.
    assert not agent._looks_like_login("https://es.wallapop.com/search?kw=moto", '[7] textbox "¿Qué buscas?"')
    # Clean home page.
    assert not agent._looks_like_login("https://www.google.com/", "")


def test_login_site_is_readable_host():
    assert agent._login_site("https://accounts.google.com/v3/signin") == "accounts.google.com"
    assert agent._login_site("https://www.wallapop.com/login") == "wallapop.com"
