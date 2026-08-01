"""Clusters PÚBLICOS (tokenless) y superficie NATIVA de red — V2-086.

Contexto del cambio (2026-08-01): el operador pegó la invitación oficial de MeshKore a un cluster público y el
sistema no hizo nada. La causa NO era una sola: había CUATRO bloqueos apilados —(1) la tool `connect_cluster`
estaba gateada a tener abierto el widget `cluster-registro`, (2) su esquema exigía `token`, (3) su descripción
rechazaba por diseño los bloques pegados con instrucciones, y (4) el transporte siempre mandaba `token=` y nunca
`vis=public`. Estos tests fijan los que son verificables sin red.

Lo que se defiende aquí:
  · Un cluster PÚBLICO se expresa y se conecta sin token; uno PRIVADO sigue necesitándolo.
  · La URL de conexión OMITE la clave `token` en modo público (mandarla vacía no es equivalente: el servidor lo
    lee como auth fallida, no como entrada anónima).
  · Un alias reutilizado NUNCA pisa las credenciales de otro cluster.
"""
import pytest

from connectors.meshkore import store
from connectors.meshkore.client import MeshKoreClient


# ── transporte: dos modos de conexión ───────────────────────────────────────────────────────────────────────
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
    """Un cluster_id sin token solo puede ser un cluster abierto — no un privado al que le falta la credencial."""
    assert MeshKoreClient("x", "c_abc", token="").public is True


# ── resolución de credenciales ──────────────────────────────────────────────────────────────────────────────
def test_resolve_accepts_public_without_token(monkeypatch):
    monkeypatch.setattr(store, "take_staged", lambda name: None)
    monkeypatch.setattr(store, "get_cluster", lambda name: None)
    creds = store.resolve("commons", "c_abc", token="", vis="public")
    assert creds and creds["cluster_id"] == "c_abc" and creds["vis"] == "public"


def test_resolve_still_requires_a_token_for_private(monkeypatch):
    """Sin token y sin `vis=public` no hay conexión posible: no se debe inventar una entrada anónima a un
    cluster privado."""
    monkeypatch.setattr(store, "take_staged", lambda name: None)
    monkeypatch.setattr(store, "get_cluster", lambda name: None)
    assert store.resolve("privado", "c_abc", token="") is None


# ── guard de colisión de alias ──────────────────────────────────────────────────────────────────────────────
def test_alias_collision_never_overwrites_another_cluster(monkeypatch):
    """Cazado probando en vivo: al conectar a Commons el modelo eligió el alias por defecto `meshcore`, que ya
    era el del cluster PRIVADO del operador — guardarlo ahí habría sobrescrito su token. El alias lo elige un
    modelo, así que la unicidad se garantiza en código, no confiando en que acierte."""
    monkeypatch.setattr(store, "_read", lambda: {"meshcore": {"cluster_id": "c_privado", "token": "t"}})
    assert store.unique_name("meshcore", "c_publico") == "meshcore-2"
    # …pero reconectar el MISMO cluster reutiliza su alias (no es una colisión).
    assert store.unique_name("meshcore", "c_privado") == "meshcore"
    # …y un alias libre se respeta tal cual.
    assert store.unique_name("commons", "c_publico") == "commons"


# ── la red es superficie NATIVA, no un widget ───────────────────────────────────────────────────────────────
def test_cluster_registro_widget_is_gone():
    """La RED es infraestructura del sistema (pestaña «Clusters»), no un widget de usuario que el operador
    cree/borre. Si alguien lo re-crea, este test lo canta."""
    from widgets import runtime, registry
    assert runtime.get("cluster-registro") is None
    assert "cluster-registro" not in registry._BUILTINS


def test_native_clusters_surface_owns_its_confirm():
    """Conectarse a una red pide confirmación Sí/No determinista, y esa confirmación vive en la superficie
    nativa — no en una tarjeta del canvas (que ya no existe)."""
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
