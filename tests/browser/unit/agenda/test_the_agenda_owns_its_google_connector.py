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
# So the voice does the half it CAN do: it puts the button in front of him, and the manifest tells the
# model which sentence to say. He grants the permission himself, with his own account, in his own browser.
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
MANIFEST = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real agenda."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    return ag


# -- 1. routing: the agenda claims its own connector, in both languages ----------------------------------

# The operator's own phrasings, Castilian and English. One is NOT a translation of the other: the table
# GROWS. An English phrase that displaced its Castilian equivalent would fix one language by breaking the
# other, which is the standing rule.
_ASKS = [("es", "conecta mi google calendar"),
         ("es", "vincula la agenda con google calendar"),
         ("es", "abre el conector de google de la agenda"),
         ("en", "connect google calendar"),
         ("en", "link my calendar with google"),
         ("en", "open the google connector in the agenda widget")]

# The agenda's words that speak of LINKING (not of planning a day). Derived from the manifest instead of
# repeated here: a copied list goes stale the day somebody adds a keyword and forgets the copy.
_LINKING = [k for k in MANIFEST["keywords"]
            if any(w in k for w in ("conect", "connect", "calendar", "vincul", "sincroniz", "sync"))]


@pytest.mark.parametrize("lang,phrase", _ASKS)
def test_the_row_the_model_READS_says_the_agenda_owns_the_connector(lang, phrase):
    """T12's exact cause, asserted against the exact artifact: the row `widgets/brief.for_prompt` puts in
    the turn prompt. Not against the manifest — that is the source — and not against `selection`'s ranking,
    which admits all fifteen widgets today and therefore decided nothing here."""
    from widgets import brief
    rows = [r for r in brief.for_prompt([], [], query=phrase).splitlines() if r.startswith("- agenda ")]
    assert len(rows) == 1, f"[{lang}] the agenda is not in the prompt for «{phrase}»"
    row = rows[0].lower()
    assert "google calendar" in row, f"[{lang}] its row does not name the calendar: {row[:200]}"
    assert "conect" in row, f"[{lang}] its row does not say that IT connects it"
    assert "connect" in row.split("datos:")[-1], "connect is missing from its action list"


@pytest.mark.parametrize("lang,phrase", _ASKS)
def test_every_way_he_asked_it_touches_a_word_the_agenda_claims(lang, phrase):
    """The other half, the one that holds once the catalog grows. Today all fifteen widgets fit in the
    prompt and selection filters nothing; with a hundred it will filter, and then the agenda only gets in
    if one of ITS words is in the sentence. A LINKING word is required, not a bare «agenda»: if naming the
    widget were enough, T14 — which named it — would not have been necessary."""
    low = phrase.lower()
    hit = [k for k in _LINKING if k in low]
    assert hit, f"[{lang}] «{phrase}» touches none of the agenda's linking words: {_LINKING}"


def test_the_calendar_is_named_by_the_agenda_and_by_NOBODY_else():
    """The frontier. Messaging stays the owner of «connect a channel» — WhatsApp, Telegram, email, which is
    its job; what it may not do is also take the calendar, which is what it did."""
    from widgets import brief
    rows = [r for r in brief.for_prompt([], [], query="connect google calendar").splitlines()
            if r.startswith("- ") and "google calendar" in r.lower()]
    assert len(rows) == 1 and rows[0].startswith("- agenda "), rows


@pytest.mark.parametrize("concept,words", [
    ("calendario (es)", ("calendario",)),
    ("calendar (en)", ("calendar",)),
    ("conectar (es)", ("conectar calendario", "conectar google calendar", "vincular google calendar")),
    ("connect (en)", ("connect calendar", "connect google calendar")),
    ("the connector, by name", ("conector de google", "google connector")),
])
def test_both_languages_carry_the_same_concepts(concept, words):
    """The operator's standing rule: valid for English, for Spanish or for any language — and never fixing
    one at the other's expense. Both lost attempts of 2026-09-14 were in ENGLISH, against a widget whose
    twenty-one keywords were Castilian except for two («schedule», «my day»)."""
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


