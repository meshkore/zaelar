"""widgets/contactos/sources.py — WHERE the imported directories come from, and when (V2-714).

`imports.py` decides how a foreign row folds into ours; this decides who is asked and how often. Same cut
as `gcontacts.py`: the widget's data layer never talks to a connector, and a connector never writes to the
store.

## The three, and they are not alike

  · **telegram** — the account enumerates its own address book and its own dialogs, so this is EXACT. The
    connector owns the client, so the request goes on its queue and the answer comes back through the same
    seam every other Telegram pull uses.
  · **whatsapp** — the bridge accumulates what the socket tells it. There is no «give me everything» call
    on this platform (see `absorb`), so a pass brings what is known SO FAR and the card says so.
  · **meshkore** — no connector call at all: the clusters are already in this house
    (`manager.clusters()`). A cluster is a group whose members are AGENTS, and reading it costs nothing,
    so it is refreshed on every pass.

## Continuous import is continuous DISCOVERY

`tick` runs from the widget cron while the source is on. It never rewrites a row that exists — that rule
lives in `imports.merge_contacts` and this module has no way to override it.
"""
from __future__ import annotations

import time

from loguru import logger

#: Sources this module can pull. `google-contacts` is NOT here: it has its own two-way sync in
#: `gcontacts.py`, which is a different contract and stays that way.
KNOWN = ("telegram", "whatsapp", "meshkore")

#: How long between automatic passes. Generous on purpose: an address book is not a feed, and a pass that
#: brings nothing new still costs a platform round-trip.
EVERY_S = 900.0


def state(db: dict) -> dict:
    """Per-source sync state for the card: `{on, last, added, error}`."""
    raw = db.setdefault("sources", {})
    for s in KNOWN:
        raw.setdefault(s, {"on": False, "last": 0.0, "added": 0, "error": ""})
    return raw


def connected(source: str) -> bool:
    """Is the underlying connector actually linked? A sync switch on a source he never connected would be
    a promise the card cannot keep."""
    try:
        from connectors import registry
        for d in registry.descriptors():
            if str(d.get("id") or "") == source:
                return bool(d.get("connected"))
    except Exception:  # noqa: BLE001
        pass
    return False


# ── the three normalisers ───────────────────────────────────────────────────────────────────────────────

def _meshkore_payload() -> dict:
    """Clusters as GROUPS whose members are agents (V2-714).

    A cluster is exactly the shape `imports.merge_groups` wants — it has a name, an id that does not
    change (`cluster_id`), and a member list (`online`). The members are not people, so they arrive as
    `kind: "agent"`: addressable through the cluster channel, and never folded into somebody's family.
    """
    try:
        from connectors import meshkore as _mk
        rows = _mk.get_manager().clusters()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"contactos.sources: meshkore unavailable ({e})")
        return {"contacts": [], "groups": []}
    groups = []
    for c in rows or []:
        name = str(c.get("name") or "").strip()
        cid = str(c.get("cluster_id") or name)
        if not name:
            continue
        members = [{"name": str(h), "kind": "agent",
                    "externalIds": {"meshkore": f"{cid}/{h}"},
                    "channels": [{"platform": "meshkore", "handle": f"{name}/{h}"}]}
                   for h in (c.get("online") or []) if str(h or "").strip()]
        groups.append({"name": name, "platform": "meshkore", "subtype": "cluster",
                       "externalIds": {"meshkore": cid},
                       "channels": [{"platform": "meshkore", "handle": name, "chatId": cid}],
                       "members": members})
    return {"contacts": [], "groups": groups}


