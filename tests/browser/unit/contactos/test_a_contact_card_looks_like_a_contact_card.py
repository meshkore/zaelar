"""V2-699 — the contact card, RENDERED.

The operator opened the card for his only contact — Cryptonite, the one he talks to on Telegram every day —
and reported, verbatim: «cuando entro en la ficha de este Cryptonite me pone que es una persona, fíjate que
no está estructurado, no muestra ni siquiera los campos básicos, aunque sean vacíos, para que se vea que es
una ficha de un contacto. No está tampoco la cuenta de Telegram, que es lo único, el único dato que tenemos
de ese contacto.»

MEASURED before touching anything: the Telegram account WAS stored — handle, chatId, marked preferred — and
`data.py::view_data` ships the whole record to the browser. `widget.js::renderDetail` painted five fixed
rows and `row()` returned early on an empty value, so a contact whose only datum is a channel painted a
name, the word «PERSON», and nothing else.

RENDERED rather than read, for the same reason V2-697's card tests are: the store and the card were each
correct on their own, and no source scan finds a field that simply is not copied.
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


def _cryptonite(**over):
    """His record, byte for byte as `widgets/_data/contactos/state.json` holds it."""
    c = {"id": "c1", "kind": "person", "name": "Cryptonite", "city": "", "address": "", "phone": "",
         "email": "", "notes": "", "groups": [], "favorite": False,
         "channels": [{"platform": "telegram", "handle": "@cryptonite_fund", "chatId": "7477656357",
                       "source": "operator", "volume": 7, "last_seen": 1789426047.0}],
         "preferred": "telegram", "parentId": "", "created": "2026-09-13", "updated": "2026-09-13"}
    c.update(over)
    return c


def _data(contacts=None, **over):
    cs = contacts if contacts is not None else [_cryptonite()]
    groups = {}
    for c in cs:
        for g in c.get("groups") or []:
            groups[g] = groups.get(g, 0) + 1
    d = {"contacts": cs, "groups": [{"id": g, "count": n} for g, n in groups.items()],
         "cities": sorted({c["city"] for c in cs if c.get("city")}),
         "favorites_count": sum(1 for c in cs if c.get("favorite")), "count": len(cs), "view": None,
         "providers": _providers(), "sync": _sync()}
    d.update(over)
    return d


def _providers(google="connected"):
    """The subheader strip, exactly as `gcontacts.providers()` builds it."""
    return [{"id": "google-contacts", "label": "Google Contacts", "status": google},
            {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
            {"id": "carddav", "label": "CardDAV (Outlook, Fastmail…)", "status": "unavailable"}]


def _sync(**over):
    s = {"connected": True, "twoWay": False, "tier": "saved", "last": 0.0, "lastResult": {}, "auto": True}
    s.update(over)
    return s


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
            page._hb_url = f"http://127.0.0.1:{port}/widgets/contactos/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/contactos/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data):
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:900px'></div>")
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


def _open_card(page, contact=None, data=None):
    _mount(page, data if data is not None else _data([contact or _cryptonite()]))
    page.locator(".ctrow").first.click()
    page.wait_for_selector(".ctdet")


def _calls(page):
    return page.evaluate("window.__calls")


def _classes(locator):
    """Class list as TOKENS. ⚠️ A substring check is wrong here and silently passes: «on» is inside
    «ctconnicon», so `"on" in class_attr` is true of every icon whether it is lit or not."""
    return set((locator.get_attribute("class") or "").split())


def _row_for(page, platform_label):
    """The «Cómo contactar» row for one platform, located by the label the operator reads."""
    return page.locator(".ctch").filter(has_text=platform_label)


# ── THE DEFECT HE REPORTED ──────────────────────────────────────────────────────────────────────────────

def test_the_card_shows_the_telegram_account(_page):
    """«No está tampoco la cuenta de Telegram, que es lo único que tenemos de ese contacto.»"""
    _open_card(_page)
    assert "@cryptonite_fund" in _page.locator(".ctdet").inner_text()


def test_every_channel_is_present_even_when_it_is_empty(_page):
    """«No muestra ni siquiera los campos básicos, aunque sean vacíos.»

    The counterweight to the case above: showing only the channels a contact HAS is the card this
    replaced — he could not tell «no tengo su WhatsApp» from «esta ficha no enseña WhatsApp».
    """
    _open_card(_page)
    assert _page.locator(".ctch").count() == 3, "telegram, whatsapp and email — always all three"
    assert _row_for(_page, "WhatsApp").locator(".ctfv").inner_text().strip() == "—"
    assert _row_for(_page, "Email").locator(".ctfv").inner_text().strip() == "—"


def test_every_basic_field_is_present_even_when_it_is_empty(_page):
    _open_card(_page)
    labels = [t.strip() for t in _page.locator(".ctdsec .ctfr .ctfk").all_inner_texts()]
    for expected in ("Teléfono", "Ciudad", "Dirección", "Notas"):
        assert expected in labels, f"{expected} has to be on the card of a contact who has no {expected}"
    voids = _page.locator(".ctdsec .ctfr .ctfv.void")
    assert voids.count() == 4, "an empty field reads as empty, it does not disappear"


def test_the_kind_reads_as_a_word_and_not_as_a_database_field(_page):
    """He quoted it as «me pone que es una persona» — a raw uppercase PERSON is a column name, not a card."""
    _open_card(_page)
    kind = _page.locator(".ctkind").inner_text()
    assert "persona" in kind.lower()
    assert "PERSON" not in kind, "the label is the word, not the stored enum"


# ── the preferred channel, and the asymmetry it must not break ──────────────────────────────────────────

def test_the_preferred_channel_is_the_one_marked(_page):
    _open_card(_page)
    assert _row_for(_page, "Telegram").locator(".ctpref.on").count() == 1
    assert _page.locator(".ctch .ctpref.on").count() == 1, "exactly one channel is the preferred one"


def test_a_stored_phone_never_becomes_a_whatsapp(_page):
    """`widgets/directory.py`'s one written-down asymmetry, mirrored in the card.

    A stored email IS an email channel — the address is the whole capability. A stored phone is NOT a
    WhatsApp: having somebody's number is not proof they use WhatsApp, and a card that painted one would
    claim a reachability the sending door refuses.
    """
    _open_card(_page, _cryptonite(phone="+34600111222"))
    assert _row_for(_page, "WhatsApp").locator(".ctfv").inner_text().strip() == "—"
    assert "+34600111222" in _page.locator(".ctdsec").filter(has_text="Datos").inner_text()


def test_a_stored_email_IS_the_email_channel(_page):
    """The other half of the same asymmetry — and it must be the SAME address, not a second one."""
    _open_card(_page, _cryptonite(email="hola@cryptonite.fund"))
    assert _row_for(_page, "Email").locator(".ctfv").inner_text().strip() == "hola@cryptonite.fund"


# ── editing in place ────────────────────────────────────────────────────────────────────────────────────

def test_typing_a_field_saves_it(_page):
    _open_card(_page)
    _page.locator(".ctdsec .ctfr").filter(has_text="Ciudad").locator(".ctfv").click()
    _page.locator(".ctdsec input.ctin").fill("Soria")
    _page.keyboard.press("Enter")
    assert ["update_contact", {"contactId": "c1", "city": "Soria"}] in _calls(_page)


def test_emptying_a_field_CLEARS_it_instead_of_doing_nothing(_page):
    """`update_contact` ignores an empty string on purpose, so a model that omits a field cannot wipe it.

    That guard would have made the card's delete a silent no-op — the worst shape of all, because the row
    goes back to showing the old value and reads as though the engine had refused without saying so. The
    card therefore NAMES the field it clears.
    """
    _open_card(_page, _cryptonite(city="Soria"))
    _page.locator(".ctdsec .ctfr").filter(has_text="Ciudad").locator(".ctfv").click()
    _page.locator(".ctdsec input.ctin").fill("")
    _page.keyboard.press("Enter")
    assert ["update_contact", {"contactId": "c1", "clear": "city"}] in _calls(_page)


def test_escape_cancels_without_writing(_page):
    _open_card(_page)
    _page.locator(".ctdsec .ctfr").filter(has_text="Ciudad").locator(".ctfv").click()
    _page.locator(".ctdsec input.ctin").fill("Soria")
    _page.keyboard.press("Escape")
    assert not [c for c in _calls(_page) if c[0] == "update_contact"], "a cancel that still wrote is a lie"


def test_typing_a_telegram_handle_saves_the_channel(_page):
    _open_card(_page, _cryptonite(channels=[], preferred=""))
    _row_for(_page, "Telegram").locator(".ctfv").click()
    _page.locator(".ctch input.ctin").fill("@nuevo")
    _page.keyboard.press("Enter")
    assert ["set_channel", {"contactId": "c1", "platform": "telegram",
                            "handle": "@nuevo", "preferred": False}] in _calls(_page)


def test_clearing_a_channel_removes_it(_page):
    _open_card(_page)
    _row_for(_page, "Telegram").locator(".ctchx").click()
    assert ["set_channel", {"contactId": "c1", "platform": "telegram", "remove": True}] in _calls(_page)


def test_starring_a_channel_makes_it_preferred(_page):
    _open_card(_page, _cryptonite(email="hola@cryptonite.fund"))
    _row_for(_page, "Email").locator(".ctpref").click()
    assert ["set_channel", {"contactId": "c1", "platform": "email",
                            "preferred": True}] in _calls(_page)


# ── the list and the sidebar he called «un menú ahí suelto» ─────────────────────────────────────────────

def test_the_sidebar_is_a_panel_and_not_loose_buttons(_page):
    _mount(_page, _data())
    side = _page.locator(".ctside")
    assert side.count() == 1
    bg = _page.evaluate("getComputedStyle(document.querySelector('.ctside')).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent"), "a menu with no ground is the loose menu he saw"


def test_the_favourites_control_is_not_duplicated(_page):
    """It used to be BOTH a sidebar entry and a chip over the list — two surfaces for one fact, and half
    of the «menú ahí suelto» he reported.

    ⚠️ Measured against a directory with TWO cities on purpose. The filter strip only exists when there is
    more than one city to choose between, so asserting «no favourites chip» on a one-contact fixture
    passes without measuring anything — a disarm that put the chip straight back stayed GREEN until this
    fixture changed.
    """
    _mount(_page, _data([_cryptonite(city="Soria"),
                         _cryptonite(id="c2", name="Marta", city="Barcelona", channels=[], preferred="")]))
    strip = _page.locator(".ctfil")
    assert strip.count() == 1, "the fixture has to actually render the strip for this to measure anything"
    assert _page.locator(".ctside .ctg", has_text="Favoritos").count() == 1
    assert _page.locator(".ctfil .ctchip", has_text="favoritos").count() == 0
    assert sorted(_page.locator(".ctfil .ctchip").all_inner_texts()) == ["Barcelona", "Soria"]


def test_the_search_is_in_the_header(_page):
    _mount(_page, _data())
    assert _page.locator(".ctbar .ctsearch input").count() == 1


def test_a_list_row_says_how_to_reach_him(_page):
    _mount(_page, _data())
    assert _page.locator(".ctrow .ctsub").first.inner_text().strip() == "@cryptonite_fund"


def test_the_search_matches_a_channel_handle(_page):
    """He knows people by their account as often as by their name."""
    _mount(_page, _data())
    _page.locator(".ctbar .ctsearch input").fill("cryptonite_fund")
    assert _page.locator(".ctrow").count() == 1


def test_every_row_carries_a_face(_page):
    _mount(_page, _data())
    assert _page.locator(".ctrow .ctav").count() == 1


# ── THE HOUSE HEADER STANDARD (his second report, the same day) ─────────────────────────────────────────
# «Esto es un sistema operativo, con lo cual esas barras ya tienen un formato estándar y nos llevan al
# sistema de conectores.» The contract lives in
# `.meshkore/docs/conventions/zaelar-widget-header-standard.md`; these cases are what holds it.

def test_the_widget_wears_the_house_header_and_subheader(_page):
    _mount(_page, _data())
    assert _page.locator(".ctbar .ctbrand svg").count() == 1, "brand disc with the widget's own mark"
    assert _page.locator(".ctbar .cttitle").inner_text().strip() == "Contactos"
    assert _page.locator(".ctviews").count() == 1, "the subheader band"
    assert _page.locator(".ctviews .ctviewsright .ctconnbtn").count() == 1, "the plug button, right-aligned"


def test_the_subheader_shows_every_contact_source(_page):
    """«El iconito de Google y el de Apple desactivado, para que la gente sepa que se pueden conectar
    varias fuentes de contactos al sistema.»"""
    _mount(_page, _data())
    icons = _page.locator(".ctconnicons .ctconnicon")
    assert icons.count() == 3, "Google, iCloud and CardDAV — what we have and what we do not"
    assert icons.nth(1).is_disabled(), "a source with no connector is visible but INERT"
    assert icons.nth(2).is_disabled()


def test_a_connected_source_is_shown_IN_COLOUR_and_the_rest_dimmed(_page):
    """«Como los conectores ya están conectados en cuanto a Google […] el iconito de contactos debería
    estar en color.» Same contract as the agenda's strip (V2-679)."""
    _mount(_page, _data())
    g = _page.locator(".ctconnicons .ctconnicon").first
    assert "on" in _classes(g), "connected reads as lit"
    assert _page.evaluate("getComputedStyle(document.querySelector('.ctconnicon')).opacity") == "1"
    assert "off" in _classes(_page.locator(".ctconnicon").nth(1))


