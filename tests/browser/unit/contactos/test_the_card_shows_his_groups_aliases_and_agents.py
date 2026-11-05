"""V2-854 F5 — the contacts card, RENDERED: his groups in the rail, the strip over a group, and the person's aliases,
relation, groups and agents on her card.

The store already held all of it (F1: groups as rows with an id, `aliasSources`, `agents`, the derived unclassified)
and the card showed none: the aliases he had given Rakel existed and were not on her card, and a group could only be
made by voice. Rendered, because a section that is simply not painted passes every source scan.

  · rail: «Grupos» — the natives always (a 0 says nobody is filed there yet), then his by size, «+ Nuevo grupo»;
    «Estado» — «Sin clasificar» (no phone, no e-mail, no channel) and «Ocultos»; the kind of a chat group reads
    «Grupos de chat» so it never collides with his groups;
  · strip over a group: add members (a selection mode over the whole directory, its difference written in one call
    each way), send a message (never from the card: `message_group`, and with no WhatsApp mirror it asks ONCE —
    create the WhatsApp group or one by one), the mirror, rename and delete for his own groups only;
  · her card: aliases as chips (a learned one dimmer, editable, removable), the relation as a selector, the native
    groups as toggles (one held by her relation cannot be untoggled — the relation owns it), his groups as chips,
    the agents (id + cluster) for a person or a company.
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

_NATS = [{"id": "favorites"},
         {"id": "family", "relations": ["partner", "mother", "father", "child", "sibling", "grandparent", "family"]},
         {"id": "friends", "relations": ["friend"]}, {"id": "colleagues", "relations": ["colleague"]}]
_RELATIONS = ["partner", "mother", "father", "child", "sibling", "grandparent", "family", "friend", "colleague"]


def _people():
    """Synthetic, shaped like his directory: a favorite with a near spelling, a group of his, a WhatsApp chat group
    of the same name as another group of his, a name with no way to reach it."""
    return [
        {"id": "c1", "kind": "person", "name": "Rakel Prat", "favorite": True, "relation": "partner",
         "aliases": ["Raquel", "Raki"], "aliasSources": {"Raki": "learned"},
         "agents": [{"agent_id": "ag_7f3a", "cluster": "commons", "label": ""}],
         "channels": [{"platform": "whatsapp", "chatId": "111@lid", "handle": "+34 600 000 111"}], "groups": []},
        {"id": "c2", "kind": "person", "name": "Pau Serra", "groups": ["School parents"],
         "channels": [{"platform": "whatsapp", "chatId": "222@lid"}]},
        {"id": "c3", "kind": "person", "name": "Mia Font", "groups": ["School parents", "Climbing"],
         "channels": [{"platform": "telegram", "chatId": "333"}]},
        {"id": "c4", "kind": "person", "name": "Nobody Reachable", "groups": []},
        {"id": "w1", "kind": "group", "name": "Climbing", "platform": "whatsapp",
         "channels": [{"platform": "whatsapp", "chatId": "999@g.us"}], "groups": []},
    ]


def _rows(people):
    nat = [{"groupId": g["id"], "name": g["id"], "native": True} for g in _NATS]
    his = [{"groupId": "g1", "name": "School parents", "native": False},
           {"groupId": "g2", "name": "Climbing", "native": False,
            "mirror": {"contactId": "w1", "name": "Climbing", "platform": "whatsapp"}}]
    return nat + his


def _data(**over):
    cs = _people()
    d = {"contacts": cs, "groups": [], "cities": [], "favorites_count": 1, "count": len(cs), "view": None,
         "providers": [], "sync": {"connected": False}, "hidden_rows": [], "groupRows": _rows(cs),
         "native_groups": _NATS, "relations": _RELATIONS, "unclassified_count": 1}
    d.update(over)
    return d


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


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
            page = browser.new_page(viewport={"width": 1100, "height": 900})
            page._hb = (f"http://127.0.0.1:{port}/widgets/contactos/widget.js",
                        f"http://127.0.0.1:{port}/widgets/contactos/")
            page._errors = []
            page.on("pageerror", lambda e: page._errors.append(str(e)))
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, reply=None):
    """`reply` is what every action answers (default {ok:true}); each call is recorded."""
    page.goto(page._hb[1])
    page.set_content("<div id='w' style='width:900px'></div>")
    page._errors.clear()
    page.evaluate(
        """async ([src, data, reply]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve(reply || {ok: true}); },
                              openConnector: () => {}, top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb[0], data, reply])


def _calls(page):
    return page.evaluate("window.__calls")


def _rail(page):
    return page.evaluate("[...document.querySelectorAll('.ctside .ctg')].map(b => b.textContent.trim())")


