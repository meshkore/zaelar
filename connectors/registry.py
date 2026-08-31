#
# Connectors registry — SINGLE typed inventory of ALL agent connectors (V2-083).
#
# Previously the catalog was scattered (config/connectors.py=messaging, spotify/auth, meshkore, architect). This
# unifies it in ONE point for the Configuration "Connectors" tab: each connector with family, auth method, state
# (connected/authenticated), and which credentials are set (REDACTED). Connectors are NATIVE: connection code lives
# in `connectors/<x>/`, but ALL configuration/credentials are DYNAMIC, visible, revocable, and authenticatable from
# the frontend — NOTHING in `.env` (env only as power-user fallback).
#
# Read-only: this module only READS state. WRITES (connect/disconnect/revoke) go through the existing endpoints for
# each family (`/api/messaging/*`, `/api/spotify/*`, `/api/meshkore/*`) + architect endpoints (V2-083).
#
from __future__ import annotations

# Descriptor for each connector:
#   id · label · family (mensajeria|musica|infra) · auth (qr|app-password|oauth|token|cluster)
#   connected (bool) · detail (human str) · config (REDACTED dict) · [clusters] (meshkore only)


def _messaging() -> list[dict]:
    out = []
    try:
        from config import connectors as cfg
        from connectors.messaging import control, store
        live = store.load().get("platforms", {})
        meta = {
            "whatsapp": ("WhatsApp", "qr"),
            "telegram": ("Telegram", "app-password"),   # api_id/api_hash → then QR
            "email": ("Email", "app-password"),
        }
        for p in control.PLATFORMS:
            pub = cfg.public(p)
            lv = live.get(p) or {}
            status = str(lv.get("status") or ("off" if not pub.get("enabled") else "starting"))
            label, auth = meta.get(p, (p.title(), "app-password"))
            out.append({"id": p, "label": label, "family": "mensajeria", "auth": auth,
                        "connected": status == "connected", "status": status,
                        "detail": str(lv.get("detail") or ""), "qr": lv.get("qr"), "config": pub})
    except Exception as e:
        out.append({"id": "messaging", "label": "Messaging", "family": "mensajeria", "auth": "app-password",
                    "connected": False, "status": "error", "detail": f"registry unavailable: {e}", "config": {}})
    return out


def _music() -> list[dict]:
    try:
        from connectors.spotify import auth
        st = auth.status() or {}
        return [{"id": "spotify", "label": "Spotify", "family": "musica", "auth": "oauth",
                 "connected": bool(st.get("logged_in")), "status": "connected" if st.get("logged_in") else "off",
                 "detail": "Play and control Spotify (OAuth).", "config": st}]
    except Exception as e:
        return [{"id": "spotify", "label": "Spotify", "family": "musica", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _architect() -> list[dict]:
    try:
        from config import connectors as cfg
        from connectors.architect import client
        pub = cfg.public("architect")
        connected = client.configured()
        return [{"id": "architect", "label": "Architect (code daemon)", "family": "infra", "auth": "token",
                 "connected": connected, "status": "connected" if connected else "off",
                 "detail": "Code projects/agents on the MeshKore daemon. Dynamic token (revocable).",
                 "config": pub}]
    except Exception as e:
        return [{"id": "architect", "label": "Architect", "family": "infra", "auth": "token",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _meshkore() -> list[dict]:
    try:
        from connectors import meshkore
        mgr = meshkore.get_manager()
        clusters = mgr.clusters() if mgr else []
        # `clusters()` gives the known/connected cluster list; normalize it to {name, connected}.
        norm = []
        for c in (clusters or []):
            if isinstance(c, dict):
                norm.append({"name": c.get("name") or c.get("id") or "?",
                             "connected": bool(c.get("connected", True))})
            else:
                norm.append({"name": str(c), "connected": True})
        return [{"id": "meshkore", "label": "MeshKore (cluster / team)", "family": "infra", "auth": "cluster",
                 "connected": bool(norm), "status": "connected" if norm else "off",
                 "detail": "Access to the team/cluster via cluster_id + token (dynamic, revocable).",
                 "clusters": norm, "config": {}}]
    except Exception as e:
        return [{"id": "meshkore", "label": "MeshKore", "family": "infra", "auth": "cluster",
                 "connected": False, "status": "error", "detail": str(e), "clusters": [], "config": {}}]


# Stable family order (messaging -> music -> infra) for the tab.
def descriptors() -> list[dict]:
    """Complete connector inventory with state + redacted config. Each source is isolated (a broken connector does
    not take down the registry)."""
    return [*_messaging(), *_music(), *_architect(), *_meshkore()]