def test_a_source_that_is_not_linked_does_not_read_as_linked(_page):
    _mount(_page, _data(providers=_providers(google="off")))
    g = _page.locator(".ctconnicons .ctconnicon").first
    assert "on" not in _classes(g)
    assert not g.is_disabled(), "not linked is still a DOOR — it is «we have not built it» that is inert"


def test_there_is_no_import_button_in_the_sidebar_any_more(_page):
    """He had it removed: importing is a CONNECTOR gesture, and every connector gesture in this product is
    reached the same way — the plug button in the subheader."""
    _mount(_page, _data())
    assert _page.locator(".ctside .ctact", has_text="Importar").count() == 0
    assert _page.locator(".ctside .ctact", has_text="Nuevo").count() == 1, "adding a contact still lives here"


def test_the_plug_button_opens_the_connectors_screen_over_the_content(_page):
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctconnscreen").count() == 1
    assert _page.locator(".ctcols").count() == 0, "a SCREEN, not an overlay floating on the list"
    assert _page.locator(".cttab").first.is_disabled(), "no tab is the one on screen while it is open"


def test_the_connectors_screen_lists_the_sources_with_their_state(_page):
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    rows = _page.locator(".ctsrc")
    assert rows.count() == 3
    assert "conectado" in rows.first.inner_text()
    assert _page.locator(".ctsrc .ctdot.ok").count() == 1


