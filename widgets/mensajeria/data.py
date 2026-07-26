#
# Mensajería widget — data layer (INI-015). LEE/muta el store UNIFICADO (widgets/_data/mensajeria.json), que
# ESCRIBEN los motores de los conectores (connectors/whatsapp/service.py y connectors/telegram/service.py vía
# connectors/messaging/store.py). El widget es la cara; los conectores son los motores. Una sola lista para TODAS
# las plataformas.
#
# CONTRATO de widgets: data.py es stdlib-only + el paquete `widgets` (aislamiento). Por eso NO importa `connectors`:
# usa `widgets.store` directamente sobre el MISMO fichero/id que el conector. view_data NUNCA lanza. Las acciones
# del operador encolan la clave (CON su `platform`) en `pending_read`; el conector correcto la drena y marca leído
# en su app. Un fallo de una plataforma no tumba la otra ni la voz.
#
from .. import store

WIDGET_ID = "mensajeria"
_PLATFORMS = ("whatsapp", "telegram", "email")   # email: V2-051
_URG_RANK = {"alta": 0, "media": 1, "baja": 2}   # copia local (data.py es stdlib-only, no importa connectors)


def _empty() -> dict:
    return {
        "platforms": {p: {"status": "off", "qr": None} for p in _PLATFORMS},
        "updated": "",
        "items": [],
        "pending_read": [],
        "pending_reply": [],
        "pending_control": [],
        "active_chat": None,   # {"platform":..., "chatId":...} | None — hilo abierto en el widget (clic o voz)
    }


def load_db() -> dict:
    db = store.load(WIDGET_ID, _empty())
    if not isinstance(db.get("platforms"), dict):
        db["platforms"] = {}
    for p in _PLATFORMS:
        if not isinstance(db["platforms"].get(p), dict):
            db["platforms"][p] = {"status": "off", "qr": None}
    db.setdefault("items", [])
    db.setdefault("pending_read", [])
    db.setdefault("pending_reply", [])
    db.setdefault("updated", "")
    db.setdefault("active_chat", None)
    return db


def _renumber(items: list) -> list:
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items


def _key(it: dict) -> dict:
    return {"platform": it.get("platform"), "chatId": it.get("chatId"),
            "messageId": it.get("messageId"), "senderId": it.get("senderId")}


def _visible_items(db: dict) -> list:
    """Items no silenciados, renumerados — la MISMA lista base que ve el widget y el brain."""
    muted_channels = db.get("muted_channels", [])
    muted_keys = {(m.get("platform"), str(m.get("chatId"))) for m in muted_channels}
    return _renumber([
        it for it in db.get("items", [])
        if (it.get("platform"), str(it.get("chatId"))) not in muted_keys
    ])


def _group_chats(items: list) -> list:
    """Agrupa la lista PLANA (ya renumerada) por (platform, chatId), preservando el orden de aparición — un
    item por CHAT en vez de uno por mensaje. Cada chat lleva su propio `n`: un addressing space DISTINTO del
    de `items` ([[msg.open:N]]/[[msg.readchat:N]] usan este; [[msg.read:N]]/[[msg.dismiss:N]] siguen usando el
    `n` de `items`, solo direccionable con el chat abierto)."""
    order, by_key = [], {}
    for it in items:
        key = (it.get("platform"), str(it.get("chatId")))
        g = by_key.get(key)
        if g is None:
            g = {"platform": it.get("platform"), "chatId": it.get("chatId"),
                 "name": it.get("group") or it.get("from") or "?", "isGroup": bool(it.get("isGroup")),
                 "count": 0, "rank": 3, "dirigido_a_mi": False, "last": it}
            by_key[key] = g
            order.append(key)
        g["count"] += 1
        g["rank"] = min(g["rank"], _URG_RANK.get(it.get("urgencia"), 3))
        g["dirigido_a_mi"] = g["dirigido_a_mi"] or bool(it.get("dirigido_a_mi"))
        g["last"] = it   # el más reciente EN ORDEN DE APARICIÓN (no hay timestamp en el store)
    rank_to_urg = {0: "alta", 1: "media", 2: "baja"}
    chats = []
    for i, key in enumerate(order, 1):
        g = by_key[key]
        last = g["last"]
        chats.append({
            "n": i, "platform": g["platform"], "chatId": g["chatId"], "name": g["name"],
            "isGroup": g["isGroup"], "count": g["count"], "dirigido_a_mi": g["dirigido_a_mi"],
            "urgencia": rank_to_urg.get(g["rank"], "media"),
            "lastFrom": last.get("from"), "lastBody": last.get("body", ""), "lastMotivo": last.get("motivo", ""),
        })
    return chats


