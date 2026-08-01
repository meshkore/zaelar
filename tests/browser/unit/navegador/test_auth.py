"""Tests del detector de muro de login del navegador (INI-016, auth) — el arreglo que impide inventar credenciales
(bug 2026-07-10: el bucle tecleó user@gmail.com en el login de Google). DETERMINISTA, sin red ni modelo."""
from widgets.navegador import agent


def test_login_url_is_detected():
    # URLs de login CONOCIDAS → muro de login (sin necesidad de mirar el DOM).
    assert agent._looks_like_login("https://accounts.google.com/v3/signin/identifier?x=1", "")
    assert agent._looks_like_login("https://es.wallapop.com/login", "")
    assert agent._looks_like_login("https://www.linkedin.com/checkpoint/lg/login", "")
    assert agent._looks_like_login("https://appleid.apple.com/sign-in", "")


def test_password_field_is_detected():
    # URL cualquiera pero con campo de CONTRASEÑA + jerga de login en el snapshot → muro de login.
    els = '[3] textbox "Contraseña"\n[4] button "Iniciar sesión"'
    assert agent._looks_like_login("https://ejemplo.com/x", els)


def test_home_and_results_are_not_login():
    # Portada con un simple botón «Iniciar sesión» (SIN campo password) → NO es login (no dispara falsos positivos).
    assert not agent._looks_like_login("https://www.youtube.com/", '[1] button "Iniciar sesión"')
    # Página de resultados de búsqueda → NO es login.
    assert not agent._looks_like_login("https://es.wallapop.com/search?kw=moto", '[7] textbox "¿Qué buscas?"')
    # Portada limpia.
    assert not agent._looks_like_login("https://www.google.com/", "")


def test_login_site_is_readable_host():
    assert agent._login_site("https://accounts.google.com/v3/signin") == "accounts.google.com"
    assert agent._login_site("https://www.wallapop.com/login") == "wallapop.com"
