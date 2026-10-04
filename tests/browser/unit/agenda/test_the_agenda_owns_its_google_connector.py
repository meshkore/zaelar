# V2-686 — «connect my Google Calendar» has to arrive SOMEWHERE.
#
# Measured live on 2026-09-14, two attempts by the operator, both in English, both lost:
#
#   T12·9e60  «open the google connector»
#             -> the model opened MESSAGING and answered «I'm opening the Messaging widget — the Google
#                connector is right there with the login steps». It did not hallucinate: of the fifteen
#                widgets in that turn's prompt, the only purpose line that mentioned connecting was
#                messaging's («…o conectar un canal»), and the agenda's said nothing about connecting,
#                nothing about Google and nothing about a calendar. It routed with what it had.
#
#   T14·76b6  «open the google connector in the agenda wwidget»
#             -> naming the widget DID get there: `widget_data agenda:connect`, allowed, executed, and the
#                action returned a perfectly good consent URL. And NOTHING happened: the screen did not
#                move and the mouth did not say a word (`completion_chars: 0`).
#
# The second one is the interesting half, because the fault is NOT in the connector — it is in the last
# metre. Two links cut it, and neither is a bug that shows up in a log:
#
#   1. The turn report keeps `{widget, act}` and THROWS AWAY the action's result
#      (`nucleo/flash/widget_data_turn.py`), so the URL cannot reach the model and never could.
#   2. Even if it did, the voice cannot finish an OAuth consent: the popup only survives inside the click
#      that opened it — already paid for and written down in `widget.js`, V2-679's «ni siquiera funciona».
#
# So the voice does the half it CAN do: it puts the button in front of him. He grants the permission himself,
# with his own account, in his own browser.
#
# 2026-10-04 — the button moved. The agenda's own `connect` action and its in-card wizard were removed with
# every other widget's connect screen: there is ONE door, the ⚙ «Conectores» section opened on that connector
# (`show_panel(panel='conectores', connector=…)`, canon in `nucleo/flash/connector_canon.py`). What this file
# pins is the same property on the new door: every phrase of 2026-09-14 names the Google calendar connector,
# the agenda's routing row still claims the calendar (so the catalog never sends it to messaging again), no
# widget declares a connect action of its own, and the consent door the section opens is real.
from __future__ import annotations

import json
import pathlib

import pytest

from nucleo.flash.connector_canon import canon_connector

ENGINE = pathlib.Path(__file__).resolve().parents[4]
MANIFEST = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))

#: The one Google connector as the section shows it: the calendar service, or the Google account it belongs
#: to when the phrase names Google without naming the calendar (`ConnectorWizard.focusOf` opens the same entry).
_GOOGLE = {"google", "google-account"}


# -- 1. routing: every way he asked lands on the Google connector ------------------------------------------

# The operator's own phrasings, Castilian and English. One is NOT a translation of the other: the table
# GROWS. An English phrase that displaced its Castilian equivalent would fix one language by breaking the
# other, which is the standing rule.
_ASKS = [("es", "conecta mi google calendar"),
         ("es", "vincula la agenda con google calendar"),
         ("es", "abre el conector de google de la agenda"),
         ("en", "connect google calendar"),
         ("en", "link my calendar with google"),
         ("en", "open the google connector in the agenda widget")]


@pytest.mark.parametrize("lang,phrase", _ASKS)
def test_every_way_he_asked_it_names_the_google_connector(lang, phrase):
    """T12 and T14, on the new door: the argument the model hands `show_panel` is the phrase or a word of it,
    and the canon has to answer with the Google connector — never '' (the bare list) and never another one."""
    assert canon_connector(phrase) in _GOOGLE, f"[{lang}] «{phrase}» does not reach the Google connector"


@pytest.mark.parametrize("word", ["google calendar", "calendario", "calendar", "google"])
def test_the_words_the_model_is_likeliest_to_pass_resolve_too(word):
    assert canon_connector(word) in _GOOGLE


