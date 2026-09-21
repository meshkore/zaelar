"""V2-744 — RENDERED: the agenda card carries two sections, and the tasks one is numbered.

The operator asked for a selector «arriba del todo que separe lo que es agenda de tareas», for lists with
their progress, and for numbers he can speak. Whether a selector exists, whether choosing TAREAS actually
replaces the calendar, whether the numeral is on the row and whether a click reaches the widget's declared
action are questions only a real render answers — a computed style is not a painted pixel (V2-690), and a
DOM built by a harness that differs from the product measures a different product (V2-608).

So this mounts the REAL `widget.js` in Chromium against the shape `view_data()` actually returns, and
drives it with clicks.
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


def _tasks(**over):
    """The shape `tasklists.view()` returns — lists with their number and progress, items with theirs."""
    t = {
        "lists": [
            {"id": "general", "name": "General", "no": 1, "builtin": True, "total": 1, "done": 0},
            {"id": "tl_la_compra", "name": "La compra", "no": 2, "builtin": False, "total": 3, "done": 1},
        ],
        "items": {
            "general": [{"id": "t_banco", "no": 1, "title": "Llamar al banco", "status": "todo",
                         "date": "", "time": "", "planned": False}],
            "tl_la_compra": [
                {"id": "t_pan", "no": 1, "title": "Pan", "status": "done", "date": "", "time": "", "planned": False},
                {"id": "t_leche", "no": 2, "title": "Leche", "status": "todo", "date": "", "time": "", "planned": False},
                {"id": "t_huevos", "no": 3, "title": "Huevos", "status": "todo",
                 "date": _d(1), "time": "17:00", "planned": False},
            ],
        },
        "view": None,
    }
    t.update(over)
    return t


def _data(**over):
    d = {"date": _d(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
         "active": None, "days": _days(), "todayIndex": 0, "meetings": [], "projects": [],
         "view": None, "calendars": [], "warnings": [], "coaching": [], "tasks": _tasks()}
    d.update(over)
    return d


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


def _mount(page, data, *, card_w=920):
    page.goto(page._hb_origin)
    page.set_content(f"<div id='w' style='width:{card_w}px;height:620px'></div>")
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


def _open_tasks(page):
    page.click('.agsecb[data-sec="tasks"]')


# ── the selector, and what it actually swaps ───────────────────────────────────────────────────────────

def test_the_card_opens_on_the_calendar_with_both_sections_offered(_page):
    _mount(_page, _data())
    assert _page.locator(".agsec .agsecb").count() == 2
    assert _page.locator(".agsecb.on").get_attribute("data-sec") == "agenda"
    assert _page.locator(".agviews").count() == 1, "the calendar's own view band is there"
    assert _page.locator(".agt").count() == 0


def test_choosing_TAREAS_replaces_the_calendar_instead_of_sitting_beside_it(_page):
    """«Arriba del todo un selector que separe lo que es agenda de tareas» — separate, not stacked. The
    calendar's toolbar and its four views belong to the other half and must be gone, or the card shows
    a day nav that steers nothing."""
    _mount(_page, _data())
    _open_tasks(_page)
    assert _page.locator(".agsecb.on").get_attribute("data-sec") == "tasks"
    assert _page.locator(".agt").count() == 1
    assert _page.locator(".agviews").count() == 0, "the calendar's view band is still on screen"
    assert _page.locator(".agbar").count() == 0, "so is its ‹ Hoy › toolbar"


def test_going_back_returns_the_calendar_whole(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agsecb[data-sec="agenda"]')
    assert _page.locator(".agviews .agtab").count() == 4
    assert _page.locator(".agt").count() == 0


# ── the lists: the number, the name, the progress ──────────────────────────────────────────────────────

def test_every_list_leads_with_the_number_he_will_SPEAK(_page):
    """«Ábreme la lista número 3» only works if the 3 is on the screen he is reading."""
    _mount(_page, _data())
    _open_tasks(_page)
    rows = _page.locator(".agt-side .agt-list")
    assert rows.count() == 2
    assert [rows.nth(i).locator(".agt-no").inner_text() for i in range(2)] == ["1", "2"]
    assert [rows.nth(i).locator(".agt-lname").inner_text() for i in range(2)] == ["General", "La compra"]


def test_a_list_shows_how_far_along_it_is(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    row = _page.locator('.agt-side .agt-list[data-list="tl_la_compra"]')
    assert row.locator(".agt-count").inner_text() == "1/3"
    width = _page.evaluate(
        """() => { const r = document.querySelector('.agt-list[data-list="tl_la_compra"]');
                   const bar = r.querySelector('.agt-prog'), fill = r.querySelector('.agt-prog span');
                   return fill.getBoundingClientRect().width / bar.getBoundingClientRect().width; }""")
    assert 0.30 < width < 0.37, f"1 of 3 should paint about a third of the bar, got {width:.2f}"


def test_clicking_a_list_shows_ITS_items_numbered_from_one(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    rows = _page.locator(".agt-items .agt-item")
    assert rows.count() == 3
    assert [rows.nth(i).locator(".agt-ino").inner_text() for i in range(3)] == ["1.", "2.", "3."]
    assert [rows.nth(i).locator(".agt-text").inner_text() for i in range(3)] == ["Pan", "Leche", "Huevos"]
    assert rows.nth(0).get_attribute("class").find("done") >= 0, "a finished item reads as finished"
    assert rows.nth(2).locator(".agt-when").count() == 1, "the one with a day and an hour says so"


def test_the_lists_IDENTIFIER_is_on_screen_because_he_will_share_it(_page):
    """«Ese identificador lo podré compartir en el futuro con otro agente a través de la red de MeshKore».
    An id you cannot see is an id you cannot hand over."""
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    assert _page.locator(".agt-id").inner_text() == "tl_la_compra"


# ── every gesture reaches the widget's DECLARED action ─────────────────────────────────────────────────

def _calls(page):
    return page.evaluate("() => window.__calls")


def test_ticking_an_item_marks_it_done_through_the_action(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    _page.locator(".agt-items .agt-item").nth(1).locator(".agt-check").click()
    name, payload = _calls(_page)[-1]
    assert name == "done" and payload["task"] == "t_leche" and payload["list"] == "tl_la_compra"


def test_adding_an_item_goes_to_the_list_being_looked_at(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    _page.fill('.agt-add input[data-add="task"]', "Aceite")
    _page.click('.agt-add button[data-a2="additem"]')
    name, payload = _calls(_page)[-1]
    assert name == "add_task" and payload == {"title": "Aceite", "list": "tl_la_compra"}


def test_deleting_an_item_is_one_click_and_emptying_the_LIST_asks_first(_page):
    """One row off a checklist is cheap and runs; taking the whole list is not, and the question is shown
    IN the card with Yes/No — the house rule, no popups."""
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    _page.locator(".agt-items .agt-item").nth(0).locator('[data-a2="deleteitem"]').click()
    assert _calls(_page)[-1][0] == "delete_task"

    before = len(_calls(_page))
    _page.click('[data-a2="clear"]')
    assert len(_calls(_page)) == before, "emptying a list must not have run on the first click"
    assert _page.locator(".agt-ask").count() == 1
    _page.click('[data-a2="clearyes"]')
    name, payload = _calls(_page)[-1]
    assert name == "clear_list" and payload["list"] == "tl_la_compra"


def test_creating_a_list_asks_for_its_name_and_then_creates_it(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('[data-a2="newlist"]')
    _page.fill(".agt-newl input", "Viaje a Roma")
    _page.press(".agt-newl input", "Enter")
    name, payload = _calls(_page)[-1]
    assert name == "add_list" and payload == {"name": "Viaje a Roma"}


def test_renaming_a_list_edits_it_in_place(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    _page.click('[data-a2="rename"]')
    _page.fill(".agt-head input", "Súper")
    _page.press(".agt-head input", "Enter")
    name, payload = _calls(_page)[-1]
    assert name == "rename_list" and payload == {"list": "tl_la_compra", "newName": "Súper"}


def test_editing_an_items_text_sends_the_new_title_only(_page):
    _mount(_page, _data())
    _open_tasks(_page)
    _page.click('.agt-list[data-list="tl_la_compra"]')
    _page.locator(".agt-items .agt-item").nth(1).locator('[data-a2="edititem"]').click()
    _page.fill(".agt-items input", "Leche entera")
    _page.press(".agt-items input", "Enter")
    name, payload = _calls(_page)[-1]
    assert name == "update_task" and payload["newTitle"] == "Leche entera" and payload["task"] == "t_leche"


# ── the voice can move this screen, and only when it says something new ────────────────────────────────

def test_a_voice_order_opens_the_section_ON_the_list_it_named(_page):
    """`show_tasks` is the only way «ábreme la lista de la compra» can land — reopening the card always
    comes back to the calendar (the V2-540 rule, one section over)."""
    _mount(_page, _data(tasks=_tasks(view={"list": "tl_la_compra", "n": 1, "at": 1})))
    assert _page.locator(".agsecb.on").get_attribute("data-sec") == "tasks"
    assert _page.locator(".agt-list.on").get_attribute("data-list") == "tl_la_compra"


def test_a_plain_refresh_does_not_drag_him_out_of_what_he_is_reading(_page):
    """The token is a COUNTER: the same push re-delivered on a repaint must move nothing, or every
    background tick would yank the list under his hand."""
    data = _data(tasks=_tasks(view={"list": "tl_la_compra", "n": 1, "at": 1}))
    _mount(_page, data)
    _page.click('.agt-list[data-list="general"]')
    assert _page.locator(".agt-list.on").get_attribute("data-list") == "general"
    _page.evaluate("d => window.__mod.render(document.getElementById('w'), d, window.__ctx)", data)
    assert _page.locator(".agt-list.on").get_attribute("data-list") == "general"


def test_asking_for_a_DAY_brings_the_calendar_back(_page):
    """«Enséñame el jueves» answered while the card sits on the shopping list would be a day nobody sees."""
    data = _data(tasks=_tasks(view={"list": "tl_la_compra", "n": 1, "at": 1}))
    _mount(_page, data)
    assert _page.locator(".agsecb.on").get_attribute("data-sec") == "tasks"
    _page.evaluate("""d => { const nd = JSON.parse(JSON.stringify(d));
                             nd.view = {sel: "month", n: 7, at: 1};
                             window.__mod.render(document.getElementById('w'), nd, window.__ctx); }""", data)
    assert _page.locator(".agsecb.on").get_attribute("data-sec") == "agenda"
    assert _page.locator(".agtab.on").get_attribute("data-view") == "month"


# ── nothing the data carries becomes markup ────────────────────────────────────────────────────────────

def test_a_task_title_is_TEXT_however_it_is_written(_page):
    """Widget data is brain-pushable, which means it is untrusted: the whole card is built with
    `textContent`, and this is the section that renders the most of it."""
    hostile = "<img src=x onerror=alert(1)>"
    t = _tasks()
    t["items"]["general"] = [{"id": "t_x", "no": 1, "title": hostile, "status": "todo",
                              "date": "", "time": "", "planned": False}]
    t["lists"][0]["name"] = hostile
    _mount(_page, _data(tasks=t))
    _open_tasks(_page)
    assert _page.locator(".agt-items img").count() == 0
    assert _page.locator(".agt-items .agt-text").inner_text() == hostile
    assert _page.locator('.agt-list[data-list="general"] .agt-lname').inner_text() == hostile
