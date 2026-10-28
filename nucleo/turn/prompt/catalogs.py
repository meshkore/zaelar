"""The catalogs the turn reads: the connectors' live facts, and which connector or panel an argument names.

Three readers that used to be three flash modules (`connector_briefs`, `connector_canon`, `panel_canon`), each born
to pay a ratchet. Each reads ONE truth: the connector services' own state, the connector catalog
(`connectors/catalog/*.json`), and the ChatWall's declared tabs.

The rule the connector facts share: **a model cannot decline what is not in its prompt** (V2-540). Given the verbs
and no state, the model narrates the outcome it assumes («you have no important messages» over a closed widget).
Each family keeps its own gate, because «does this capability exist» and «what is its state» matter at different
moments.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


# ── the connectors' live facts ────────────────────────────────────────────────────────────────────────────────
def connector_facts(open_ids: set[str], turn_text: str = "") -> str:
    """The connector facts this turn needs, or "". Messaging: its full brief while its card is OPEN, the platforms'
    connection state while it is closed but configured, or when he names a channel nobody linked. Video accounts:
    always while the capability does not exist yet, the account's state while the card is open (V2-603). Google:
    whenever one of its cards is open or it is not fully usable (V2-685). Best-effort."""
    try:
        _msg_on = False
        for mod in ("connectors.whatsapp.service", "connectors.telegram.service"):
            try:
                _msg_on = _msg_on or __import__(mod, fromlist=["x"]).enabled()
            except Exception:  # noqa: BLE001 — an unloadable channel is an unlinked one
                pass
        out = ""
        if _msg_on or _names_a_channel(turn_text):
            from connectors.messaging import brief as _mb
            out = _mb.for_brain() if (_msg_on and "mensajeria" in open_ids) else _mb._platform_states()
        try:
            from connectors.video import service as _vs
            if not _vs.available() or "youtube" in open_ids:
                if (vstate := _vs.brain_state()):
                    out = (out + "\n\n" + vstate) if out else vstate
        except Exception:  # noqa: BLE001 — no video fact is better than a broken turn
            pass
        try:
            from connectors.google import brain as _gb
            if open_ids & {"agenda", "mensajeria", "fotos", "archivos", "youtube"} or not _gb.connected_services():
                if (gstate := _gb.brain_state()):
                    out = (out + "\n\n" + gstate) if out else gstate
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception:  # noqa: BLE001
        return ""


def _names_a_channel(turn_text: str) -> bool:
    """Does his sentence name a messaging platform by its proper name? Names, not verbs: same in every language
    («Reply to Marta on WhatsApp» over an unlinked WhatsApp, dictate-a-reply EN 2026-10-15)."""
    t = str(turn_text or "").lower()
    return "whatsapp" in t or "telegram" in t


# ── which connector an argument names ─────────────────────────────────────────────────────────────────────────
#: The connector catalog: one door to connect a service, the ⚙ «Conectores» section opened on that connector.
_CATALOG = Path(__file__).resolve().parents[3] / "connectors" / "catalog"
_EXTRA = {"google-contacts": ("Google Contacts", ["contactos", "contacts", "google contacts", "people", "agenda de contactos"])}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@lru_cache(maxsize=1)
def _vocab() -> tuple[tuple[str, tuple[str, ...]], ...]:
    rows: dict[str, list[str]] = {}
    for f in sorted(_CATALOG.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a broken manifest is the catalog gate's problem, not routing's
            continue
        # `auth: none` (YouTube audio) has nothing to connect, so it must not shadow the account it is named after
        if m.get("kind") == "connector" and m.get("state") == "built" and m.get("auth") != "none":
            rows[m["id"]] = [m["id"], m.get("label", "")] + list(m.get("capabilities") or [])
    for cid, (label, words) in _EXTRA.items():
        rows.setdefault(cid, [cid, label, *words])
    return tuple((cid, tuple(_norm(w) for w in ws if _norm(w))) for cid, ws in rows.items())


def canon_connector(v) -> str:
    """The connector id the argument names, or '' (the section opens on its list). Exact id first, then a
    whole-phrase match, then the longest catalog word inside it — «google drive» must beat «google»."""
    p = _norm(v)
    if not p:
        return ""
    vocab = _vocab()
    for cid, _ in vocab:
        if p == _norm(cid):
            return cid
    for cid, words in vocab:
        if p in words:
            return cid
    best, size = "", 0
    for cid, words in vocab:
        for w in words:
            if len(w) > size and re.search(rf"\b{re.escape(w)}\b", p):
                best, size = cid, len(w)
    return best


# ── which ChatWall destination a `panel` argument means (V2-728 · V2-744 · V2-761) ─────────────────────────────
def canon_panel(v) -> str:
    """The `show_panel` argument as a ChatWall destination: `chat` · `clusters` · `conectores` · `apps` /
    `apps-custom` · `procesos` · `crons` (repeats) · `programadas` (fires once). «Tareas» no longer means this
    panel (V2-744: his tasks live in the agenda), but the literal `tareas` is still accepted for stored rows.
    Synonyms of the ARGUMENT only; the 'when' lives in the tool description. Default `procesos`."""
    p = str(v or "").strip().lower()
    if p in ("chat", "procesos", "crons", "programadas", "clusters", "conectores", "tareas", "apps", "apps-custom"):
        return "procesos" if p == "tareas" else p
    if any(k in p for k in ("cluster", "meshkore", "mesh", "red", "malla", "peer", "network", "conexion", "conexión")):
        return "clusters"
    if any(k in p for k in ("conector", "connector", "integracion", "integración")):
        return "conectores"
    # AFTER the connectors: «app» is inside «whatsapp», so it is matched as a WORD.
    if re.search(r"\b(apps?|widgets?|aplicacion(es)?|aplicación)\b", p):
        return apps_tab(p)
    # 'periódica' BEFORE 'programada': a recurring job IS scheduled, so the narrower word has to win.
    if any(k in p for k in ("cron", "periodic", "periódic", "recurren", "cada semana", "cada dia", "cada día",
                            "semanal", "diaria", "diario", "mensual", "repit", "repet")):
        return "crons"
    if any(k in p for k in ("programad", "agendad", "schedul", "recordatorio", "aviso", "para luego",
                            "para mañana", "la semana que viene")):
        return "programadas"
    if any(k in p for k in ("chat", "texto", "muro", "escrib", "message", "mensaj")):
        return "chat"
    return "procesos"


_CUSTOM_RE = re.compile(r"\b(custom|personaliz|propi|mios|mías|mias|míos)", re.I)


def apps_tab(text) -> str:
    """`apps-custom` when a phrase that named the catalogue asks for HIS widgets, `apps` otherwise (V2-761)."""
    return "apps-custom" if _CUSTOM_RE.search(str(text or "")) else "apps"


#: The system surfaces that are TABS of the wall, opened by the `panel` event rather than shown as a card.
_WALL_SURFACES = ("chat", "apps")


def wall_tab_for(system_id, text) -> str:
    """The wall tab a phrase opens when the name resolver said it NAMES a system surface, or ""."""
    sid = str(system_id or "")
    if sid not in _WALL_SURFACES:
        return ""
    return apps_tab(text) if sid == "apps" else sid
