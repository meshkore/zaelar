"""V2-718 — the operator's own criterion for act-or-ask, made mechanical.

> «Imagínate que te dice: vamos a hacer la reunión presencial, o ¿por qué no invitas a otra persona? Hay
> cosas que van a necesitar permiso y otras cosas que no. Esto por ejemplo que no nos hace ningún daño no
> necesita permiso. Añadir a otra persona, cambiar de hora o hacer otras cosas sí que obviamente necesitan
> permiso, y creo que nuestro sistema ya debería tener los prompts o herramientas suficientes como para
> identificar qué cosas necesitan permiso y qué no.»

The rule that decides act-or-ask already exists and is declared data (V2-712, `nucleo/consent.py`). What it
could not do is tell these two apart, because the difference is not in the verb, not in the payload keys and
not in the wording of the request: it is whether THIS call stays inside a commitment already made with the
people already in it. Only the widget holding the guest list can answer that, so a widget may now say so
(`consent_scope`), and the answer is a genesis CLASS the operator can flip by speaking.

Every input here is data somebody else measured: the meeting's own guest list, the directory, and what the
other party WROTE TO US. Nothing reads intent.
"""
import pytest

from nucleo import consent
from nucleo.flash import frontend
from widgets.agenda import data as ad


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """⚠️ The store is not the only live artifact on this path. `consent.set_class` PERSISTS — that is the
    whole point of it, the operator's answer becoming the default the next decision reads — and it writes to
    `<workspace>/config/consent.json`, which on a developer's machine is the operator's REAL standing rules.
    The first run of this file wrote two calendar classes into his own config and had to be undone by hand.
    A unit test never touches live artifacts: the overrides file lives in tmp here."""
    import widgets.store as store
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    yield
    consent._reset_for_tests()


_MEETING = {"title": "Meeting with Ivan Mikushin", "date": "2026-09-17", "startTime": "22:00",
            "endTime": "23:00", "source": "google", "googleId": "ev1", "googleCalendarId": "primary",
            "meetLink": "https://meet.google.com/ydi-zeaz-tri"}
_IVAN = {"id": "c1", "kind": "person", "name": "Ivan Mikushin", "email": "", "emails": [],
         "channels": [{"platform": "telegram", "handle": "@imikushin", "chatId": "21045673"}]}


def _world(monkeypatch, *, meeting=None, contacts=(_IVAN,), said=("can you send me a calendar invite to: "
                                                                  "ivan@charms.dev",)):
    """The three pieces of data the criterion reads, and nothing else."""
    import widgets.store as store
    db = ad.load_db()
    db["meetings"] = [dict(meeting or _MEETING)]
    store.save(ad.WIDGET_ID, db)
    from widgets import directory
    monkeypatch.setattr(directory, "_contacts", lambda: [dict(c) for c in contacts])
    from connectors.messaging import archive
    monkeypatch.setattr(archive, "search",
                        lambda *a, **k: [{"body": s, "sender": "Ivan Mikushin"} for s in said])


def _verdict(payload, action="invite"):
    return frontend.action_verdict("agenda", action, payload)


# ── what does NOT need permission ─────────────────────────────────────────────────────────────────────────

def test_sending_the_invitation_to_the_address_he_gave_us_just_happens(monkeypatch):
    """«Esto no nos hace ningún daño»: the meeting was agreed WITH this person, and the address is the one
    they typed into the conversation themselves."""
    _world(monkeypatch)
    assert ad.consent_scope("invite", {"who": "ivan@charms.dev"})["class"] == "calendar.invite_agreed"
    assert _verdict({"who": "ivan@charms.dev"})["verdict"] == consent.RUN


def test_moving_an_hour_only_he_is_holding_just_happens(monkeypatch):
    """⚠️ The VERDICT, not the hook's answer. The first version of this test asserted `consent_scope == {}`
    and passed while every move asked, his dentist included: the manifest declared the «ask» class and
    `_policy_key` falls back to the declared class whenever the hook says nothing. A class declared in the
    manifest is a floor the hook cannot lower — so an action that is free by default declares none."""
    _world(monkeypatch, meeting={"title": "Dentist", "date": "2026-09-17", "startTime": "17:00"})
    assert ad.consent_scope("move_meeting", {"title": "Dentist"}) == {}
    assert _verdict({"title": "Dentist", "newTime": "10:00"}, action="move_meeting")["verdict"] == consent.RUN


