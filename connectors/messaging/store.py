#
# store.py — el store UNIFICADO de mensajería (INI-015). UN solo archivo (widgets/_data/mensajeria.json) donde
# TODOS los conectores (WhatsApp, Telegram, …) escriben, y del que el widget único LEE. Reusa la primitiva
# atómica de widgets/store.py (escritura por tmp+rename → lectores nunca ven medio escrito).
#
# Forma:
#   { platforms: { whatsapp:{status,qr}, telegram:{status,qr} },
#     updated,
#     items:[{n, platform, from, group, isGroup, body, urgencia, dirigido_a_mi, motivo, messageId, chatId, senderId}],
#     pending_read:[{platform, chatId, messageId, senderId}] }
#
# CONCURRENCIA: proceso único, todos los conectores en el mismo loop. Cada helper es un read-modify-write SÍNCRONO
# sin await en medio → no hay interleaving dentro de una operación. `n` NO se persiste como identidad: lo asigna
# view_data/_renumber por orden de urgencia, así el número que ve el operador == el número que usa el brain.
#
import time

WIDGET_ID = "mensajeria"
PLATFORMS = ("whatsapp", "telegram", "email")  # email: V2-051 (IMAP/SMTP, misma forma unificada)
_RANK = {"alta": 0, "media": 1, "baja": 2}


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _empty() -> dict:
    return {
        "platforms": {p: {"status": "off", "qr": None} for p in PLATFORMS},
        "updated": "",
        "items": [],
        "pending_read": [],
        "pending_reply": [],
        "pending_control": [],
        "muted_channels": [],
    }


def _wstore():
    # lazy: no acoplar el import-time de messaging al dominio widgets (audit de modularidad 2026-07-17)
    from widgets import store
    return store


def load() -> dict:
    db = _wstore().load(WIDGET_ID, _empty())
    if not isinstance(db.get("platforms"), dict):
        db["platforms"] = {}
    for p in PLATFORMS:
        if not isinstance(db["platforms"].get(p), dict):
            db["platforms"][p] = {"status": "off", "qr": None}
    db.setdefault("items", [])
    db.setdefault("pending_read", [])
    db.setdefault("pending_reply", [])
    db.setdefault("pending_control", [])
    db.setdefault("muted_channels", [])
    db.setdefault("updated", "")
    return db


def save(db: dict) -> dict:
    return _wstore().save(WIDGET_ID, db)


def _renumber(items: list) -> list:
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items


def _key(it: dict) -> dict:
    return {"platform": it.get("platform"), "chatId": it.get("chatId"),
            "messageId": it.get("messageId"), "senderId": it.get("senderId")}


# ── Escritura por los conectores ────────────────────────────────────────────
def set_platform_status(platform: str, status: str, qr=None, detail=None) -> dict:
    """Estado de vínculo de UNA plataforma (off | no_creds | starting | connecting | connected | error). `qr` es un
    data-URI PNG o None. `detail` = mensaje HUMANO para el usuario (qué está pasando o por qué falló) — el widget lo
    muestra bajo el loader / en el card de error. No toca las otras plataformas ni la lista de items."""
    db = load()
    cur = (db.get("platforms") or {}).get(platform) or {}
    if cur.get("status") == status and cur.get("qr") == qr and cur.get("detail") == detail:
        return db      # SIN cambio real (p.ej. el poll de "Waiting for scan" repite el mismo estado) → no re-guardes:
                       # el bump de `updated` cada segundo defraudaría el change-gate de widgets/store.py y floodearía el SSE.
    db["platforms"][platform] = {"status": status, "qr": qr, "detail": detail}
    db["updated"] = _now()
    return save(db)


def upsert_items(platform: str, new_items: list[dict]) -> dict:
    """Añade items ya triados de `platform` a la lista común (dedupe por (platform, messageId)) y re-ordena por
    urgencia. Normaliza desde el veredicto crudo del triaje (senderName/chatName) a la forma del store.
    Salta items de canales silenciados (muted_channels) para que nunca entren al store."""
    db = load()
    muted_keys = {(m.get("platform"), str(m.get("chatId")))
                  for m in db.get("muted_channels", [])}
    items = db["items"]
    have = {(it.get("platform"), it.get("messageId")) for it in items}
    added = False
    fresh: list[dict] = []      # los realmente NUEVOS, para volcar a memoria (V2-003 · T57)
    for m in new_items:
        key = (platform, m.get("messageId"))
        if key[1] is None or key in have:
            continue
        # Saltar canales silenciados (no entran al store)
        if (platform, str(m.get("chatId"))) in muted_keys:
            continue
        have.add(key)
        added = True
        entry = {
            "platform": platform,
            "messageId": m.get("messageId"), "chatId": m.get("chatId"), "senderId": m.get("senderId"),
            "from": m.get("from") or m.get("senderName") or "?",
            "group": m.get("group") or (m.get("chatName") if m.get("isGroup") else None),
            "isGroup": bool(m.get("isGroup")),
            "body": m.get("body", ""), "urgencia": m.get("urgencia", "media"),
            "dirigido_a_mi": bool(m.get("dirigido_a_mi")), "motivo": m.get("motivo", ""),
        }
        # Metadatos de EMAIL para poder RESPONDER con threading (V2-051): asunto + Message-ID RFC. Solo email los
        # trae; el resto de plataformas los ignora (campos opcionales).
        if m.get("subject") is not None:
            entry["subject"] = m.get("subject")
        if m.get("msgid"):
            entry["msgid"] = m.get("msgid")
        items.append(entry)
        fresh.append(entry)
    if not added:
        return db      # nada nuevo que triar → no re-guardes (evita bump de `updated` + emit por poll sin cambio)
    items.sort(key=lambda it: _RANK.get(it.get("urgencia"), 3))
    db["items"] = items
    db["updated"] = _now()
    out = save(db)     # SSE de UI intacto: el store por-widget sigue mandando la cara
    _to_memory(fresh)  # ADEMÁS, lo durable va a la memoria central (recall del cerebro)
    return out


