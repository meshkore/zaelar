"""Contract for ChatWall's 4th NATIVE «Clusters» tab — V2-086.

The NETWORK (MeshKore today; perhaps other providers tomorrow) is SYSTEM infrastructure: it is what connects the agent
to the outside world. That is why it lives alongside Chat/Processes/Crons and NOT in the widget catalog, which is for
pieces the operator creates and deletes.

This is a CONTRACT test between the three layers that must agree (in the same spirit as
`test_system_surfaces_sync.py`): the backend that serves the data, the routing that opens the tab by voice, and the
frontend that renders it. A REAL browser test cannot run in the deterministic suite, so this specifies here
what can be verified without Chromium — and what would silently break if someone changed one side but not the other.
"""
import json
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "app"
CHATWALL = (FRONTEND / "components" / "ChatWall.js").read_text(encoding="utf-8")
STORE = (FRONTEND / "core" / "store.js").read_text(encoding="utf-8")
SSE = (FRONTEND / "services" / "sse.js").read_text(encoding="utf-8")
STYLES = (FRONTEND.parent / "app" / "styles.css").read_text(encoding="utf-8")

TABS = ("chat", "procesos", "crons", "clusters")


# ── voice routing: the tab opens like the other three ─────────────────────────────────────────────────────────
def test_show_panel_knows_the_clusters_tab():
    from nucleo.flash import router
    assert router._canon_panel("clusters") == "clusters"
    for word in ("cluster", "meshkore", "la red", "la malla", "peers", "conexiones"):
        assert router._canon_panel(word) == "clusters", word


def test_show_panel_still_routes_the_other_tabs():
    """Network routing must not have broken Processes/Crons/Chat."""
    from nucleo.flash import router
    assert router._canon_panel("crons") == "crons"
    assert router._canon_panel("recordatorios programados") == "crons"
    assert router._canon_panel("chat") == "chat"
    assert router._canon_panel("workers") == "procesos"


def test_the_tool_description_mentions_the_tab():
    """If the tab is not in the description, the model does not know it can open it: existing is not enough."""
    from nucleo.flash import router
    fn = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "show_panel")
    assert "clusters" in fn["description"].lower()
    assert "clusters" in fn["parameters"]["properties"]["panel"]["description"]


# ── frontend: the four tabs, their panel, and their CSS ──────────────────────────────────────────────────────
@pytest.mark.parametrize("tab", TABS)
def test_chatwall_has_the_four_tabs(tab):
    assert f'store.setChatTab("{tab}")' in CHATWALL, f"falta el botón de la pestaña «{tab}»"


@pytest.mark.parametrize("tab", TABS)
def test_every_tab_has_a_css_rule_that_shows_it(tab):
    """Without the `.chatwall.tab-X .cw-X{display:flex}` rule, the tab exists but remains invisible — a silent failure
    that breaks nothing and is not visible until the tab is opened."""
    panel = "list" if tab == "chat" else ("proc" if tab == "procesos" else tab)
    assert re.search(rf"\.chatwall\.tab-{tab}\s+\.cw-{panel}\s*\{{", STYLES), f"la pestaña «{tab}» no se muestra"


def test_entering_the_tab_refreshes_its_data():
    assert 'else if (t === "clusters") store.fetchClusters();' in CHATWALL


def test_store_exposes_the_cluster_controls():
    # Signals are exported destructured (`export const [clusters, setClusters] = …`), functions are not →
    # search for the symbol after `export const`, in either form.
    for sym in ("clusters", "setClusters", "fetchClusters", "clusterConnect", "clusterDisconnect",
                "clusterConfirm", "setClusterConfirm", "clusterConfirmResolve"):
        assert re.search(rf"export const (\[[^\]]*\b{sym}\b[^\]]*\]|{sym}\b)", STORE), f"el store no expone {sym}"


def test_the_tab_shows_state_peers_and_traffic_but_no_conversation():
    """What the operator requested: names, connections, and a counter. NO message history — clusters
    have their own monitor, and duplicating it here would create a second source of truth."""
    assert "cl-row" in CHATWALL and "cl-meta" in CHATWALL
    assert "c.connected" in CHATWALL and "c.online" in CHATWALL and "c.msgs" in CHATWALL
    assert "pushChat" not in CHATWALL.split("cw-clusters")[-1], "la pestaña no debe volcar conversación"


# ── the CONNECT confirmation lives on the native surface, not in a card ───────────────────────────────────────
def test_connect_confirm_is_routed_to_the_native_tab():
    from widgets import confirm
    assert confirm.NATIVE_CLUSTERS == "clusters"
    assert 'd.id === "clusters"' in SSE, "SSE does not route the network confirmation to the tab"
    assert "setClusterConfirm" in SSE and "clusterConfirmResolve" in CHATWALL


def test_cluster_events_refresh_the_tab_without_touching_the_chat():
    """The chat wall is ONLY operator ↔ zaelar (the operator's rule): cluster traffic refreshes the list,
    and is never poured into the personal conversation."""
    branch = SSE.split('d.kind === "cluster"')[-1].split("}")[0]
    assert "fetchClusters" in branch
    assert "pushChat" not in branch


# ── backend: the data contract consumed by the tab ───────────────────────────────────────────────────────────
def test_status_rows_carry_everything_the_tab_paints(monkeypatch):
    import connectors.meshkore as _mk
    from connectors.meshkore import manager as _mgr

    class _FakeClient:
        name, cluster_id, handle = "commons", "c_abc", "zaelar"
        connected, public = True, True
        online, msgs_in, msgs_out = {"zalo"}, 2, 3

    m = _mk.get_manager()
    monkeypatch.setattr(m, "_clients", {"commons": _FakeClient()}, raising=False)
    monkeypatch.setattr("connectors.meshkore.store.load_clusters", lambda: {})
    row = m.clusters()[0]
    for k in ("name", "connected", "public", "handle", "online", "cluster_id", "msgs"):
        assert k in row, f"falta {k}"
    assert row["msgs"] == 5, "el contador debe sumar entrada y salida"
    assert "token" not in json.dumps(row), "the token NEVER reaches the frontend"


def test_a_credentialled_but_offline_cluster_still_shows_up(monkeypatch):
    """Previously only live clients were listed, so a failed cluster DISAPPEARED from the list exactly when
    knowing it existed mattered most."""
    import connectors.meshkore as _mk
    m = _mk.get_manager()
    monkeypatch.setattr(m, "_clients", {}, raising=False)
    monkeypatch.setattr("connectors.meshkore.store.load_clusters",
                        lambda: {"guardado": {"cluster_id": "c_x", "token": "t", "handle": "zaelar"}})
    rows = m.clusters()
    assert [r["name"] for r in rows] == ["guardado"]
    assert rows[0]["connected"] is False and rows[0]["public"] is False