# -- 2. the sentence: an undeclared capability gets NARRATED (or, here, gets no words at all) ------------

def test_connect_tells_the_model_to_hand_off_to_the_click():
    """T14 in one line. The model cannot authorize, does not receive the URL and has nothing to say — unless
    the manifest tells it, because the manifest DOES travel in the prompt."""
    desc = MANIFEST["actions"]["connect"]["desc"].lower()
    assert "conectar" in desc
    assert "pulse" in desc or "pulsa" in desc, "it never says the click belongs to the operator"
    assert "url" in desc, "it never forbids dictating the URL, which is all the action returns"


def test_the_action_is_declared_exactly_once_and_handled():
    """The gate already requires this of every action; it is anchored here because THIS one is called from
    two places (the card's button and the voice) and one of the two is easy to lose."""
    assert "connect" in MANIFEST["actions"]
    assert "connect" not in (MANIFEST["actions"]["connect"].get("payload") or {})


# -- 3. the push: the card stays ON the step that holds the button ---------------------------------------

def test_connect_leaves_the_card_on_its_connect_step(agenda):
    from widgets.agenda import gcal
    agenda.apply_action("connect", {})
    from widgets import store
    db = store.load(agenda.WIDGET_ID)
    assert gcal.fresh_connect(db), "the voice ran connect and the card did not move"
    assert agenda.view_data()["connect"], "the push never reaches the render"


def test_asking_TWICE_lands_twice(agenda):
    """The token is a COUNTER, not a boolean: if he asks again because the window closed on him the first
    time, the card has to jump again. A flag would stay true and move nothing."""
    from widgets import store
    agenda.apply_action("connect", {})
    first = store.load(agenda.WIDGET_ID)["connect"]["n"]
    agenda.apply_action("connect", {})
    assert store.load(agenda.WIDGET_ID)["connect"]["n"] == first + 1


def test_a_stale_order_does_not_ambush_him_later(agenda):
    """The token's other half: an old `at` expires. Without it, the card would open its connect screen on
    the first repaint tomorrow morning, on top of the agenda he was reading."""
    from widgets import store
    from widgets.agenda import gcal
    agenda.apply_action("connect", {})
    db = store.load(agenda.WIDGET_ID)
    db["connect"]["at"] = db["connect"]["at"] - (gcal._CONNECT_TTL_S + 1)
    assert gcal.fresh_connect(db) is None


def test_disconnect_does_not_push_anyone_to_a_connect_screen(agenda):
    """Counterweight. `connect` and `disconnect` enter through the SAME `apply_action` branch; if the push
    lived in the branch instead of in the action, disconnecting would open the connect screen."""
    from widgets import store
    from widgets.agenda import gcal
    agenda.apply_action("disconnect", {})
    assert gcal.fresh_connect(store.load(agenda.WIDGET_ID)) is None


def test_the_screen_moves_even_when_the_connector_REFUSES(agenda, monkeypatch):
    """A failure has to be visible. If the push depended on the URL coming out well, the case that needs a
    screen MOST — no OAuth app registered — would be precisely the one without one."""
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)
    db: dict = {}
    res = gcal.ui_action("connect", {}, db)
    assert res and res.get("ok") is False
    assert gcal.fresh_connect(db), "the refusal was left with no screen to tell itself on"


# -- 4. and the connector itself still opens a usable door ----------------------------------------------

def test_the_consent_door_is_real_without_printing_what_is_behind_it():
    """What the operator will use tomorrow with his own account. The SHAPE is asserted — this repo is public
    and one of its reports leaked personal data once: no client_id, no state, no tokens."""
    from widgets.agenda import gcal
    r = gcal.ui_action("connect", {}, {})
    if not (r or {}).get("ok"):
        pytest.skip("no Google OAuth client on this machine: " + str((r or {}).get("error")))
    url = str(r["url"])
    assert url.startswith("https://accounts.google.com/")
    for must in ("code_challenge_method=S256", "access_type=offline", "%2Fapi%2Fcalendar%2Fcallback"):
        assert must in url, must
