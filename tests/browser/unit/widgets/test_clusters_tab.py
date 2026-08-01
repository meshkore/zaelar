"""Contrato de la 4ª pestaña NATIVA «Clusters» del ChatWall — V2-086.

La RED (hoy MeshKore; mañana quizá otros proveedores) es infraestructura del SISTEMA: es lo que conecta al agente
con el exterior. Por eso vive junto a Chat/Procesos/Crons y NO en el catálogo de widgets, que es para piezas que
el operador crea y borra.

Esto es un test de CONTRATO entre las tres capas que tienen que estar de acuerdo (mismo espíritu que
`test_system_surfaces_sync.py`): el backend que sirve los datos, el ruteo que abre la pestaña por voz, y el
frontend que la pinta. Un test de navegador REAL no puede correr en la batería determinista, así que aquí se fija
lo que sí es verificable sin Chromium — y lo que se rompería en silencio si alguien tocara un lado y no el otro.
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


# ── ruteo por voz: la pestaña se abre como las otras tres ────────────────────────────────────────────────────
def test_show_panel_knows_the_clusters_tab():
    from nucleo.flash import router
    assert router._canon_panel("clusters") == "clusters"
    for word in ("cluster", "meshkore", "la red", "la malla", "peers", "conexiones"):
        assert router._canon_panel(word) == "clusters", word


def test_show_panel_still_routes_the_other_tabs():
    """El ruteo de la red no puede haberse llevado por delante Procesos/Crons/Chat."""
    from nucleo.flash import router
    assert router._canon_panel("crons") == "crons"
    assert router._canon_panel("recordatorios programados") == "crons"
    assert router._canon_panel("chat") == "chat"
    assert router._canon_panel("workers") == "procesos"


def test_the_tool_description_mentions_the_tab():
    """Si la pestaña no está en la descripción, el modelo no sabe que puede abrirla: existir no basta."""
    from nucleo.flash import router
    fn = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "show_panel")
    assert "clusters" in fn["description"].lower()
    assert "clusters" in fn["parameters"]["properties"]["panel"]["description"]


# ── frontend: las cuatro pestañas, su panel y su CSS ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("tab", TABS)
def test_chatwall_has_the_four_tabs(tab):
    assert f'store.setChatTab("{tab}")' in CHATWALL, f"falta el botón de la pestaña «{tab}»"


@pytest.mark.parametrize("tab", TABS)
def test_every_tab_has_a_css_rule_that_shows_it(tab):
    """Sin la regla `.chatwall.tab-X .cw-X{display:flex}` la pestaña existe pero se queda invisible — un fallo
    mudo que no rompe nada y no se ve hasta abrirla."""
    panel = "list" if tab == "chat" else ("proc" if tab == "procesos" else tab)
    assert re.search(rf"\.chatwall\.tab-{tab}\s+\.cw-{panel}\s*\{{", STYLES), f"la pestaña «{tab}» no se muestra"


def test_entering_the_tab_refreshes_its_data():
    assert 'else if (t === "clusters") store.fetchClusters();' in CHATWALL


def test_store_exposes_the_cluster_controls():
    # Las señales se exportan destructuradas (`export const [clusters, setClusters] = …`), las funciones no →
    # se busca el símbolo tras `export const`, en cualquiera de las dos formas.
    for sym in ("clusters", "setClusters", "fetchClusters", "clusterConnect", "clusterDisconnect",
                "clusterConfirm", "setClusterConfirm", "clusterConfirmResolve"):
        assert re.search(rf"export const (\[[^\]]*\b{sym}\b[^\]]*\]|{sym}\b)", STORE), f"el store no expone {sym}"


def test_the_tab_shows_state_peers_and_traffic_but_no_conversation():
    """Lo que el operador pidió: nombres, conexiones y contador. NADA de histórico de mensajes — los clusters
    tienen su propio monitor y duplicarlo aquí sería una segunda fuente de verdad."""
    assert "cl-row" in CHATWALL and "cl-meta" in CHATWALL
    assert "c.connected" in CHATWALL and "c.online" in CHATWALL and "c.msgs" in CHATWALL
    assert "pushChat" not in CHATWALL.split("cw-clusters")[-1], "la pestaña no debe volcar conversación"


# ── el confirm de CONECTAR vive en la superficie nativa, no en una tarjeta ───────────────────────────────────
def test_connect_confirm_is_routed_to_the_native_tab():
    from widgets import confirm
    assert confirm.NATIVE_CLUSTERS == "clusters"
    assert 'd.id === "clusters"' in SSE, "el SSE no rutea el confirm de red a la pestaña"
    assert "setClusterConfirm" in SSE and "clusterConfirmResolve" in CHATWALL


def test_cluster_events_refresh_the_tab_without_touching_the_chat():
    """El muro de chat es SOLO operador ↔ zaelar (regla del operador): el tráfico de cluster refresca la lista,
    nunca se vuelca en la conversación personal."""
    branch = SSE.split('d.kind === "cluster"')[-1].split("}")[0]
    assert "fetchClusters" in branch
    assert "pushChat" not in branch


# ── backend: el contrato de datos que consume la pestaña ─────────────────────────────────────────────────────
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
    assert "token" not in json.dumps(row), "el token NUNCA sale al frontend"


def test_a_credentialled_but_offline_cluster_still_shows_up(monkeypatch):
    """Antes solo se listaban los clientes vivos, así que un cluster caído DESAPARECÍA de la lista justo cuando
    más importaba saber que existe."""
    import connectors.meshkore as _mk
    m = _mk.get_manager()
    monkeypatch.setattr(m, "_clients", {}, raising=False)
    monkeypatch.setattr("connectors.meshkore.store.load_clusters",
                        lambda: {"guardado": {"cluster_id": "c_x", "token": "t", "handle": "zaelar"}})
    rows = m.clusters()
    assert [r["name"] for r in rows] == ["guardado"]
    assert rows[0]["connected"] is False and rows[0]["public"] is False
