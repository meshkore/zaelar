#
# Connectors registry — inventario ÚNICO y tipado de TODOS los conectores del agente (V2-083).
#
# Antes el catálogo estaba disperso (config/connectors.py=mensajería, spotify/auth, meshkore, architect). Esto lo
# unifica en UN punto para la pestaña "Conectores" de Configuración: cada conector con su familia, método de auth,
# estado (conectado/autenticado) y qué credenciales tiene puestas (REDACTADAS). Los conectores son NATIVOS: el
# código de conexión vive en `connectors/<x>/`, pero TODA su configuración/credenciales es DINÁMICA, visible,
# revocable y autenticable desde el frontend — NADA en `.env` (env solo fallback power-user).
#
# Read-only: este módulo solo LEE estado. Las ESCRITURAS (connect/disconnect/revoke) van por los endpoints ya
# existentes de cada familia (`/api/messaging/*`, `/api/spotify/*`, `/api/meshkore/*`) + los de architect (V2-083).
#
from __future__ import annotations

# Descriptor de cada conector:
#   id · label · family (mensajeria|musica|infra) · auth (qr|app-password|oauth|token|cluster)
#   connected (bool) · detail (str humano) · config (dict REDACTADO) · [clusters] (solo meshkore)


def _messaging() -> list[dict]:
    out = []
    try:
        from config import connectors as cfg
        from connectors.messaging import control, store
        live = store.load().get("platforms", {})
        meta = {
            "whatsapp": ("WhatsApp", "qr"),
            "telegram": ("Telegram", "app-password"),   # api_id/api_hash → luego QR
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
        # `clusters()` da la lista de clusters conocidos/conectados; la normalizamos a {name, connected}.
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


# Orden estable por familia (mensajería → música → infra) para la pestaña.
def descriptors() -> list[dict]:
    """Inventario completo de conectores con estado + config redactada. Cada fuente aislada (un conector roto no
    tumba el registro)."""
    return [*_messaging(), *_music(), *_architect(), *_meshkore()]