def _to_memory(items: list[dict]) -> None:
    """Vuelca los mensajes entrantes a la memoria central como recuerdos `kind='msg'` nivel `short`
    (V2-003 · T57). Fire-and-forget por la cola de memoria; best-effort — un fallo aquí NO afecta al store de
    UI ni al triaje. El store por-widget se mantiene para el estado de UI; la memoria es para el recall.

    Pasa por `memory.ingest_message` (la vía TIPADA unificada, multi-fuente 2026-07-10): indexa `source`
    (plataforma) + `entity` (remitente) en `meta` → el cerebro puede consultar POR TIPO ("¿qué me han escrito por
    WhatsApp?") con `recent_by_source`, sin retriever. `trust='external'` = conector personal del dueño."""
    if not items:
        return
    try:
        from memory import api as memapi
    except Exception:
        return
    for it in items:
        try:
            body = (it.get("body") or "").strip()
            if not body:
                continue
            memapi.ingest_message(it.get("platform") or "?", it.get("from") or "?", body,
                                  group=it.get("group"), directed=bool(it.get("dirigido_a_mi")),
                                  trust="external")
        except Exception:
            continue


# ── Drenaje del pending_read por los conectores ─────────────────────────────
def take_pending_read(platform: str | None = None) -> list[dict]:
    """Devuelve (y QUITA) las claves de pending_read; si `platform` se da, solo las suyas. Cada conector llama con
    su plataforma, marca leído en su app y, si falla, re-encola con requeue_pending_read()."""
    db = load()
    pending = db.get("pending_read", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    db["pending_read"] = rest
    save(db)
    return mine


def take_pending_reply(platform: str | None = None) -> list[dict]:
    """Devuelve (y QUITA) las respuestas pendientes de enviar; si `platform` se da, solo las suyas. Cada conector
    con capacidad de envío (hoy email) llama con su plataforma, envía en su app y, si falla, re-encola.
    Cada orden: {platform, chatId, to, messageId, subject, msgid, text}."""
    db = load()
    pending = db.get("pending_reply", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    db["pending_reply"] = rest
    save(db)
    return mine


def take_control() -> list[dict]:
    """Devuelve (y QUITA) las órdenes de control encoladas por el WIDGET (connect/disconnect). Las drena el
    supervisor. Cada orden: {platform, cmd:"connect"|"disconnect", api_id?, api_hash?, forget?}. Al quitarlas del
    store, los secretos (api_hash) NO quedan residentes en el fichero de mensajes (van a config/connectors.json)."""
    db = load()
    cmds = list(db.get("pending_control", []))
    if cmds:
        db["pending_control"] = []
        save(db)
    return cmds


def requeue_pending_read(keys: list[dict]) -> dict:
    """Re-encola claves cuyo mark-read falló (reintento en el siguiente tick). Idempotente."""
    if not keys:
        return load()
    db = load()
    pending = db.get("pending_read", [])
    have = {(k.get("platform"), k.get("chatId"), k.get("messageId")) for k in pending}
    for k in keys:
        sig = (k.get("platform"), k.get("chatId"), k.get("messageId"))
        if sig not in have:
            have.add(sig)
            pending.append(k)
    db["pending_read"] = pending
    return save(db)


# ── Acciones del operador (widget / voz) ────────────────────────────────────
def remove_item(n: int, mark_read: bool = True) -> dict:
    """Quita el item número `n` (numeración por orden actual). Si mark_read, encola su clave (con platform) en
    pending_read para que el conector correcto lo marque leído en su app."""
    db = load()
    items = _renumber(db.get("items", []))
    keep, hit = [], None
    for it in items:
        if it.get("n") == n:
            hit = it
        else:
            keep.append(it)
    if hit and mark_read:
        db.setdefault("pending_read", []).append(_key(hit))
    db["items"] = keep
    db["updated"] = _now()
    return save(db)


def clear() -> dict:
    """Marca leído TODO lo visible (encola cada clave con su platform) y vacía la lista."""
    db = load()
    for it in db.get("items", []):
        db.setdefault("pending_read", []).append(_key(it))
    db["items"] = []
    db["updated"] = _now()
    return save(db)
