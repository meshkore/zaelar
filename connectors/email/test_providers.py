"""Tests del REGISTRO de proveedores de email (V2-055) — puro, sin red."""
from connectors.email import providers as pv


def test_all_providers_present():
    for pid in ("gmail", "outlook", "yahoo", "icloud", "imap"):
        assert pv.get(pid) is not None


def test_gmail_prefers_oauth_but_allows_password():
    g = pv.get("gmail")
    assert g.default_method == "oauth"
    assert g.supports("oauth") and g.supports("password")
    assert g.oauth and "mail.google.com" in g.oauth.scopes[0]


def test_outlook_is_oauth_only():
    o = pv.get("outlook")
    assert o.auth_methods == ("oauth",)          # Microsoft deshabilitó basic-auth → sin password
    assert not o.supports("password")
    assert o.oauth and "outlook.office.com" in o.oauth.scopes[0]


def test_password_only_providers():
    for pid in ("yahoo", "icloud", "imap"):
        assert pv.get(pid).auth_methods == ("password",)
        assert pv.get(pid).oauth is None


def test_by_domain_deduces_provider():
    assert pv.by_domain("a@gmail.com").id == "gmail"
    assert pv.by_domain("a@hotmail.com").id == "outlook"
    assert pv.by_domain("a@live.com").id == "outlook"
    assert pv.by_domain("a@icloud.com").id == "icloud"
    assert pv.by_domain("a@empresa-rara.es") is None


def test_public_list_has_no_secrets_and_lists_all():
    pub = pv.public_list()
    ids = {p["id"] for p in pub}
    assert {"gmail", "outlook", "yahoo", "icloud", "imap"} <= ids
    for p in pub:
        assert set(p.keys()) == {"id", "label", "auth_methods", "oauth", "needs_hosts", "note"}


def test_legacy_presets_alias():
    assert pv.PRESETS["gmail"]["imap_host"] == "imap.gmail.com"
    assert "imap" not in pv.PRESETS         # 'otro' no tiene hosts → no está en PRESETS
