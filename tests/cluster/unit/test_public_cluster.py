"""PUBLIC (tokenless) clusters and NATIVE network surface — V2-086.

Change context (2026-08-01): the operator pasted the official MeshKore invitation for a public cluster, and the
system did nothing. There was NOT a single cause: there were FOUR stacked blockers —(1) the `connect_cluster`
tool was gated on having the `cluster-registro` widget open, (2) its schema required `token`, (3) its description
by design rejected pasted blocks with instructions, and (4) the transport always sent `token=` and never
`vis=public`. These tests pin down the aspects that can be verified without a network.

What is protected here:
  · A PUBLIC cluster is represented and connected without a token; a PRIVATE one still requires it.
  · The connection URL OMITS the `token` key in public mode (sending it empty is not equivalent: the server reads it
    as failed authentication, not as anonymous access).
  · A reused alias NEVER overwrites another cluster's credentials.
"""
import pytest

from connectors.meshkore import store
from connectors.meshkore.client import MeshKoreClient


# ── transport: two connection modes ─────────────────────────────────────────────────────────────────────────
def test_public_url_omits_the_token_key():
    c = MeshKoreClient("commons", "c_abc", token="", handle="zaelar", vis="public")
    url = c._url()
    assert c.public is True
    assert "vis=public" in url and "agent=zaelar" in url
    assert "token" not in url, "un cluster público NO debe llevar la clave token, ni siquiera vacía"


def test_private_url_still_carries_the_token():
    c = MeshKoreClient("privado", "c_abc", token="t0k3n", handle="zaelar")
    url = c._url()
    assert c.public is False
    assert "token=t0k3n" in url and "vis=" not in url


def test_id_without_token_is_treated_as_public():
    """A cluster_id without a token can only be an open cluster — not a private one missing its credential."""
    assert MeshKoreClient("x", "c_abc", token="").public is True


# ── credential resolution ───────────────────────────────────────────────────────────────────────────────────
def test_resolve_accepts_public_without_token(monkeypatch):
    monkeypatch.setattr(store, "take_staged", lambda name: None)
    monkeypatch.setattr(store, "get_cluster", lambda name: None)
    creds = store.resolve("commons", "c_abc", token="", vis="public")
    assert creds and creds["cluster_id"] == "c_abc" and creds["vis"] == "public"


def test_resolve_still_requires_a_token_for_private(monkeypatch):
    """Without a token and without `vis=public`, no connection is possible: an anonymous access path to a private
    cluster must not be invented."""
    monkeypatch.setattr(store, "take_staged", lambda name: None)
    monkeypatch.setattr(store, "get_cluster", lambda name: None)
    assert store.resolve("privado", "c_abc", token="") is None


# ── alias collision guard ───────────────────────────────────────────────────────────────────────────────────
def test_alias_collision_never_overwrites_another_cluster(monkeypatch):
    """Caught through live testing: when connecting to Commons, the model chose the default alias `meshcore`, which
    already belonged to the operator's PRIVATE cluster — saving it there would have overwritten its token. A
    model chooses the alias, so uniqueness is guaranteed in code rather than by trusting it to choose correctly."""
    monkeypatch.setattr(store, "_read", lambda: {"meshcore": {"cluster_id": "c_privado", "token": "t"}})
    assert store.unique_name("meshcore", "c_publico") == "meshcore-2"
    # …but reconnecting to the SAME cluster reuses its alias (it is not a collision).
    assert store.unique_name("meshcore", "c_privado") == "meshcore"
    # …and an available alias is preserved as is.
    assert store.unique_name("commons", "c_publico") == "commons"


# ── the network is a NATIVE surface, not a widget ────────────────────────────────────────────────────────────
def test_cluster_registro_widget_is_gone():
    """The NETWORK is system infrastructure (the «Clusters» tab), not a user widget that the operator
    creates/deletes. If someone recreates it, this test will flag it."""
    from widgets import runtime, registry
    assert runtime.get("cluster-registro") is None
    assert "cluster-registro" not in registry._BUILTINS


def test_native_clusters_surface_owns_its_confirm():
    """Connecting to a network requests deterministic Yes/No confirmation, and that confirmation lives in the
    native surface — not in a canvas card (which no longer exists)."""
    from widgets import confirm
    assert confirm.NATIVE_CLUSTERS == "clusters"
    confirm.request("data", confirm.NATIVE_CLUSTERS, "¿Conectar?",
                    op={"action": "connect_cluster", "payload": {"name": "commons"}})
    try:
        assert confirm.NATIVE_CLUSTERS in confirm.pending()
        p = confirm.resolve(confirm.NATIVE_CLUSTERS, True)
        assert p and p["op"]["action"] == "connect_cluster"
    finally:
        confirm.resolve(confirm.NATIVE_CLUSTERS, False)