def test_the_row_the_model_READS_still_says_the_calendar_is_the_agendas():
    """T12's exact cause: of fifteen purpose lines, only messaging's mentioned connecting, so the model took
    «open the google connector» to messaging. The agenda's row keeps naming Google Calendar as ITS connector,
    in the artifact the turn prompt carries (`widgets/brief.for_prompt`), not just in the manifest."""
    from widgets import brief
    rows = [r for r in brief.for_prompt([], [], query="connect google calendar").splitlines()
            if r.startswith("- agenda ")]
    assert len(rows) == 1, "the agenda is not in the prompt"
    low = rows[0].lower()
    assert "google calendar" in low and "conect" in low
    assert "connect" not in low.split("datos:")[-1], "and it declares no connect action of its own any more"


def test_the_calendar_is_named_by_the_agenda_and_by_NOBODY_else():
    """The frontier. Messaging keeps its channels — WhatsApp, Telegram, email, which is its job; what it may
    not do is also take the calendar, which is what it did."""
    from widgets import brief
    rows = [r for r in brief.for_prompt([], [], query="connect google calendar").splitlines()
            if r.startswith("- ") and "google calendar" in r.lower()]
    assert len(rows) == 1 and rows[0].startswith("- agenda "), rows


@pytest.mark.parametrize("concept,words", [
    ("calendario (es)", ("calendario",)),
    ("calendar (en)", ("calendar",)),
    ("google calendar, by name", ("google calendar",)),
])
def test_both_languages_carry_the_same_concepts(concept, words):
    """The operator's standing rule: valid for English, for Spanish or for any language — and never fixing
    one at the other's expense. Both lost attempts of 2026-09-14 were in ENGLISH, against a widget whose
    twenty-one keywords were Castilian except for two («schedule», «my day»). The «conectar …» keywords
    left with the action: connecting is routed by the connector canon, not by the agenda's keywords."""
    kws = set(MANIFEST["keywords"])
    assert kws & set(words), f"missing «{concept}»: none of {words}"


def test_the_routing_line_names_the_connector_and_SURVIVES_the_cap():
    """The workflow's T4 trap: `whenToUse` has a 300-character budget and what gets cut is the END — exactly
    where the frontier clause goes. Here the frontier IS the new sentence («the agenda, not messaging»), so
    it is asserted against `brief._purpose`, which is what the prompt actually carries."""
    from widgets import brief
    purpose = brief._purpose(MANIFEST["whenToUse"])
    assert purpose == MANIFEST["whenToUse"], "the routing line is being truncated"
    low = purpose.lower()
    assert "google calendar" in low and "conect" in low
    assert "mensajería" in low, "the frontier with messaging is the half that resolved T12"


# -- 2. no widget connects anything: ONE door --------------------------------------------------------------

def test_no_widget_declares_a_connect_action_of_its_own():
    """Two plausible destinations is how «conecta mi Drive» got routed by luck; the canon is the only router."""
    offenders = []
    for mf in sorted((ENGINE / "widgets").glob("*/manifest.json")):
        acts = set(json.loads(mf.read_text(encoding="utf-8")).get("actions") or {})
        hit = acts & {"connect", "disconnect", "open_connectors", "show_connectors", "disconnect_provider"}
        if hit:
            offenders.append(f"{mf.parent.name}: {sorted(hit)}")
    assert not offenders, offenders


def test_the_agenda_keeps_only_its_own_calendar_preference():
    """What stays on the card is a PREFERENCE (which Google calendar new appointments go to), not a connection."""
    assert "set_default_calendar" in MANIFEST["actions"]
    assert not {"connect", "disconnect"} & set(MANIFEST["actions"])


# -- 3. and the connector itself still opens a usable door -----------------------------------------------

def test_the_consent_door_is_real_without_printing_what_is_behind_it(monkeypatch):
    """What the operator will use tomorrow with his own account, through the section's `/api/calendar/connect`
    (`connectors/calendar/service.connect_url`). The SHAPE is asserted — this repo is public and one of its
    reports leaked personal data once: no client_id, no state, no tokens."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")   # V2-778 F0: declared
    svc = pytest.importorskip("connectors.calendar.service")
    r = svc.connect_url("google", "")
    assert (r or {}).get("ok"), f"a declared client must open the door: {(r or {}).get('error')}"
    url = str(r["url"])
    assert url.startswith("https://accounts.google.com/")
    for must in ("code_challenge_method=S256", "access_type=offline", "%2Fapi%2Fcalendar%2Fcallback"):
        assert must in url, must
