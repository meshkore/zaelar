"""A connector opens ALONE, behind a breadcrumb, with its step-by-step guide (operator, 2026-10-04).

«La pantalla de conectores me deja clickar en uno, pero luego salen todos juntos»: the chat column's catalog sent
the operator to ⚙ → Conectores, which rendered every connector's form at once (WhatsApp, Telegram, Email…), and
the WhatsApp «Conectar (mostrar QR)» never drew the QR the descriptor carries. Now the catalog names the connector,
the tab opens on that one with `Conectores › family › name`, the steps that happen outside come one at a time,
and the last step is the form plus the live state (the QR). The module is executed with node, not grepped.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
WIZ = APP / "components" / "ConnectorWizard.js"
CHATWALL = (APP / "components" / "ChatWall.js").read_text(encoding="utf-8")
PANEL = (APP / "components" / "ConfigPanel.js").read_text(encoding="utf-8")
STORE = (APP / "core" / "store.js").read_text(encoding="utf-8")

_RUN = r"""
globalThis.location = { origin: "http://localhost:43917" };
const W = await import(process.argv[1]);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const ui = { t: (k, p) => k + (p ? JSON.stringify(p) : ""), esc, badge: c => `[${c.connected ? "on" : "off"}]` };
const cs = JSON.parse(process.argv[2]);
const out = {
  list: W.connectorList(W.groupGoogle(cs), [["mensajeria", "Mensajería"], ["google", "Google"], ["agenda", "Calendario"]], ui),
  wa0: W.connectorWizard(cs[0], 0, "<FORM-wa>", "Mensajería", ui),
  wa1: W.connectorWizard(cs[0], 1, "<FORM-wa>", "Mensajería", ui),
  // A connected one, done: opened from a card that named itself, from an unnamed caller, and from the list.
  doneFrom: W.connectorWizard({ ...cs[1], connected: true }, 0, "<F>", "Mensajería", { ...ui, returnTo: { from: "Contactos" } }),
  doneAnon: W.connectorWizard({ ...cs[1], connected: true }, 0, "<F>", "Mensajería", { ...ui, returnTo: { from: "" } }),
  doneList: W.connectorWizard({ ...cs[1], connected: true }, 0, "<F>", "Mensajería", ui),
  // The real forms (2026-10-25 pass): fields stacked, actions on the left, the QR replacing its own button.
  forms: Object.fromEntries([
    ["email", { id: "email", label: "Email", family: "mensajeria", connected: false, config: {} }],
    ["tgShipped", { id: "telegram", label: "Telegram", family: "mensajeria", connected: false, config: { app_shipped: true } }],
    ["tgQr", { id: "telegram", label: "Telegram", family: "mensajeria", connected: false, status: "connecting", qr: "data:image/png;base64,AAAA", config: { app_shipped: true } }],
    ["onedrive", { id: "onedrive", label: "OneDrive", family: "archivos", connected: false, config: {} }],
    ["architect", { id: "architect", label: "Architect", family: "infra", connected: false, config: {} }],
    ["meshkore", { id: "meshkore", label: "MeshKore", family: "infra", connected: false, clusters: [{ name: "equipo", connected: true }] }],
  ].map(([k, c]) => [k, W.connectorForm(c, f => f, { ...ui, service: "", consent: null })])),
  tgQrPage: W.connectorWizard(cs[0], 1, "<FORM-wa>", "Mensajería", ui),
  waLast: W.connectorWizard({ ...cs[0], qr: undefined, status: "off" }, 1, "<FORM-wa>", "Mensajería", ui),
  // Google is ONE connector (2026-10-04): the calendar row is a SERVICE inside the `google-account` group, and
  // the guide is the group's — its API step names every service's API, its credentials step the redirect URIs.
  gcal: W.guideSteps(W.groupGoogle(cs)[0]),
  gcalReady: W.guideSteps({ ...W.groupGoogle(cs)[0], app: true }),
  focus: [W.focusOf("google"), W.focusOf("gdrive"), W.focusOf("whatsapp")],
  keys: ["whatsapp", "telegram", "email", "spotify", "gdrive", "onedrive", "google-photos", "youtube", "google",
         "google-contacts", "google-account", "architect", "meshkore"]
        .flatMap(id => W.guideSteps({ id, config: {} }).map(g => g.key)),
};
console.log(JSON.stringify(out));
"""

CS = [{"id": "whatsapp", "label": "WhatsApp", "family": "mensajeria", "connected": False, "status": "connecting",
       "qr": "data:image/png;base64,AAAA"},
      {"id": "telegram", "label": "Telegram", "family": "mensajeria", "connected": False, "status": "off"},
      {"id": "google-account", "label": "Google", "family": "google", "connected": False, "status": "off",
       "config": {"app_configured": False, "redirect_uris": ["http://localhost:43917/api/calendar/callback"]}},
      {"id": "google", "label": "Google Calendar", "family": "agenda", "connected": False, "status": "off",
       "config": {"app_configured": False}}]


@pytest.fixture(scope="module")
def run():
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    p = subprocess.run(["node", "--input-type=module", "-e", _RUN, str(WIZ), json.dumps(CS)],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_the_list_opens_nothing_and_offers_one_card_per_connector(run):
    assert run["list"].count('class="cf-cx-card"') == 3, "WhatsApp, Telegram and the Google services folded into ONE card"
    assert "<FORM" not in run["list"] and "cx_tg_api_id" not in run["list"]


def test_each_family_is_a_heading_followed_by_a_row_of_cards(run):
    """Operator 2026-10-23: «Google este; Mensajería y los tres iconos por separado en cajitas». Each family is
    its heading and then ONE grid holding that family's cards, in order — not a stacked full-width list."""
    groups = re.findall(r'<h3 class="cf-fam">([^<]+)</h3><div class="cf-cx-grid">(.*?)</div>(?=<h3|$)', run["list"])
    assert [(t, g.count('class="cf-cx-card"')) for t, g in groups] == [("Mensajería", 2), ("Google", 1)]
    assert 'data-cx="whatsapp"' in groups[0][1] and 'data-cx="telegram"' in groups[0][1]
    assert "cf-cx-row" not in run["list"] and "cf-cx-list" not in run["list"]