def _open(page, name):
    page.locator(".ctrow", has_text=name).first.click()
    page.wait_for_selector(".ctdet")


def _section(page, title):
    return page.locator(".ctdsec").filter(has=page.locator("h4", has_text=title))


# ── the rail ───────────────────────────────────────────────────────────────────────────────────────────────

def test_the_rail_shows_the_natives_always_then_his_groups(_page):
    _mount(_page, _data())
    labels = _page.evaluate("[...document.querySelectorAll('.ctsidelbl')].map(b => b.textContent)")
    assert "Grupos" in labels and "Etiquetas" not in labels, labels
    rail = _rail(_page)
    for native, n in (("Familia", 1), ("Amigos", 0), ("Compañeros", 0)):
        assert any(r.endswith(f"{native}{n}") for r in rail), (native, rail)
    assert any(r.startswith("School parents2") for r in rail) and any(r.startswith("Climbing1") for r in rail), rail
    assert _page.locator(".ctside .ctact", has_text="Nuevo grupo").count() == 1
    assert _page._errors == [], _page._errors


def test_a_relation_files_her_in_her_native_group(_page):
    _mount(_page, _data())
    _page.locator(".ctside .ctg", has_text="Familia").click()
    assert _page.locator(".ctrow .ctnm").all_inner_texts() == ["Rakel Prat"]


def test_the_unclassified_have_their_own_row(_page):
    _mount(_page, _data())
    assert _page.locator(".ctsidelbl", has_text="Estado").count() == 1
    _page.locator(".ctside .ctg", has_text="Sin clasificar").click()
    assert _page.locator(".ctrow .ctnm").all_inner_texts() == ["Nobody Reachable"]


def test_a_chat_group_kind_never_collides_with_his_groups(_page):
    _mount(_page, _data())
    assert any(r.endswith("Grupos de chat1") for r in _rail(_page)), _rail(_page)


def test_a_new_group_is_created_from_the_rail(_page):
    _mount(_page, _data())
    _page.locator(".ctside .ctact", has_text="Nuevo grupo").click()
    _page.locator(".ctside input.ctin").fill("Guitar course")
    _page.keyboard.press("Enter")
    assert ["create_group", {"name": "Guitar course"}] in _calls(_page)


def test_the_voice_pushes_one_of_his_groups_by_id(_page):
    _mount(_page, _data(view={"sel": {"groupId": "g1"}, "n": 1}))
    assert sorted(_page.locator(".ctrow .ctnm").all_inner_texts()) == ["Mia Font", "Pau Serra"]
    assert _page.locator(".ctgstrip .ctgsname").inner_text().startswith("School parents")


# ── the strip over a group ────────────────────────────────────────────────────────────────────────────────

def _group(page, name, **kw):
    _mount(page, _data(), **kw)
    page.locator(".ctside .ctg", has_text=name).click()
    page.wait_for_selector(".ctgstrip")


def test_adding_members_is_a_selection_over_the_whole_directory(_page):
    _group(_page, "School parents")
    _page.locator(".ctgstrip .ctbtn", has_text="Añadir").click()
    assert _page.locator(".ctrow").count() == 5, "every entry is offered, not only the members"
    assert _page.locator(".ctpickbox:checked").count() == 2, "the members start ticked"
    _page.locator(".ctrow", has_text="Rakel Prat").locator(".ctpickbox").click()
    _page.locator(".ctrow", has_text="Mia Font").locator(".ctpickbox").click()
    _page.locator(".ctgstrip .ctbtn", has_text="Listo").click()
    calls = _calls(_page)
    assert ["add_to_group", {"groupId": "g1", "contactIds": ["c1"]}] in calls, calls
    assert ["add_to_group", {"groupId": "g1", "contactIds": ["c3"], "remove": True}] in calls, calls


def test_a_message_to_a_group_without_a_mirror_asks_once_how(_page):
    _group(_page, "School parents")
    assert _page.locator(".ctgstrip .ctbtn", has_text="WhatsApp: crear").count() == 1
    _page.locator(".ctgstrip .ctbtn", has_text="Mandar mensaje").click()
    _page.locator(".ctgstrip input.ctin").fill("no school on friday")
    _page.keyboard.press("Enter")
    assert not [c for c in _calls(_page) if c[0] == "message_group"], "nothing leaves before he says how"
    assert _page.locator(".ctgask").count() == 1
    _page.locator(".ctgask .ctbtn", has_text="Uno a uno").click()
    assert ["message_group", {"groupId": "g1", "text": "no school on friday", "mode": "each"}] in _calls(_page)
    assert _page.locator(".ctgask").count() == 0, "asked once"


