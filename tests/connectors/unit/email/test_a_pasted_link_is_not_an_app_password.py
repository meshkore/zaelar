"""What the user PASTES into the app-password box, and what happens when it cannot be one (V2-559).

The operator followed the guide, created the app password at Google, pasted the LINK of that page instead of
the password, and the product answered `[AUTHENTICATIONFAILED] Invalid credentials` translated into "use an
app password" — over a password he had just created. Every word true, none of it useful: the evidence (a
47-character string starting with `https://`) was in hand and thrown away.

Three seams, one rule (`connectors/email/credentials`): the form's own gate before enqueuing, the door the
HTTP API and the supervisor share, and the message after IMAP says no.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.email import credentials as creds

# The shape the operator actually pasted (a Google account URL), redacted to its structure.
PASTED_LINK = "https://xxx.google.com/u/AB_Cdefgh/x/aBC1dEfgGH"
GOOD_GMAIL = "abcdefghijklmnop"


# ── normalize ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_spaces_the_provider_PRINTS_are_stripped():
    # Google shows the password as four groups of four; `str.strip()` — what we had — leaves them intact.
    assert creds.normalize("abcd efgh ijkl mnop") == GOOD_GMAIL
    assert creds.normalize("  abcd\tefgh\nijkl mnop  ") == GOOD_GMAIL


def test_normalize_survives_nothing_at_all():
    assert creds.normalize(None) == ""
    assert creds.normalize("") == ""


# ── diagnose ──────────────────────────────────────────────────────────────────────────────────────────────
def test_a_LINK_is_named_as_a_link_and_not_as_a_wrong_password():
    why = creds.diagnose("gmail", "someone@example.com", PASTED_LINK)
    assert why and "ENLACE" in why
    # It has to say what to do with the link, or it is the same dead end with better wording.
    assert "contraseña de aplicación" in why.lower()


def test_a_link_is_caught_for_ANY_provider_even_one_with_no_published_shape():
    # Outlook/Yahoo have no fixed format, so the length rule never fires there — the URL rule must.
    for pid in ("outlook", "yahoo", "otro", ""):
        assert creds.diagnose(pid, "a@b.com", PASTED_LINK), pid


def test_an_address_pasted_into_the_password_box_is_named():
    assert "dirección de correo" in (creds.diagnose("gmail", "a@b.com", "someone@gmail.com") or "")


def test_a_google_app_password_of_the_wrong_LENGTH_says_how_many_it_got():
    why = creds.diagnose("gmail", "a@gmail.com", "abcdefghijklmno")   # 15
    assert why and "15" in why and "16" in why


def test_a_correct_google_app_password_passes_spaces_and_all():
    assert creds.diagnose("gmail", "a@gmail.com", "abcd efgh ijkl mnop") is None


def test_an_apple_password_keeps_its_dashes_and_still_passes():
    # Apple prints xxxx-xxxx-xxxx-xxxx and its sign-in accepts it with or without them; the separators must
    # not count against the length.
    assert creds.diagnose("icloud", "a@icloud.com", "abcd-efgh-ijkl-mnop") is None


def test_a_provider_with_NO_published_shape_is_never_told_its_password_is_wrong():
    # The expensive direction: a false "that is not a password" locks someone out of a mailbox that works.
    for pwd in ("Whatever-123!", "x", "a" * 40):
        assert creds.diagnose("outlook", "a@outlook.com", pwd) is None, pwd
        assert creds.diagnose("", "a@mydomain.com", pwd) is None, pwd


def test_an_empty_password_says_it_is_not_the_normal_one():
    why = creds.diagnose("gmail", "a@gmail.com", "   ")
    assert why and "contraseña normal" in why


# ── the shared door: control.validate_connect ─────────────────────────────────────────────────────────────
def _connect(**over):
    payload = {"email_address": "rjj@proars.com", "provider": "gmail", "email_password": GOOD_GMAIL}
    payload.update(over)
    return payload


def test_the_shared_door_REFUSES_the_link_before_it_is_ever_stored():
    from connectors.messaging import control
    why = control.validate_connect("email", _connect(email_password=PASTED_LINK))
    assert why and "ENLACE" in why


def test_the_shared_door_accepts_the_real_thing():
    from connectors.messaging import control
    assert control.validate_connect("email", _connect()) is None
    assert control.validate_connect("email", _connect(email_password="abcd efgh ijkl mnop")) is None


def test_a_custom_domain_on_gmail_is_judged_by_GOOGLE_rules():
    # rjj@proars.com with provider=gmail is a Workspace account: same servers, same 16-letter rule.
    from connectors.messaging import control
    assert control.validate_connect("email", _connect(email_password="short")) is not None


def test_an_unknown_domain_with_no_provider_still_asks_for_its_servers():
    from connectors.messaging import control
    why = control.validate_connect("email", _connect(provider="", email_password="whatever-123"))
    assert why and "IMAP" in why


def test_what_gets_PERSISTED_carries_no_spaces(monkeypatch):
    from connectors.messaging import control
    seen = {}
    monkeypatch.setattr(control.cfg, "set", lambda platform, patch: seen.update(patch))

    class _Svc:
        @staticmethod
        async def stop():
            return None

        @staticmethod
        def start():
            return None

    monkeypatch.setattr(control, "_services", lambda: {"email": _Svc})
    res = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        control.apply_connect("email", _connect(email_password="abcd efgh ijkl mnop")))
    assert res["ok"] is True
    assert seen["email_password"] == GOOD_GMAIL


# ── the supervisor: a refusal the user cannot see is a hang ────────────────────────────────────────────────
def test_a_REFUSED_connect_is_reported_back_to_the_card(monkeypatch):
    """`apply_connect` returned {ok:False,error} and the supervisor dropped it on the floor: the widget had
    already painted "Conectando…" and waited forever for a status nobody was going to publish."""
    from connectors.messaging import supervisor

    published: list[tuple] = []
    monkeypatch.setattr(supervisor.store, "take_control",
                        lambda: [{"platform": "email", "cmd": "connect", "email_password": PASTED_LINK}])

    async def _apply(platform, cmd):
        return {"ok": False, "error": "eso es un ENLACE"}

    monkeypatch.setattr(supervisor.control, "apply_connect", _apply)
    monkeypatch.setattr(supervisor, "_report_failure", lambda p, d: published.append((p, d)))
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(supervisor._drain_once())
    assert published == [("email", "eso es un ENLACE")]


def test_an_EXCEPTION_while_connecting_is_reported_too(monkeypatch):
    from connectors.messaging import supervisor

    published: list[tuple] = []
    monkeypatch.setattr(supervisor.store, "take_control",
                        lambda: [{"platform": "email", "cmd": "connect"}])

    async def _boom(platform, cmd):
        raise RuntimeError("the server hung up")

    monkeypatch.setattr(supervisor.control, "apply_connect", _boom)
    monkeypatch.setattr(supervisor, "_report_failure", lambda p, d: published.append((p, d)))
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(supervisor._drain_once())
    assert published and "the server hung up" in published[0][1]


def test_a_SUCCESSFUL_connect_reports_nothing(monkeypatch):
    # Counterweight: an error status published on the happy path would paint a failure over a live channel.
    from connectors.messaging import supervisor

    published: list[tuple] = []
    monkeypatch.setattr(supervisor.store, "take_control",
                        lambda: [{"platform": "email", "cmd": "connect"}])

    async def _ok(platform, cmd):
        return {"ok": True, "platform": platform}

    monkeypatch.setattr(supervisor.control, "apply_connect", _ok)
    monkeypatch.setattr(supervisor, "_report_failure", lambda p, d: published.append((p, d)))
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(supervisor._drain_once())
    assert published == []


# ── the message AFTER the server says no ──────────────────────────────────────────────────────────────────
@pytest.fixture()
def _stored(monkeypatch):
    from connectors.email import config

    def _set(pwd, addr="rjj@proars.com", pid="gmail"):
        monkeypatch.setattr(config, "password", lambda: creds.normalize(pwd))
        monkeypatch.setattr(config, "address", lambda: addr)
        monkeypatch.setattr(config, "resolved_provider_id", lambda: pid)
    return _set


def test_an_auth_failure_over_a_LINK_names_the_link_instead_of_blaming_the_password(_stored):
    from connectors.email import service
    _stored(PASTED_LINK)
    msg = service._friendly_error("IMAP: b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'")
    assert "ENLACE" in msg


def test_an_auth_failure_over_a_PLAUSIBLE_password_gives_the_provider_causes(_stored):
    from connectors.email import service
    _stored(GOOD_GMAIL, addr="someone@gmail.com")
    msg = service._friendly_error("IMAP: b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'")
    assert "IMAP" in msg and "ENLACE" not in msg


def test_a_custom_domain_is_told_its_admin_may_be_the_reason(_stored):
    # rjj@proars.com is Workspace: app passwords and IMAP can be off account-wide, and no amount of retyping
    # the password fixes that.
    from connectors.email import service
    _stored(GOOD_GMAIL, addr="rjj@proars.com")
    msg = service._friendly_error("IMAP: b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'")
    assert "proars.com" in msg and "administrador" in msg


def test_the_other_failure_kinds_are_untouched(_stored):
    from connectors.email import service
    _stored(GOOD_GMAIL)
    assert "servidor de correo" in service._friendly_error("nodename nor servname provided")
    assert "no respondió a tiempo" in service._friendly_error("operation timed out")


# ── what the CONNECTOR reads back out of the store ────────────────────────────────────────────────────────
def test_config_password_strips_what_the_store_already_holds(monkeypatch):
    """Normalizing on the way IN is not enough: an install that already saved the password with the spaces
    Google prints keeps failing at every reconnect until someone retypes it. The read is the last chance."""
    from connectors.email import config
    monkeypatch.setattr(config, "_cfg", lambda: {"email_password": "abcd efgh ijkl mnop"})
    assert config.password() == GOOD_GMAIL


def test_config_password_survives_an_empty_store(monkeypatch):
    from connectors.email import config
    monkeypatch.setattr(config, "_cfg", lambda: {})
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    assert config.password() == ""