def test_the_connectors_tab_is_left_aligned_and_its_cards_wrap():
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert '<div class="cf-scroll${activeTab === "conectores" ? " cf-scroll--cx" : ""}"><div class="cf-panel${activeTab === "conectores" ? " cf-panel--cx" : ""}">' in PANEL
    assert ".cf-panel--cx{max-width:none;margin:0}" in css, "the centred column (margin:0 auto) is overridden"
    assert re.search(r"\.cf-cx-grid\{display:grid;grid-template-columns:repeat\(auto-fill,", css), "cards wrap"
    assert re.search(r"@media\(max-width:520px\)\{\s*\.cf-cx-grid\{grid-template-columns:repeat\(2,", css)


def test_one_connector_has_its_breadcrumb_and_a_way_back(run):
    assert 'data-cx-back="1"' in run["wa0"] and "Mensajería" in run["wa0"] and "<b>WhatsApp</b>" in run["wa0"]
    assert "<FORM-wa>" not in run["wa0"], "the guide comes before the form"


def test_the_last_step_is_the_form_and_the_qr_it_never_drew(run):
    assert "<FORM-wa>" in run["wa1"] and 'src="data:image/png;base64,AAAA"' in run["wa1"]
    assert "config.cxw.qr_scan_whatsapp" in run["wa1"]


def test_a_google_guide_names_its_api_and_the_redirect_to_register(run):
    assert run["gcal"][0]["params"]["api"] == "Google Calendar API"
    assert run["gcal"][1]["code"] == "http://localhost:43917/api/calendar/callback"
    assert run["gcalReady"] == [], "a registered app skips the Cloud Console half"


def test_any_google_service_opens_the_one_google_connector_with_that_service_picked_out(run):
    """A card's plug says `google` or `gdrive`; the section opens the single Google entry and highlights that
    service's consent row. A non-Google id opens itself."""
    assert run["focus"][0] == {"focus": "google-account", "service": "google"}
    assert run["focus"][1] == {"focus": "google-account", "service": "gdrive"}
    assert run["focus"][2] == {"focus": "whatsapp", "service": ""}


@pytest.mark.parametrize("bundle", ["es", "en"])
def test_every_step_has_its_words_in_both_bundles(run, bundle):
    b = json.loads((ENGINE / "i18n" / "genesis" / bundle / "ui.json").read_text(encoding="utf-8"))
    keys = {f"config.cxw.{k}.{part}" for k in run["keys"] for part in ("title", "body")}
    keys |= set(re.findall(r'"(config\.cxw\.[a-z_]+)"', WIZ.read_text(encoding="utf-8")))
    keys |= set(re.findall(r'"(config\.cxw\.[a-z_]+)"', PANEL))
    assert not sorted(k for k in keys if k not in b)


def test_the_catalog_names_the_connector_and_the_panel_consumes_it_once():
    assert "openConnectorConfig(c.id)" in CHATWALL and "store.setConfigConnector(id || null)" in CHATWALL
    assert re.search(r"export const \[configConnector, setConfigConnector\]", STORE)
    assert "store.configConnector()" in PANEL and "store.setConfigConnector(null)" in PANEL
    assert "connectorList(view, fams, ui)" in PANEL and "connectorWizard(c, cxStep, connectorForm(c, famTitle, {" in PANEL
    assert "const view = groupGoogle(cs);" in PANEL, "the panel renders the Google services as ONE connector"


def test_contacts_finally_has_a_form_and_a_route_behind_it():
    # The consent row of each Google service carries its own act; contacts' is `contacts-connect`.
    assert '"google-contacts": "contacts-connect"' in WIZ.read_text(encoding="utf-8") and "api.contactsConnect(" in PANEL
    api = (APP / "services" / "api.js").read_text(encoding="utf-8")
    assert '"/api/contacts/connect"' in api
    from connectors.contacts.server_api import router   # its routes are the shared door, connectors/oauth_routes.py
    assert any(r.path == "/api/contacts/connect" and "POST" in r.methods for r in router.routes)