def test_with_no_meeting_named_the_invitation_goes_to_the_next_one_ahead_never_to_a_holiday(monkeypatch):
    """Measured on the operator's real agenda: «the last meeting» was a public holiday in 2027. Birthdays and
    holidays live years out as all-day entries, and an invitation to one of those is the wrong action."""
    import datetime as _dt
    import widgets.store as store
    from widgets.agenda import invite
    today = _dt.date.today()
    later = (today + _dt.timedelta(days=3)).isoformat()
    _world(monkeypatch)
    db = ad.load_db()
    db["meetings"] = [
        {"title": "Día de la Hispanidad", "date": f"{today.year + 1}-10-12", "allDay": True},
        {"title": "Dentist", "date": (today - _dt.timedelta(days=1)).isoformat(), "startTime": "17:00",
         "endTime": "18:00"},
        {"title": "Meeting with Ivan Mikushin", "date": later, "startTime": "22:00", "endTime": "23:00"},
        {"title": "Comité", "date": (today + _dt.timedelta(days=9)).isoformat(), "startTime": "09:00"},
    ]
    store.save(ad.WIDGET_ID, db)
    picked = invite.find_meeting(ad.load_db(), {})
    assert picked and picked["title"] == "Meeting with Ivan Mikushin", picked
    # Naming it still wins, and a spoken date resolves the way the agenda resolves it.
    assert invite.find_meeting(ad.load_db(), {"meeting": "Comité"})["title"] == "Comité"
    assert invite.find_meeting(ad.load_db(), {"meeting": "nope"}) is None


# ── what DOES need permission ─────────────────────────────────────────────────────────────────────────────

def test_putting_a_THIRD_person_in_the_room_asks(monkeypatch):
    _world(monkeypatch)
    assert ad.consent_scope("invite", {"who": "otro@example.com"})["class"] == "calendar.invite_new_party"
    v = _verdict({"who": "otro@example.com"})
    assert v["verdict"] == consent.ASK_CONSENT and "invite_new_party" in v["why"]


def test_moving_an_hour_somebody_else_agreed_asks(monkeypatch):
    _world(monkeypatch)
    assert ad.consent_scope("move_meeting", {"meeting": "Meeting with Ivan"})["class"] == \
        "calendar.reschedule_committed"
    # Nothing named → the hook says NOTHING. The move half reads the same lookup the action performs (a
    # title is required), never the invitation's «next meeting ahead» fallback: otherwise «muévela» with no
    # title would be answered with «hay alguien más contando con esa hora» about a meeting he never named.
    assert ad.consent_scope("move_meeting", {"newTime": "10:00"}) == {}


def test_an_address_nobody_ever_gave_us_is_a_stranger_even_with_the_right_name(monkeypatch):
    """The name in the title is not the credential — the ADDRESS is. «ivan@» at some other domain is
    somebody we have never heard from, and sending them his meeting is the harm this question exists for."""
    _world(monkeypatch)
    assert ad.consent_scope("invite", {"who": "ivan@somewhere-else.com"})["class"] == \
        "calendar.invite_new_party"


def test_two_contacts_with_the_same_name_are_DOUBT_not_membership(monkeypatch):
    """Walking the directory for any name that is a substring of the title is how a meeting «with Ivan
    Mikushin» quietly adopted a different contact called just «Ivan». Doubt is not membership."""
    other = {"id": "c2", "kind": "person", "name": "Ivan", "email": "ivan@citingart.com", "emails": []}
    _world(monkeypatch, contacts=(_IVAN, other))
    assert ad.consent_scope("invite", {"who": "ivan@citingart.com"})["class"] == "calendar.invite_new_party"


# ── the rule stays the operator's, not the code's ─────────────────────────────────────────────────────────

def test_the_operator_can_flip_either_of_these_by_saying_so(monkeypatch):
    """Nothing here is hardcoded: the two classes are genesis DATA, layered exactly like `style_policy`."""
    _world(monkeypatch)
    assert _verdict({"who": "otro@example.com"})["verdict"] == consent.ASK_CONSENT
    consent.set_class("calendar.invite_new_party", "allow")
    assert _verdict({"who": "otro@example.com"})["verdict"] == consent.RUN
    consent.set_class("calendar.invite_agreed", "ask")
    assert _verdict({"who": "ivan@charms.dev"})["verdict"] == consent.ASK_CONSENT


def test_a_widget_that_says_nothing_keeps_the_class_its_manifest_declares(monkeypatch):
    """The hook REFINES; it never invents. A widget with no `consent_scope`, or one that raises, has to
    behave exactly as it did before this seam existed."""
    _world(monkeypatch)
    monkeypatch.delattr(ad, "consent_scope")
    v = _verdict({"who": "ivan@charms.dev"})
    assert v["verdict"] == consent.ASK_CONSENT, "falls back to the manifest's own class, which asks"
    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ad, "consent_scope", _boom, raising=False)
    assert _verdict({"who": "ivan@charms.dev"})["verdict"] == consent.ASK_CONSENT


def test_the_invitation_is_a_declared_action_so_the_voice_can_ask_for_it():
    """A capability the model cannot see is a capability nobody has (the V2-548 rule)."""
    from widgets import runtime
    spec = ((runtime.get("agenda") or {}).get("actions") or {}).get("invite")
    assert spec, "the agenda has to DECLARE the verb or no sentence can reach it"
    assert "who" in (spec.get("payload") or {})
    assert spec.get("confirm_q"), "when it does ask, it has to have a sentence he can hear"