def _ask_connector(source: str, timeout: float = 25.0) -> dict:
    """Put a contacts request on the connector's queue and wait for its answer.

    The queue is the seam every other pull in these two connectors already uses (`_drain_fetch`,
    `_drain_history`): the connector owns its client and its event loop, and nothing outside it may touch
    either. A timeout is not an error worth shouting about — the next tick asks again.
    """
    try:
        from connectors.messaging import contacts_bus
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"sin bus de contactos ({e})"}
    try:
        return contacts_bus.request(source, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _payload(source: str) -> dict:
    if source == "meshkore":
        return {"ok": True, **_meshkore_payload()}
    return _ask_connector(source)


# ── the two entry points ────────────────────────────────────────────────────────────────────────────────

def sync_now(source: str) -> dict:
    """One pass of one source, right now. Returns the counts `apply_action` speaks back."""
    source = (source or "").strip().lower()
    if source not in KNOWN:
        return {"ok": False, "error": f"no sé importar contactos de «{source}» — tengo {', '.join(KNOWN)}"}
    if source != "meshkore" and not connected(source):
        return {"ok": False, "error": f"{source} no está conectado todavía — conéctalo y vuelve a pedírmelo"}
    t0 = time.time()
    got = _payload(source)
    logger.info(f"contactos: {source} contestó en {time.time() - t0:.1f}s → ok={got.get('ok')} "
                f"pending={bool(got.get('pending'))} {len(got.get('contacts') or [])} personas")
    if got.get("pending"):
        return {"ok": False, "pending": True, "error": str(got.get("error") or "")}
    try:
        return _absorb(source, got)
    except Exception as e:  # noqa: BLE001 — it runs in a pool thread that nobody awaits past 8 s: say it HERE
        logger.exception(f"contactos: no pude incorporar lo que trajo {source}: {e}")
        return {"ok": False, "error": f"no pude incorporar los contactos de {source}: {e}"}


def _absorb(source: str, got: dict) -> dict:
    """Fold one connector answer into the directory — the answer asked for now, or one that arrived late."""
    from . import data as _d, imports
    db = _d.load_db()
    st = state(db)[source]
    if not got.get("ok", True) or got.get("error"):
        st["error"] = str(got.get("error") or "no pude leer esa fuente")
        _d.store.save(_d.WIDGET_ID, db)
        return {"ok": False, "error": st["error"]}
    res = imports.absorb(db, got, source=source)
    st.update({"last": time.time(), "added": int(res.get("added") or 0), "error": ""})
    _d.store.save(_d.WIDGET_ID, db)
    logger.info(f"contactos: import {source} → +{res['added']} nuevos, {res['filled']} completados")
    return {"ok": True, "source": source, **res}


def set_auto(source: str, on: bool) -> dict:
    """The ONE switch he asked for: «un botón de sincronizar que se queda activado y en modo sincronizando
    en tiempo real». Turning it on runs a pass immediately — a switch that promises syncing and then waits
    fifteen minutes to prove it is the kind of silence this engine has paid for before."""
    from . import data as _d
    source = (source or "").strip().lower()
    if source not in KNOWN:
        return {"ok": False, "error": f"no sé importar contactos de «{source}»"}
    db = _d.load_db()
    state(db)[source]["on"] = bool(on)
    _d.store.save(_d.WIDGET_ID, db)
    if not on:
        return {"ok": True, "source": source, "on": False}
    return {**sync_now(source), "on": True}


def tick(ctx) -> None:
    """Continuous import, from the widget cron. Best-effort and quiet: a source that cannot be read is a
    line in the log and a message on the card, never a raised turn."""
    from . import data as _d
    # An answer that came back after its ask gave up is absorbed here, whether or not the source is «on»:
    # he asked for it, and it arrived (2026-09-26 — Telegram takes ~25 s, the ask waited 25 s).
    for s in ("telegram", "whatsapp"):
        try:
            from connectors.messaging import contacts_bus
            late = contacts_bus.take_late(s)
            if late is not None:
                r = _absorb(s, late)
                logger.info(f"contactos.sources: respuesta tardía de {s} incorporada → {r.get('added', 0)} nuevos")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contactos.sources: no pude incorporar la respuesta tardía de {s}: {e}")
    try:
        db = _d.load_db()
        due = [s for s, st in state(db).items()
               if st.get("on") and (time.time() - float(st.get("last") or 0.0)) >= EVERY_S]
    except Exception:  # noqa: BLE001
        return
    for s in due:
        try:
            sync_now(s)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contactos.sources: tick de {s} falló: {e}")