def view_data(q: str = "") -> dict:
    db = load_db()
    items = _visible_items(db)
    chats = _group_chats(items)
    muted_channels = db.get("muted_channels", [])

    active = db.get("active_chat")
    active_key = (active.get("platform"), str(active.get("chatId"))) if active else None
    active_items = [it for it in items if (it.get("platform"), str(it.get("chatId"))) == active_key] \
        if active_key else []
    if active and not active_items:
        # El chat abierto se quedó sin mensajes (se leyeron/descartaron todos) — ciérralo solo, no dejar un
        # hilo vacío esperando a que el operador pulse "volver" (y evita que resucite si llega un mensaje nuevo
        # mucho más tarde en ese mismo chat, cuando el operador ya lo dio por cerrado).
        db["active_chat"] = None
        store.save(WIDGET_ID, db)
        active = None

    return {
        "platforms": db.get("platforms", {}),
        "updated": db.get("updated", ""),
        "items": items,
        "count": len(items),
        "chats": chats,
        "active_chat": active,
        "active_items": active_items,
        "muted_channels": [
            {"group": m.get("group") or f"{m.get('platform')}:{m.get('chatId')}",
             "platform": m.get("platform"), "chatId": m.get("chatId")}
            for m in muted_channels
        ],
    }


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Acciones del operador desde el widget (ÚNICO canal widget→backend; el widget no puede hacer fetch):
    - read/dismiss/clear → mutan la lista (marcar leído encola en `pending_read`, drenado por el conector).
    - connect/disconnect → encolan una orden de control en `pending_control` (plataforma + credenciales); el
      SUPERVISOR (server-side) la drena y hace el connect/disconnect real (config/connectors.py + arrancar/parar).
      Así el usuario conecta Telegram/WhatsApp desde la UI, sin tocar .env. data.py sigue siendo stdlib-only."""
    payload = payload or {}

    # ── Control de conexión (lo ejecuta el supervisor, no el widget) ─────────
    if action in ("connect", "disconnect"):
        platform = (payload.get("platform") or "").lower()
        if platform in _PLATFORMS:
            db = load_db()
            cmd = {"platform": platform, "cmd": action}
            if action == "connect" and platform == "telegram":
                cmd["api_id"] = str(payload.get("api_id") or "").strip()
                cmd["api_hash"] = str(payload.get("api_hash") or "").strip()
            if action == "connect" and platform == "email":
                # Credenciales del formulario del widget (V2-051). El supervisor→control.py las persiste redactadas.
                for k in ("email_address", "email_password", "provider",
                          "imap_host", "imap_port", "smtp_host", "smtp_port"):
                    if payload.get(k) not in (None, ""):
                        cmd[k] = payload.get(k)
            if action == "disconnect" and payload.get("forget"):
                cmd["forget"] = True
            db.setdefault("pending_control", []).append(cmd)
            store.save(WIDGET_ID, db)
        return view_data()

    # ── RESPONDER a un mensaje (V2-051) — encola en pending_reply para que el conector de esa plataforma lo ENVÍE.
    #    `n` sigue la MISMA dualidad que read/dismiss: con un chat ABIERTO es un `n` de MENSAJE (items); con la
    #    lista de chats es un `n` de CHAT (→ su último mensaje). El envío real (hoy email) lo hace el conector; el
    #    gate CONFIRM (V2-025) ya pidió OK antes de llegar aquí. ─────────────────────────────────────────────────
    if action == "reply":
        n = payload.get("n")
        text = (payload.get("text") or "").strip()
        if n is not None and text:
            db = load_db()
            target = None
            if db.get("active_chat") is not None:
                target = next((it for it in _renumber(db.get("items", [])) if it.get("n") == n), None)
            else:
                chat = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
                if chat:                       # el chat → su último mensaje (para el threading / destinatario)
                    key = (chat["platform"], str(chat["chatId"]))
                    msgs = [it for it in db.get("items", [])
                            if (it.get("platform"), str(it.get("chatId"))) == key]
                    target = msgs[-1] if msgs else None
            if target is not None:
                db.setdefault("pending_reply", []).append({
                    "platform": target.get("platform"),
                    "chatId": target.get("chatId"),
                    "to": target.get("senderId") or target.get("chatId"),
                    "messageId": target.get("messageId"),
                    "subject": target.get("subject", ""),
                    "msgid": target.get("msgid", ""),
                    "text": text,
                })
                # Responder implica LEÍDO: encola también el mark-read de ese mensaje y quítalo de la lista.
                db.setdefault("pending_read", []).append(_key(target))
                db["items"] = [it for it in db.get("items", []) if it is not target]
                store.save(WIDGET_ID, db)
        return view_data()

    # ── Silenciar canal — N direcciona lo mismo que read/dismiss según el contexto: con un chat ABIERTO es un
    #    `n` de MENSAJE (numeración de `items`); con la lista de chats es un `n` de CHAT (numeración de
    #    `_group_chats`). Misma dualidad ya documentada en brief.py para read/dismiss/hide. ──────────────────
    if action == "hide":
        n = payload.get("n")
        if n is not None:
            db = load_db()
            platform = chat_id = group = None
            if db.get("active_chat") is not None:
                for it in _renumber(db.get("items", [])):
                    if it.get("n") == n:
                        platform, chat_id = it.get("platform"), it.get("chatId")
                        group = it.get("group") or it.get("from") or ""
                        break
            else:
                match = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
                if match:
                    platform, chat_id, group = match["platform"], match["chatId"], match["name"]
            if platform and chat_id is not None:
                key = (platform, str(chat_id))
                muted = db.get("muted_channels", [])
                if not any((m.get("platform"), str(m.get("chatId"))) == key for m in muted):
                    muted.append({"platform": platform, "chatId": chat_id, "group": group})
                    db["muted_channels"] = muted
                db["items"] = [it for it in db.get("items", [])
                               if (it.get("platform"), str(it.get("chatId"))) != key]
                store.save(WIDGET_ID, db)
        return view_data()

    if action == "unhide":
        platform = payload.get("platform")
        chat_id = payload.get("chatId")
        if platform and chat_id is not None:
            db = load_db()
            key = (platform, str(chat_id))
            db["muted_channels"] = [m for m in db.get("muted_channels", [])
                                     if (m.get("platform"), str(m.get("chatId"))) != key]
            store.save(WIDGET_ID, db)
        return view_data()

    # ── Abrir/cerrar el hilo de un chat — navegación pura, direccionable por clic o por voz
    #    ([[msg.open:N]]/[[msg.close]], N = el `n` del CHAT, ver _group_chats) ─────────────
    if action == "open":
        n = payload.get("n")
        if n is not None:
            db = load_db()
            match = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
            if match:
                db["active_chat"] = {"platform": match["platform"], "chatId": match["chatId"]}
                store.save(WIDGET_ID, db)
        return view_data()

    if action == "close":
        db = load_db()
        if db.get("active_chat") is not None:
            db["active_chat"] = None
            store.save(WIDGET_ID, db)
        return view_data()

    # ── Marcar leído un chat ENTERO sin abrirlo (voz: [[msg.readchat:N]], N = el `n` del CHAT) ──
    if action == "readchat":
        n = payload.get("n")
        if n is not None:
            db = load_db()
            match = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
            if match:
                key = (match["platform"], str(match["chatId"]))
                pending = db.get("pending_read", [])
                keep = []
                for it in db.get("items", []):
                    if (it.get("platform"), str(it.get("chatId"))) == key:
                        pending.append(_key(it))
                    else:
                        keep.append(it)
                db["items"] = keep
                db["pending_read"] = pending
                store.save(WIDGET_ID, db)
        return view_data()

    db = load_db()
    items = _renumber(db.get("items", []))   # alinear n con lo que el widget mostró (view_data numera por orden)
    pending = db.get("pending_read", [])

    if action in ("read", "dismiss"):
        n = payload.get("n")
        mid = payload.get("messageId")
        keep = []
        for it in items:
            hit = (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)
            if hit and action == "read":
                pending.append(_key(it))
            elif not hit:
                keep.append(it)
        db["items"] = keep
    elif action == "clear":
        for it in items:
            pending.append(_key(it))
        db["items"] = []

    db["pending_read"] = pending
    store.save(WIDGET_ID, db)
    return view_data()
