"""V2-697 — the appointment card, RENDERED.

The operator opened the detail card for a real invitation — an intro somebody at zerohash convened — and put
it beside Google's own popover for the same event. Ours showed a title, a date, one bare address and a chip
reading «Confirmed». Google's showed the Meet link, both guests with their answers, who organized it, and
buttons to say whether he was going.

His priorities, verbatim: «sobre todo el enlace, el enlace a Google Meet, que es lo que más me importa, y
nosotros no exponemos eso» · «quién me ha convocado. Porque a veces nosotros somos los que insertamos el
ítem en la agenda, pero a veces es una invitación externa que nosotros aceptamos» · «yo por ahora no haría
la funcionalidad de proponer otra hora, pero sí diría si sí o si no». And what he did NOT want: the phone
bridge, the PIN, «more phone numbers» — «cosas que yo considero que son extras y absurdas».

RENDERED rather than read, because the defect was never in the connector — it captured all of this from the
first import. It was that `eventsOf` did not COPY the fields into the object the card reads, which a source
scan cannot see: the connector's code and the card's code were each individually correct.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _d(n: int = 0) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


def _days(n: int = 7):
    return [{"date": _d(i), "label": "X", "weekday": "X",
             "plan": {"blocks": [], "focus": [], "summary": "", "coaching": [], "warnings": []}}
            for i in range(n)]


def _data(**over):
    d = {"date": _d(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
         "active": None, "days": _days(), "todayIndex": 0, "meetings": [], "projects": [],
         "view": None, "calendars": [], "warnings": [], "coaching": [], "proposals": []}
    d.update(over)
    return d


#: The operator's own event, as the connector stores it after V2-697.
def _invitation(**over):
    m = {"title": "Gavin/Ricart zerohash blockchain intro", "date": _d(), "startTime": "15:00",
         "endTime": "15:30", "source": "google", "googleId": "ev1", "googleCalendarId": "primary",
         "attendees": ["Gavin Hayes"],
         "guests": [{"name": "Gavin Hayes", "email": "gavin.hayes@zerohash.com",
                     "rsvp": "accepted", "organizer": True}],
         "organizer": "Gavin Hayes", "selfEmail": "me@x.com", "myRsvp": "needsAction",
         "meetLink": "https://meet.google.com/cgh-pouq-gje", "status": "confirmed"}
    m.update(over)
    return m


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 800})
            page._hb_url = f"http://127.0.0.1:{port}/widgets/agenda/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/agenda/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data):
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:920px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve({ok: true}); },
                              top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


def _open_detail(page, meeting):
    """Open the card the operator screenshotted: the day view, then the chip."""
    _mount(page, _data(meetings=[meeting]))
    page.locator(".agtab[data-view='day']").click()
    page.locator(".agev").first.click()
    page.wait_for_selector(".agpanel")


# ── what he said mattered most ──────────────────────────────────────────────────────────────────────────

def test_the_card_offers_the_google_meet_link(_page):
    _open_detail(_page, _invitation())
    link = _page.locator(".agpmeet")
    assert link.count() == 1, "the join link is the thing he asked for first"
    assert link.get_attribute("href") == "https://meet.google.com/cgh-pouq-gje"
    assert link.get_attribute("target") == "_blank"
    assert "noopener" in (link.get_attribute("rel") or "")


def test_a_join_link_that_is_not_http_is_never_turned_into_a_link(_page):
    """A row stored before the connector's own guard existed is still on disk, and this is the line that
    becomes an href — so the sink refuses it a second time."""
    _open_detail(_page, _invitation(meetLink="javascript:alert(1)"))
    assert _page.locator(".agpmeet").count() == 0


def test_the_card_never_offers_a_phone_bridge_or_a_pin(_page):
    _open_detail(_page, _invitation())
    body = _page.locator(".agpanel").inner_text()
    for junk in ("Join by phone", "PIN", "More phone numbers", "+34"):
        assert junk not in body, f"«{junk}» is exactly what he called an absurd extra"


def test_an_external_invitation_says_WHO_convened_it(_page):
    _open_detail(_page, _invitation())
    assert "Gavin Hayes" in _page.locator(".agpanel").inner_text()
    rows = _page.locator(".agprow").all_inner_texts()
    assert any("Gavin Hayes" in r and ("invit" in r.lower()) for r in rows), \
        "«a veces es una invitación externa» — the card has to say so"


def test_an_appointment_WE_created_does_not_name_an_organizer(_page):
    """The counterweight: the connector omits `organizer` when it is ours, and a card about your own
    appointment must not name you as the person who invited you."""
    _open_detail(_page, _invitation(organizer="", myRsvp="", guests=[], attendees=["Marta"]))
    rows = _page.locator(".agprow").all_inner_texts()
    assert not any("invit" in r.lower() for r in rows)


def test_each_guest_is_listed_with_the_answer_they_gave(_page):
    _open_detail(_page, _invitation(guests=[
        {"name": "Gavin Hayes", "email": "g@z.com", "rsvp": "accepted", "organizer": True},
        {"name": "Marta", "email": "m@z.com", "rsvp": "declined"},
        {"name": "Luis", "email": "l@z.com"},
    ]))
    names = _page.locator(".agpgn").all_inner_texts()
    assert names == ["Gavin Hayes", "Marta", "Luis"]
    marks = _page.locator(".agpgm").evaluate_all("els => els.map(e => e.className)")
    assert marks == ["agpgm accepted", "agpgm declined", "agpgm unknown"], \
        "an answer Google did not report reads as unknown, never as a yes"
    assert _page.locator(".agpgo").count() == 1                 # only the organizer is marked as one


# ── the chip that used to lie ───────────────────────────────────────────────────────────────────────────

def test_your_own_answer_and_theirs_are_two_separate_statements(_page):
    """The card showed «Confirmed» over an invitation he had merely been sent, because `status` carried HIS
    responseStatus under a label about the other party."""
    _open_detail(_page, _invitation())                          # he has NOT answered; Gavin has accepted
    chips = _page.locator(".agpstate").all_inner_texts()
    assert len(chips) == 2, "his answer and theirs are two facts, not one"
    joined = " · ".join(chips).lower()
    assert "no has respondido" in joined
    assert "1 de 1" in joined


def test_once_he_accepts_the_chip_says_HE_is_going(_page):
    _open_detail(_page, _invitation(myRsvp="accepted"))
    assert "vas a ir" in _page.locator(".agpstate").first.inner_text().lower()


# ── saying yes or no ────────────────────────────────────────────────────────────────────────────────────

def test_an_invitation_offers_yes_and_no_and_nothing_else(_page):
    _open_detail(_page, _invitation())
    labels = " · ".join(_page.locator(".agpacts button").all_inner_texts()).lower()
    assert "sí, voy" in labels and "no puedo ir" in labels
    for absent in ("otra hora", "propon", "quizá"):
        assert absent not in labels, "he scoped this to yes/no on purpose"


def test_saying_yes_travels_as_an_rsvp_and_not_as_a_local_note(_page):
    _open_detail(_page, _invitation())
    _page.locator(".agpacts button", has_text="Sí, voy").click()
    calls = _page.evaluate("window.__calls")
    assert calls and calls[0][0] == "rsvp_meeting", \
        "update_meeting is a note he takes about THEM; this one has to reach the organizer"
    assert calls[0][1]["answer"] == "accepted"


def test_the_answer_he_already_gave_is_not_offered_again(_page):
    _open_detail(_page, _invitation(myRsvp="declined"))
    labels = " · ".join(_page.locator(".agpacts button").all_inner_texts()).lower()
    assert "no puedo ir" not in labels and "sí, voy" in labels


def test_an_appointment_nobody_invited_him_to_offers_no_rsvp(_page):
    """There is no response status to set on a meeting he dictated — offering one would promise a message
    to an organizer who does not exist."""
    _open_detail(_page, _invitation(organizer="", myRsvp="", guests=[], attendees=["Marta"]))
    labels = " · ".join(_page.locator(".agpacts button").all_inner_texts()).lower()
    assert "sí, voy" not in labels and "no puedo ir" not in labels


# ── a proposal is a QUESTION, not an entry ──────────────────────────────────────────────────────────────

_PROPOSAL = {"errand_id": "e1", "party": "Gavin Hayes", "objective": "una intro de blockchain",
             "date": _d(1), "startTime": "15:00", "endTime": "15:30", "at": f"{_d(1)} 15:00",
             "asked_at": 1}


def test_a_proposal_is_shown_apart_from_the_calendar_with_who_and_when(_page):
    _mount(_page, _data(proposals=[_PROPOSAL]))
    band = _page.locator(".agprop")
    assert band.count() == 1
    text = band.inner_text()
    assert "Gavin Hayes" in text and "15:00" in text and "una intro de blockchain" in text
    # It is NOT on the calendar, so it must not be painted as an appointment on it.
    assert _page.locator(".agev").count() == 0


def test_a_proposal_is_never_accepted_without_him(_page):
    _mount(_page, _data(proposals=[_PROPOSAL]))
    assert _page.evaluate("window.__calls") == [], "nothing may be accepted by merely rendering the card"
    _page.locator(".agpropacts button", has_text="Aceptar").click()
    calls = _page.evaluate("window.__calls")
    assert calls == [["accept_proposal", {"errand_id": "e1"}]]


def test_declining_a_proposal_asks_for_exactly_that(_page):
    _mount(_page, _data(proposals=[_PROPOSAL]))
    _page.locator(".agpropacts button", has_text="Rechazar").click()
    assert _page.evaluate("window.__calls") == [["decline_proposal", {"errand_id": "e1"}]]


def test_with_no_proposals_the_band_does_not_exist(_page):
    _mount(_page, _data())
    assert _page.locator(".agprops").count() == 0
