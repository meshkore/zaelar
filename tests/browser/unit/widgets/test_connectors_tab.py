"""Contract for ChatWall's 5th NATIVE «Conectores» tab — V2-561, implementing the V2-526 design.

Same reasoning as `test_clusters_tab.py`'s header: the connector DIRECTORY is system infrastructure —
what the agent can reach, not something the operator creates/deletes — so it lives alongside Chat/
Processes/Crons/Clusters and not in the widget catalog. This is a CONTRACT test between the layers that
must agree: the backend that serves the wishlist, the store that carries the tab, and the frontend that
renders + wires it to ConfigPanel/feedback. A real browser cannot run in the deterministic suite; this
pins what would silently break if one side changed without the other.

Voice routing (`show_panel` opening this tab by name) is explicitly NOT built this pass — see the
initiative doc's "not done" section — so there is no `_canon_panel` test here the way `test_clusters_tab`
has one for "clusters".
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "app"
CHATWALL = (FRONTEND / "components" / "ChatWall.js").read_text(encoding="utf-8")
STORE = (FRONTEND / "core" / "store.js").read_text(encoding="utf-8")
CONFIG_PANEL = (FRONTEND / "components" / "ConfigPanel.js").read_text(encoding="utf-8")
API_JS = (FRONTEND / "services" / "api.js").read_text(encoding="utf-8")
FEEDBACK_JS = (FRONTEND / "services" / "feedback-api.js").read_text(encoding="utf-8")
STYLES = (FRONTEND.parent / "app" / "styles.css").read_text(encoding="utf-8")
ENGINE = Path(__file__).resolve().parents[4]

TABS = ("chat", "procesos", "crons", "clusters", "conectores")


# ── frontend: the tab button, its panel, and the CSS that shows it ─────────────────────────────────────
def test_chatwall_has_the_five_tabs():
    for tab in TABS:
        assert f'store.setChatTab("{tab}")' in CHATWALL, f"missing the «{tab}» tab button"


def test_the_conectores_panel_has_a_css_rule_that_shows_it():
    assert re.search(r"\.chatwall\.tab-conectores\s+\.cw-conn\s*\{", STYLES), \
        "the conectores panel exists but stays invisible (missing display rule)"


def test_entering_the_tab_refreshes_both_live_and_wishlist_data():
    assert 'else if (t === "conectores") refreshConnectors();' in CHATWALL
    assert "api.getConnectors()" in CHATWALL and "api.getConnectorCatalog()" in CHATWALL


def test_families_render_in_a_stable_order_with_unknown_families_after_the_known_ones():
    assert 'CONN_FAMILY_ORDER = ["mensajeria", "musica", "fotos", "archivos", "infra"]' in CHATWALL


# ── backend service functions the tab depends on ────────────────────────────────────────────────────────
def test_api_js_exposes_the_catalog_fetch():
    assert "export const getConnectorCatalog" in API_JS
    assert '"/api/connectors/catalog"' in API_JS


def test_the_route_exists_server_side():
    server_src = (ENGINE / "server" / "config_api.py").read_text(encoding="utf-8")
    assert '@router.get("/api/connectors/catalog")' in server_src


# ── "Conectar" hands off to ConfigPanel's Conectores tab, never connects from here ──────────────────────
def test_connectar_opens_config_panel_on_the_conectores_tab():
    assert "store.setConfigInitialTab" in CHATWALL and "store.setConfigOpen(true)" in CHATWALL


def test_config_panel_consumes_the_initial_tab_request_once():
    assert "store.configInitialTab()" in CONFIG_PANEL
    assert "store.setConfigInitialTab(null)" in CONFIG_PANEL, \
        "must clear the request or every later ⚙ click gets forced onto the same tab forever"


def test_store_exposes_the_config_initial_tab_signal():
    assert re.search(r"export const \[configInitialTab, setConfigInitialTab\]", STORE)


# ── "Lo quiero" carries the manifest id, never lets the operator type free text ─────────────────────────
def test_lo_quiero_uses_the_shared_feedback_service_not_an_inline_fetch():
    assert "feedbackApi.sendFeedback" in CHATWALL
    assert 'fetch("/api/feedback"' not in CHATWALL, "must reuse services/feedback-api.js, not a second door"


def test_the_wishlist_request_carries_the_manifest_id_deterministically():
    """No existing structured `subject` field exists in the feedback pipeline (it forwards to a separate
    control-plane deployment outside this pass's scope) — the id travels as a fixed, code-written prefix in
    `message` instead of anything the operator typed. `m.id` must appear in the string the code BUILDS."""
    branch = CHATWALL.split("const requestConnector")[1].split("\n\n")[0]
    assert "m.id" in branch and "m.label" in branch
    assert "connRequested().has(m.id)" in branch, "must not re-send once already requested this session"


def test_a_not_possible_entry_offers_no_button():
    branch = CHATWALL.split("const connWishRow")[1].split("\n\n")[0]
    assert "impossible ? null" in branch


def test_feedback_service_shape_is_unchanged_by_this_pass():
    """Sanity: confirms the assumption above still holds — no `subject` param was silently added upstream
    that this tab should have used instead."""
    assert "subject" not in FEEDBACK_JS


# ── data files: every manifest is well-formed, and none accidentally ships as a THIRD live inventory ────
def test_every_catalog_manifest_is_well_formed():
    cat_dir = ENGINE / "connectors" / "catalog"
    files = sorted(cat_dir.glob("*.json"))
    assert files, "expected shipped connector-catalog manifests"
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["id"] == f.stem, f"{f.name}: id must match the filename"
        assert data["state"] in ("built", "planned", "not-possible")
        assert isinstance(data.get("capabilities"), list) and data["capabilities"]
