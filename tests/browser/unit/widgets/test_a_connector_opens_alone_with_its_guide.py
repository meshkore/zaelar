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
globalThis.location = { origin: "https://local.zaelar.com:44317" };
const W = await import(process.argv[1]);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const ui = { t: (k, p) => k + (p ? JSON.stringify(p) : ""), esc, badge: c => `[${c.connected ? "on" : "off"}]` };
const cs = JSON.parse(process.argv[2]);
const out = {
  list: W.connectorList(W.groupGoogle(cs), [["mensajeria", "Mensajería"], ["google", "Google"], ["agenda", "Calendario"]], ui),
  wa0: W.connectorWizard(cs[0], 0, "<FORM-wa>", "Mensajería", ui),
  wa1: W.connectorWizard(cs[0], 1, "<FORM-wa>", "Mensajería", ui),
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
       "config": {"app_configured": False, "redirect_uris": ["https://local.zaelar.com:44317/api/calendar/callback"]}},
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


def test_the_list_opens_nothing_and_offers_one_row_per_connector(run):
    assert run["list"].count('class="cf-cx-row"') == 3, "WhatsApp, Telegram and the Google services folded into ONE row"
    assert "<FORM" not in run["list"] and "cx_tg_api_id" not in run["list"]


def test_one_connector_has_its_breadcrumb_and_a_way_back(run):
    assert 'data-cx-back="1"' in run["wa0"] and "Mensajería" in run["wa0"] and "<b>WhatsApp</b>" in run["wa0"]
    assert "<FORM-wa>" not in run["wa0"], "the guide comes before the form"


def test_the_last_step_is_the_form_and_the_qr_it_never_drew(run):
    assert "<FORM-wa>" in run["wa1"] and 'src="data:image/png;base64,AAAA"' in run["wa1"]
    assert "config.cxw.qr_scan_whatsapp" in run["wa1"]


def test_a_google_guide_names_its_api_and_the_redirect_to_register(run):
    assert run["gcal"][0]["params"]["api"] == "Google Calendar API"
    assert run["gcal"][1]["code"] == "https://local.zaelar.com:44317/api/calendar/callback"
    assert run["gcalReady"] == [], "a registered app skips the Cloud Console half"


def test_any_google_service_opens_the_one_google_connector_with_that_service_picked_out(run):
    """A card's plug says `google` or `gdrive`; the section opens the single Google entry and highlights that
    service's consent row. A non-Google id opens itself."""
    assert run["focus"][0] == {"focus": "google-account", "service": "google"}
    assert run["focus"][1] == {"focus": "google-account", "service": "gdrive"}
    assert run["focus"][2] == {"focus": "whatsapp", "service": ""}


@pytest.mark.parametrize("bundle", ["es", "en"])
def test_every_step_has_its_words_in_both_bundles(run, bundle):
    b = json.loads((ENGINE / "i18n" / "bundles" / f"{bundle}.json").read_text(encoding="utf-8"))
    keys = {f"config.cxw.{k}.{part}" for k in run["keys"] for part in ("title", "body")}
    keys |= set(re.findall(r'"(config\.cxw\.[a-z_]+)"', WIZ.read_text(encoding="utf-8")))
    keys |= set(re.findall(r'"(config\.cxw\.[a-z_]+)"', PANEL))
    assert not sorted(k for k in keys if k not in b)


def test_the_catalog_names_the_connector_and_the_panel_consumes_it_once():
    assert "openConnectorConfig(c.id)" in CHATWALL and "store.setConfigConnector(id || null)" in CHATWALL
    assert re.search(r"export const \[configConnector, setConfigConnector\]", STORE)
    assert "store.configConnector()" in PANEL and "store.setConfigConnector(null)" in PANEL
    assert "connectorList(view, fams, ui)" in PANEL and "connectorWizard(c, cxStep, connectorForm(c, famTitle)" in PANEL
    assert "const view = groupGoogle(cs);" in PANEL, "the panel renders the Google services as ONE connector"


def test_contacts_finally_has_a_form_and_a_route_behind_it():
    # The consent row of each Google service carries its own act; contacts' is `contacts-connect`.
    assert '"google-contacts": "contacts-connect"' in PANEL and "api.contactsConnect(" in PANEL
    api = (APP / "services" / "api.js").read_text(encoding="utf-8")
    assert '"/api/contacts/connect"' in api
    assert '@router.post("/api/contacts/connect")' in (ENGINE / "connectors/contacts/server_api.py").read_text(encoding="utf-8")


def test_both_requests_are_read_before_either_is_cleared():
    """Clearing `configInitialTab` re-runs the open effect synchronously; a re-run that consumed the connector first
    left the outer run reading null, and the catalog's connector never opened (measured live, 2026-10-04)."""
    i = PANEL.index("const want = store.configInitialTab(), cxWant = store.configConnector();")
    assert i < PANEL.index("store.setConfigInitialTab(null)", i) < PANEL.index("store.setConfigConnector(null)", i)