def test_a_connected_source_offers_DISCONNECT_and_an_unlinked_one_offers_CONNECT(_page):
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsrc .ctbtn", has_text="Desconectar").count() == 1
    _mount(_page, _data(providers=_providers(google="off")))
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsrc .ctbtn", has_text="Conectar").count() == 1


def test_a_source_we_have_not_built_offers_no_button_at_all(_page):
    """Showing «Conectar» on iCloud would promise a flow that does not exist — the same class of lie as
    promising a view (V2-540)."""
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsrc").nth(1).locator(".ctbtn").count() == 0


# ── the sync box ────────────────────────────────────────────────────────────────────────────────────────

def test_the_sync_box_appears_only_for_a_linked_source(_page):
    _mount(_page, _data(providers=_providers(google="off"), sync=_sync(connected=False)))
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsync").count() == 0
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsync").count() == 1


def test_the_sync_panel_lives_INSIDE_the_account_it_belongs_to(_page):
    """His report: «la cajita de sincronización va dentro del google connector box. no suelta.»

    A second bordered box under the account row reads as a second, unrelated feature — and the one thing a
    connectors screen has to make obvious is WHICH account each control acts on. So the card is the source:
    one box, the account row first, everything that source owns underneath it.
    """
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    boxes = _page.locator(".ctsrcbox")
    assert boxes.count() == 3, "one card per source, and the card is the box"
    assert boxes.first.locator(".ctsync").count() == 1, "the sync panel belongs to Google's own card"
    assert _page.locator(".ctconnscreen > .ctsync").count() == 0, "never a sibling floating beside it"
    # …and it is a SECTION of that card, not a box drawn inside a box.
    assert _page.evaluate(
        "getComputedStyle(document.querySelector('.ctsync')).borderBottomWidth") == "0px"