def test_a_group_with_a_mirror_writes_there_and_says_it_is_linked(_page):
    _group(_page, "Climbing", reply={"ok": True, "result": {"handed": "Manda…", "left_out": []}})
    assert _page.locator(".ctgstrip", has_text="enlazado").count() == 1
    _page.locator(".ctgstrip .ctbtn", has_text="Mandar mensaje").click()
    _page.locator(".ctgstrip input.ctin").fill("training at 7")
    _page.keyboard.press("Enter")
    assert ["message_group", {"groupId": "g2", "text": "training at 7", "mode": "group"}] in _calls(_page)
    _page.wait_for_selector(".ctnote")
    assert "agente" in _page.locator(".ctmain .ctnote").first.inner_text()


def test_a_native_group_is_not_renamed_nor_deleted(_page):
    _group(_page, "Familia")
    assert _page.locator(".ctgstrip .ctdel").count() == 0
    _mount(_page, _data())
    _page.locator(".ctside .ctg", has_text="School parents").click()
    assert _page.locator(".ctgstrip .ctdel", has_text="renombrar").count() == 1
    d = _page.locator(".ctgstrip .ctdel", has_text="borrar")
    d.click()
    assert not [c for c in _calls(_page) if c[0] == "delete_group"], "the first click only asks"
    _page.locator(".ctgstrip .ctdel", has_text="seguro").click()
    assert ["delete_group", {"groupId": "g1"}] in _calls(_page)


# ── her card ─────────────────────────────────────────────────────────────────────────────────────────────

def test_her_aliases_are_on_her_card_the_learned_one_dimmer(_page):
    _mount(_page, _data())
    _open(_page, "Rakel Prat")
    sec = _section(_page, "Alias")
    assert sec.count() == 1
    assert sec.locator(".cttag").count() == 2
    assert sec.locator(".cttag.learned").count() == 1 and "Raki" in sec.locator(".cttag.learned").inner_text()
    sec.locator(".cttag", has_text="Raquel").locator("button").click()
    assert ["set_alias", {"contactId": "c1", "alias": "Raquel", "remove": True}] in _calls(_page)


def test_an_alias_is_added_from_her_card(_page):
    _mount(_page, _data())
    _open(_page, "Rakel Prat")
    _section(_page, "Alias").locator(".ctaddtag").click()
    _page.locator(".ctdet input.ctin").fill("Kelly")
    _page.keyboard.press("Enter")
    assert ["set_alias", {"contactId": "c1", "alias": "Kelly"}] in _calls(_page)


def test_the_relation_is_a_selector_beside_the_kind(_page):
    _mount(_page, _data())
    _open(_page, "Pau Serra")
    pick = _page.locator(".cthero select.ctpick")
    assert pick.count() == 1
    pick.select_option("friend")
    assert ["set_alias", {"contactId": "c2", "relation": "friend"}] in _calls(_page)


def test_the_native_groups_are_toggles_and_the_relation_owns_its_own(_page):
    _mount(_page, _data())
    _open(_page, "Rakel Prat")
    sec = _section(_page, "Grupos")
    fam = sec.locator(".ctnat", has_text="Familia")
    assert "on" in (fam.get_attribute("class") or "").split() and fam.is_disabled(), "held by her relation"
    sec.locator(".ctnat", has_text="Amigos").click()
    assert ["add_to_group", {"groupId": "friends", "contactId": "c1"}] in _calls(_page)


def test_his_groups_on_her_card_can_be_left_and_joined(_page):
    _mount(_page, _data())
    _open(_page, "Mia Font")
    sec = _section(_page, "Grupos")
    sec.locator(".cttag", has_text="Climbing").locator("button").click()
    assert ["add_to_group", {"groupId": "g2", "contactId": "c3", "remove": True}] in _calls(_page)


def test_her_agents_are_listed_and_one_can_be_linked(_page):
    _mount(_page, _data())
    _open(_page, "Rakel Prat")
    sec = _section(_page, "Agentes")
    assert "ag_7f3a" in sec.inner_text() and "commons" in sec.inner_text()
    sec.locator(".ctaddtag").click()
    _page.locator(".ctdet input.ctin").first.fill("ag_new")
    _page.keyboard.press("Enter")
    assert ["set_agent", {"contactId": "c1", "agent_id": "ag_new", "cluster": ""}] in _calls(_page)


def test_a_chat_group_card_carries_no_agents_and_renders_cleanly(_page):
    _mount(_page, _data())
    _page.locator(".ctside .ctg", has_text="Grupos de chat").click()
    _open(_page, "Climbing")
    assert _section(_page, "Agentes").count() == 0
    assert _page._errors == [], _page._errors