def test_both_requests_are_read_before_either_is_cleared():
    """Clearing `configInitialTab` re-runs the open effect synchronously; a re-run that consumed the connector first
    left the outer run reading null, and the catalog's connector never opened (measured live, 2026-10-04)."""
    i = PANEL.index("const want = store.configInitialTab(), cxWant = store.configConnector(), from = store.configFrom();")
    assert i < PANEL.index("store.setConfigInitialTab(null)", i) < PANEL.index("store.setConfigConnector(null)", i)


def test_back_returns_to_whoever_opened_the_connector_and_close_sits_beside_it(run):
    """Operator 2026-10-25: «si yo voy a un sitio y le doy a volver, quiero volver desde donde venía». From the
    Contactos card's «Gestionar», «Volver» used to drop the person on the connectors list, with the only way
    out a ✕ at the top of the screen. Now the done step says WHERE it goes back to and offers «Cerrar» beside it;
    the breadcrumb stays the way to roam the section."""
    assert "config.cxw.back_to{&quot;name&quot;:&quot;Contactos&quot;}" in run["doneFrom"]
    for html in (run["doneFrom"], run["doneAnon"], run["doneList"]):
        assert 'data-cx-done="1"' in html and 'data-cx-close="1"' in html
        assert 'class="cf-crumb-back" data-cx-back="1"' in html, "the breadcrumb still leads to the list"
    assert "config.cxw.done_back" in run["doneAnon"] and "config.cxw.done_back" in run["doneList"]


def test_a_caller_outside_the_panel_makes_back_close_it():
    # The card names itself in the one door every card uses…
    desk = (APP / "widgets" / "desktop.js").read_text(encoding="utf-8")
    assert re.search(r'openConnector:.*?from: \(e && e\.name\) \|\| ""', desk, re.S)
    assert "store.setConfigFrom(" in (APP / "main.js").read_text(encoding="utf-8")
    # …the panel remembers it only when opened ON a connector, and «Volver» then closes instead of listing.
    assert 'cxReturn = { from: from || "" }' in PANEL
    assert re.search(r'\[data-cx-done\].*?if \(cxReturn\) close\(\);', PANEL, re.S)
    assert re.search(r'\[data-cx-back\].*?cxReturn = null', PANEL), "taking the breadcrumb drops the return"


def test_every_form_stacks_its_fields_and_keeps_its_actions_on_the_left(run):
    """Operator 2026-10-25: «estructurado, alineado, con subsecciones… alineado a la izquierda». A field is a
    label ABOVE its control (`cf-field`), a form's buttons sit in one left-aligned `cf-acts` row — never the
    label-left/control-right settings row whose button floated to the right edge."""
    for name, html in run["forms"].items():
        if name == "tgQr":
            continue   # a code on screen IS the form (next test)
        assert "cf-row2" not in html, name
        assert 'class="cf-acts"' in html, name
    for name in ("email", "onedrive", "architect", "meshkore"):
        assert '<label class="cf-field"><span class="cf-field-l">' in run["forms"][name], name
    assert '<h5 class="cf-sub-h">' in run["forms"]["meshkore"], "adding a cluster is its own subsection"


def test_a_code_on_screen_replaces_the_button_and_sentence_that_asked_for_it(run):
    """The screenshot: «Pulsa Conectar y escanea…», the button, then the QR and the SAME path again under it.
    Now the button shows only before there is a code; with one, the code sits on the left with its how-to."""
    assert 'data-act="connect"' in run["forms"]["tgShipped"] and "config.cxw.telegram.shipped" in run["forms"]["tgShipped"]
    assert 'data-act="connect"' not in run["forms"]["tgQr"] and "config.cxw.telegram.shipped" not in run["forms"]["tgQr"]
    assert '<div class="cf-wiz-qr"><img' in run["tgQrPage"] and "cf-wiz-qr-text" in run["tgQrPage"]


def test_every_page_ends_on_the_way_out_and_the_last_step_has_no_lone_back(run):
    for html in (run["wa0"], run["wa1"], run["waLast"], run["doneList"]):
        assert html.count('data-cx-close="1"') == 1 and html.count('data-cx-done="1"') == 1
        assert html.rindex("cf-wiz-foot") > html.rindex("cf-wiz-steps") if "cf-wiz-steps" in html else True
    # Step 1 of 2 offers Next; the last step's way back is the ticked rail, not a ghost «Atrás» under «Conectar».
    assert 'class="cf-btn" data-cx-step="1"' in run["wa0"]
    assert 'cf-btn cf-btn-ghost" data-cx-step=' not in run["waLast"] and "cf-wiz-nav" not in run["waLast"]


def test_the_connectors_list_has_close_beside_refresh():
    assert re.search(r'cf-cx-foot.*?cf-cx-refresh.*?data-cx-close="1"', PANEL, re.S)
    assert re.search(r'\[data-cx-close\]"\)\.forEach\(b => b\.onclick = \(\) => close\(\)\)', PANEL)
