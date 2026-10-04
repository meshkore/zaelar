"""ONE door to connect a service: the ⚙ Conectores section, opened on that connector (operator 2026-10-04).

Until 2026-10-04 seven widgets carried a connect screen of their own plus `connect` / `open_connectors` actions, so
«conecta mi Drive» had two plausible destinations (the files card's wizard or the Conectores tab) and the model picked
one by luck — measured in the agenda (T12 routed its Google connector to MENSAJERÍA) and in the files card. Commit
6a39a053 removed them; connecting, configuring and disconnecting live only in the Conectores section, reached the
SAME way by voice (`show_panel panel='conectores' connector=…`), by text (the probe mirrors the decision as
`panel:conectores:<id>`), by a known phrase (the action map) and by hand (`ctx.openConnector`).

Three things are pinned here, each disarm-proved:
  1. voice and text AGREE, and the connector argument — an id, a product name, a word in ES or EN — lands on the
     catalog id the section knows (`nucleo/flash/connector_canon.py`), '' for garbage;
  2. no widget keeps a connect door (a ratchet over `widgets/*/manifest.json` and `actions.py`/`data.py`);
  3. a browser «login» to Spotify / WhatsApp / Telegram / email is redirected to the section and NEVER opens a browser.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from nucleo.flash import connector_canon as CC
from nucleo.flash import probe_decide as PD
from nucleo.flash import router
from nucleo.flash import tool_executor_calls as TEC
from nucleo.flash import web_auth

ENGINE = Path(__file__).resolve().parents[4]
WIDGETS = ENGINE / "widgets"


# ── 1. the canon: an id, a product name or a word lands on the catalog id ──────────────────────────────────────

@pytest.mark.parametrize("arg,cid", [
    # ids, as they are
    ("gdrive", "gdrive"), ("google", "google"), ("whatsapp", "whatsapp"), ("telegram", "telegram"),
    ("email", "email"), ("spotify", "spotify"), ("google-contacts", "google-contacts"), ("onedrive", "onedrive"),
    ("google-photos", "google-photos"), ("youtube", "youtube"),
    # product names, any case, with or without the vendor
    ("Google Drive", "gdrive"), ("Drive", "gdrive"), ("Google Calendar", "google"), ("WhatsApp", "whatsapp"),
    ("Gmail", "email"), ("outlook", "email"), ("Spotify", "spotify"), ("Google Contacts", "google-contacts"),
    ("Google Photos", "google-photos"), ("OneDrive", "onedrive"), ("Google Meet", "google-meet"),
    # words in ES and EN
    ("calendario", "google"), ("correo", "email"), ("mail", "email"), ("wasap", "whatsapp"),
    ("contactos", "google-contacts"), ("contacts", "google-contacts"), ("people", "google-contacts"),
    ("fotos", "google-photos"), ("galeria", "google-photos"),
    # a phrase that CONTAINS the word
    ("mi google drive", "gdrive"), ("my Google Calendar", "google"), ("la cuenta de spotify", "spotify"),
    ("gmail.com", "email"),
])
def test_an_id_a_product_name_or_a_word_names_the_catalog_connector(arg, cid):
    assert CC.canon_connector(arg) == cid


def test_google_drive_beats_google_which_is_the_calendars_id():
    """The longest vocabulary word wins: «google drive» must not fall on `google`, the calendar."""
    assert CC.canon_connector("google drive") == "gdrive"
    assert CC.canon_connector("google") == "google"


@pytest.mark.parametrize("garbage", ["", None, "   ", "zzz", "mi primo", "netflix", "wallapop.com", "???"])
def test_garbage_names_nothing_so_the_section_opens_on_its_list(garbage):
    assert CC.canon_connector(garbage) == ""


def test_a_service_with_nothing_to_connect_or_not_built_is_not_a_door():
    """`auth: none` (torrent, YouTube audio) has no account to link and must not shadow the account it is named
    after; a planned / not-possible connector has no guide to open yet."""
    assert CC.canon_connector("torrent") == ""
    assert CC.canon_connector("youtube") == "youtube"          # the ACCOUNT, not `youtube-audio`
    assert CC.canon_connector("slack") == ""
    assert CC.canon_connector("deezer") == ""


def test_the_vocabulary_is_the_catalogs_own():
    """A connector added to `connectors/catalog/` is reachable without touching the canon."""
    built = {json.loads(f.read_text(encoding="utf-8")).get("id") for f in (ENGINE / "connectors" / "catalog").glob("*.json")
             if json.loads(f.read_text(encoding="utf-8")).get("state") == "built"
             and json.loads(f.read_text(encoding="utf-8")).get("auth") != "none"}
    for cid in built:
        assert CC.canon_connector(cid) == cid, cid
    assert CC.canon_connector("google-contacts") == "google-contacts", "the live row with no manifest"


# ── 1b. voice and text agree: the probe's decision is the voice turn's emit ───────────────────────────────────

class _Sess:
    window: list = []
    last_action = ""
    brief = None


def _probe_action(text, calls):
    blk = asyncio.run(PD.name_the_action(_hard=None, _router=router, _tbrief=None, _vault_gate=None, ingest=None,
                                         names={c["name"] for c in calls}, sess=_Sess(), tags=[], text=text,
                                         tool_calls=calls))
    return blk.get("action", "")


def _voice_panel_emit(args, text):
    """The voice turn's `show_panel` arm, with `emit` captured; returns the `panel` event's extra."""
    got = []
    TEC._t_show_panel(args=args, _router=router, _tool_fired=set(), acted={}, operator_text="", text=text,
                      emit=lambda kind, act, text="", extra=None, **kw: got.append((kind, act, extra or {})))
    panels = [(a, x) for k, a, x in got if k == "panel"]
    assert len(panels) == 1, got
    return panels[0]


@pytest.mark.parametrize("text,connector,cid", [
    ("conecta mi Drive", "Drive", "gdrive"),
    ("connect my Google Calendar", "Google Calendar", "google"),
    ("quiero enlazar WhatsApp", "whatsapp", "whatsapp"),
    ("vincula mi correo", "correo", "email"),
    ("conéctame Spotify", "spotify", "spotify"),
    ("link my Google Contacts", "google contacts", "google-contacts"),
])
def test_voice_and_text_open_the_same_connector(text, connector, cid):
    calls = [{"name": "show_panel", "args": {"panel": "conectores", "connector": connector}}]
    assert _probe_action(text, calls) == f"panel:conectores:{cid}"
    act, extra = _voice_panel_emit(calls[0]["args"], text)
    assert (act, extra["tab"], extra.get("connector")) == ("open", "conectores", cid)
    # the two channels are one decision: the probe's label IS the voice event
    assert _probe_action(text, calls) == f"panel:{extra['tab']}:{extra['connector']}"


def test_the_known_phrase_door_describes_and_emits_the_same_event():
    """The action map (a phrase that skips the model) is the third door and names the connector the same way."""
    from nucleo.actionmap import executor as AM
    action = {"do": "show_panel", "tab": "conectores", "connector": "gdrive"}
    assert AM.describe(action) == "panel:conectores:gdrive"
    got = []
    assert AM.execute(action, lambda k, a, text="", extra=None, **kw: got.append((k, a, extra or {})), "conecta mi drive")
    assert got and got[0][0] == "panel" and got[0][1] == "open"
    assert (got[0][2]["tab"], got[0][2]["connector"]) == ("conectores", "gdrive")


def test_without_a_connector_the_section_opens_on_its_list():
    calls = [{"name": "show_panel", "args": {"panel": "conectores"}}]
    assert _probe_action("abre los conectores", calls) == "panel:conectores"
    _act, extra = _voice_panel_emit(calls[0]["args"], "abre los conectores")
    assert extra["tab"] == "conectores" and "connector" not in extra


def test_closing_the_section_carries_no_connector():
    _act, extra = _voice_panel_emit({"panel": "conectores", "connector": "gdrive", "action": "close"}, "cierra eso")
    assert _act == "close" and "connector" not in extra


def test_disarmed_a_canon_that_names_nothing_leaves_both_channels_on_the_list(monkeypatch):
    """RED proof: with the canon returning '' both channels degrade to the bare list — the agreement test above is
    measuring the canon, not a constant. Restored in `finally`, never left disarmed."""
    calls = [{"name": "show_panel", "args": {"panel": "conectores", "connector": "Drive"}}]
    saved = (router._canon_connector, PD._canon_connector)
    try:
        router._canon_connector = lambda v: ""
        PD._canon_connector = lambda v: ""
        assert _probe_action("conecta mi Drive", calls) == "panel:conectores", "the probe did not read the canon"
        _act, extra = _voice_panel_emit(calls[0]["args"], "conecta mi Drive")
        assert "connector" not in extra, "the voice arm did not read the canon"
    finally:
        router._canon_connector, PD._canon_connector = saved
    assert _probe_action("conecta mi Drive", calls) == "panel:conectores:gdrive"   # green again


# ── 2. no widget keeps a connect door (ratchet) ───────────────────────────────────────────────────────────────

# The actions 6a39a053 removed — agenda/contactos/fotos `connect`+`disconnect`, archivos `open_connectors` /
# `close_connectors` / `connect_provider` / `disconnect_provider`, mensajeria `open_connectors`, contactos
# `show_connectors`, musica `connect`/`disconnect`. Anything whose NAME says connect is a door.
_DOOR_ACTION = re.compile(r"connect|conector", re.I)
_DOOR_ALIAS = re.compile(r"conect|connect|vincul|enlaz|link ", re.I)
# A handler is a door when it is NAMED after connecting, when it branches on `connect`, or when it calls a connector's
# login (`gcontacts.connect(`, `auth.begin_login(`). The agenda's `_a_connection` STAYED under its old name but routes
# only `set_default_calendar` — a picker, not a door — so the name alone is not what this looks for.
_DOOR_HANDLER = re.compile(r"def _a_(open_connectors|connect)\b|action == [\"']connect[\"']|[\"']open_connectors[\"']"
                           r"|gcontacts\.connect\(|auth\.begin_login\(")


def _widget_manifests() -> list[tuple[str, dict]]:
    out = []
    for f in sorted(WIDGETS.glob("*/manifest.json")):
        if f.parent.name.startswith("_"):
            continue                                   # `_user/` is the operator's, `_data/` is state
        out.append((f.parent.name, json.loads(f.read_text(encoding="utf-8"))))
    assert len(out) >= 12, "the builtin widgets are not where this ratchet looks"
    return out


def _doors_in(manifests) -> list[str]:
    """Every connect door a manifest still declares: an action named like one, an alias that is a connect order."""
    found = []
    for wid, m in manifests:
        for a in (m.get("actions") or {}):
            if _DOOR_ACTION.search(a):
                found.append(f"{wid}.actions.{a}")
        for al in (m.get("aliases") or []):
            if _DOOR_ALIAS.search(str(al)):
                found.append(f"{wid}.aliases «{al}»")
    return found


def test_no_widget_manifest_declares_a_connect_action_or_alias():
    doors = _doors_in(_widget_manifests())
    assert not doors, (f"a widget grew a connect door again: {doors}. Connecting a service is the ⚙ Conectores "
                       "section (show_panel panel='conectores' + connector), never a card's own action or alias.")


def test_no_widget_handler_implements_a_connection():
    hits = []
    for f in sorted(list(WIDGETS.glob("*/actions.py")) + list(WIDGETS.glob("*/data.py"))):
        if f.parent.name.startswith("_"):
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _DOOR_HANDLER.search(line):
                hits.append(f"{f.relative_to(ENGINE)}:{i}: {line.strip()[:80]}")
    assert not hits, f"a widget implements its own connection again: {hits}"


def test_the_prompt_sends_the_model_to_the_section_not_to_a_card_action():
    """The manifests that used to own a door now TELL the model where it went — a usage line that still says
    `open_connectors` would send it to an action that no longer exists."""
    for wid, m in _widget_manifests():
        prose = " ".join(str(m.get(k) or "") for k in ("usage", "whenToUse"))
        assert "open_connectors" not in prose, f"{wid}: usage still names the removed `open_connectors`"
        if wid in ("mensajeria", "archivos", "contactos", "fotos", "musica"):
            assert "conectores" in prose.lower(), f"{wid}: its usage no longer points at the Conectores section"


def test_disarmed_a_widget_declaring_connect_is_caught():
    """RED proof for the ratchet: a manifest that declares `connect`, `open_connectors` or a «conectar …» alias is
    named by the same function the green test runs over the disk."""
    fake = _widget_manifests() + [("agenda", {"actions": {"connect": {}, "add_meeting": {}}, "aliases": ["conectar calendario"]}),
                                  ("archivos", {"actions": {"open_connectors": {}}}),
                                  ("mensajeria", {"aliases": ["connect whatsapp"]})]
    doors = _doors_in(fake)
    assert set(doors) == {"agenda.actions.connect", "agenda.aliases «conectar calendario»",
                          "archivos.actions.open_connectors", "mensajeria.aliases «connect whatsapp»"}, doors
    assert not _doors_in(_widget_manifests())            # the real tree is clean, so the fake ones are what fired


def test_disarmed_a_handler_regex_sees_what_was_removed():
    removed = ["def _a_open_connectors(action, payload) -> dict:",
               '        return _d.gcontacts.connect(str(payload.get("tier") or ""), str(payload.get("origin") or ""))',
               "def _a_connect(action: str, p: dict) -> dict:", "        res = auth.begin_login()",
               '    if action == "connect":']
    for line in removed:
        assert _DOOR_HANDLER.search(line), line
    # …and does not accuse the handler that stayed: the agenda's default-calendar picker kept the old name and
    # routes only `set_default_calendar`.
    for kept in ("def _a_connection(action, payload, db, _extra) -> dict:", '    "set_default_calendar": _a_connection,',
                 '    if action != "set_default_calendar":'):
        assert not _DOOR_HANDLER.search(kept), kept


# ── 3. a browser «login» to Spotify / WhatsApp / Telegram / email goes to the section, never the browser ────────

def _auth(site, text):
    got, browser, esc = [], [], {"v": None}
    TEC._t_authenticate_web(args={"site": site}, _start_web_auth=lambda s: browser.append(s), escalate_req=esc, text=text,
                            emit=lambda kind, act, text="", extra=None, **kw: got.append((kind, act, extra or {})))
    return got, browser, esc


@pytest.mark.parametrize("site,text,cid", [
    ("spotify", "conéctame a mi cuenta de Spotify", "spotify"),
    ("spotify.com", "log me into Spotify", "spotify"),
    ("whatsapp", "conéctame WhatsApp", "whatsapp"),
    ("web.whatsapp.com", "open WhatsApp and log in", "whatsapp"),
    ("telegram", "vincula mi Telegram", "telegram"),
    ("gmail.com", "entra en mi Gmail", "email"),
    ("", "conéctame al correo", "email"),
])
def test_a_login_to_a_connected_service_opens_the_section_not_the_browser(site, text, cid):
    got, browser, esc = _auth(site, text)
    panels = [(a, x) for k, a, x in got if k == "panel"]
    assert panels == [("open", {"tab": "conectores", "src": "flash", "connector": cid})], got
    assert not browser, f"a browser login was started for {cid}: {browser}"
    assert esc["v"] is None, "the turn escalated to the browser worker instead"


def test_a_real_site_login_still_opens_the_browser():
    """The redirect is for the services the engine connects itself; Netflix is still a browser login."""
    got, browser, _esc = _auth("netflix.com", "abre la web de Netflix y me dices cuando esté en el login")
    assert browser == ["netflix.com"]
    assert not [1 for k, _a, _x in got if k == "panel"]


def test_disarmed_without_the_guard_spotify_would_open_a_browser(monkeypatch):
    """RED proof: with `web_auth.decide` no longer naming the service kind, the same call drives a browser to
    spotify.com — the redirect, not the tool description, is what keeps the invariant. Restored in `finally`."""
    saved = web_auth.decide
    try:
        web_auth.decide = lambda site, text: (web_auth.KIND_LOGIN, site or "spotify.com")
        got, browser, _esc = _auth("spotify", "conéctame a mi cuenta de Spotify")
        assert browser == ["spotify"], "the disarm did not reach the arm — the test measures nothing"
        assert not [1 for k, _a, _x in got if k == "panel"]
    finally:
        web_auth.decide = saved
    got, browser, _esc = _auth("spotify", "conéctame a mi cuenta de Spotify")
    assert not browser and [1 for k, _a, _x in got if k == "panel"]                # green again


def test_disarmed_a_canon_that_names_nothing_leaves_the_section_on_its_list(monkeypatch):
    """RED proof for the connector half: with the canon blind, WhatsApp reaches the section but not ITS guide."""
    saved = CC.canon_connector
    try:
        CC.canon_connector = lambda v: ""
        got, browser, _esc = _auth("whatsapp", "conéctame WhatsApp")
        panels = [x for k, _a, x in got if k == "panel"]
        assert panels and "connector" not in panels[0], panels
        assert not browser                                                          # the redirect itself holds
    finally:
        CC.canon_connector = saved
    got, _b, _e = _auth("whatsapp", "conéctame WhatsApp")
    assert [x for k, _a, x in got if k == "panel"][0]["connector"] == "whatsapp"


def test_the_decision_is_still_shared_with_the_text_channel():
    """The voice arm reads `web_auth.decide`, the probe's `authenticate_web` branch reads the same — the two channels
    cannot drift on WHICH services are redirected (V2-176)."""
    import inspect
    assert "web_auth" in inspect.getsource(TEC._t_authenticate_web) and ".decide(" in inspect.getsource(TEC._t_authenticate_web)
    assert "connector_canon" in inspect.getsource(TEC._t_authenticate_web), "the arm no longer names the connector"
    for site, text, kind in [("spotify", "conéctame a Spotify", web_auth.KIND_MUSIC),
                             ("telegram", "vincula mi Telegram", web_auth.KIND_MESSAGING),
                             ("gmail.com", "conéctame a mi Gmail", web_auth.KIND_MESSAGING)]:
        assert web_auth.decide(site, text)[0] == kind