def test_a_read_only_connection_SAYS_it_only_brings(_page):
    """The honest half. The write scope is not on the OAuth app yet, so a box promising two directions
    would be promising something Google will refuse."""
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsyncarrow").inner_text().strip() == "→"
    assert _page.locator(".ctwarn").count() == 1
    assert "escritura" in _page.locator(".ctwarn").inner_text()


def test_a_two_way_connection_says_so_in_one_line(_page):
    """His own simplification: «quitando esas opciones y solo dejando la sincronización activa», so there
    are no direction checkboxes to get wrong — one state, said once."""
    _mount(_page, _data(sync=_sync(twoWay=True, tier="sync")))
    _page.locator(".ctconnbtn").click()
    assert _page.locator(".ctsyncarrow").inner_text().strip() == "⇄"
    assert _page.locator(".ctwarn").count() == 0
    assert "también cambia en Google" in _page.locator(".ctsyncdir").inner_text()
    assert _page.locator(".ctsync input[type=checkbox]").count() == 0


def test_the_sync_button_runs_the_sync(_page):
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    _page.locator(".ctsync .ctbtn", has_text="Sincronizar").click()
    assert ["sync_contacts", {}] in _calls(_page)


def test_the_box_says_when_it_last_ran_and_what_it_did(_page):
    _mount(_page, _data(sync=_sync(last=1789426047.0,
                                   lastResult={"added": 12, "updated": 3, "pushed": 2})))
    _page.locator(".ctconnbtn").click()
    txt = _page.locator(".ctsyncwhen").inner_text()
    assert "12 nuevos" in txt and "3 completados" in txt and "2 enviados a Google" in txt


def test_a_directory_that_has_never_synced_does_not_claim_a_date(_page):
    _mount(_page, _data())
    _page.locator(".ctconnbtn").click()
    assert "Todavía no" in _page.locator(".ctsyncwhen").inner_text()


# ── the kind tabs ───────────────────────────────────────────────────────────────────────────────────────

def test_the_kind_tabs_filter_and_do_not_duplicate_the_sidebar(_page):
    """Two different axes on purpose: the band filters by KIND, the rail by his own group labels. Putting
    «Todos / ★ Favoritos» in both is the duplication he called «un menú ahí suelto»."""
    _mount(_page, _data([_cryptonite(),
                         _cryptonite(id="c2", name="Elfo On", kind="place", channels=[], preferred="")]))
    assert _page.locator(".ctrow").count() == 2
    _page.locator(".cttab[data-kind='place']").click()
    assert _page.locator(".ctrow").count() == 1
    assert _page.locator(".ctrow .ctnm").inner_text() == "Elfo On"
    assert _page.locator(".ctviews .cttab", has_text="Favoritos").count() == 0
