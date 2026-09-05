#
# brief.py — what the BRAIN needs to know about messaging: the [[msg.*]] tag protocol + the live NUMBERED list from
# the unified store (WhatsApp + Telegram + ...), GROUPED BY CHAT (2026-07-08) — the same grouping the operator sees
# in the widget. When NO chat is open, the numbered list is CHATS (one per conversation, with its pending count) and
# N targets [[msg.open:N]]/[[msg.readchat:N]]. When the operator (or prior voice turn) opened a chat, the numbered
# list becomes MESSAGES for THAT chat and N targets [[msg.read:N]]/[[msg.dismiss:N]] — two DIFFERENT numberings,
# never active at the same time.
#
# COMPACT and NON-BLOCKING: reads the unified store (stdlib, fast); re-injected every turn. Never raises.
#
_LABEL = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "Email"}

PROTOCOL = """[MENSAJERÍA] Buzón personal UNIFICADO del operador (WhatsApp + Telegram + Email), YA TRIADO por zaelar (modelo local) y agrupado POR CHAT: una línea por conversación, no por mensaje. Es lectura + marcar leído + RESPONDER (email; la respuesta se ENVÍA con la tool `reply_message`, que PIDE confirmación antes de mandarla — no la escribas como tag). Tags SILENCIOSAS (nunca se hablan):
  [[show:mensajeria]] — abre/enfoca el widget de mensajería en el canvas (ahí están los QR de conexión de cada app).
  [[msg.open:N]] — abre el chat N de la lista de abajo: pasa a mostrar sus mensajes uno a uno (en el widget y en el siguiente brief).
  [[msg.close]] — si hay un chat abierto, vuelve a la lista de chats.
  [[msg.readchat:N]] — marca TODO el chat N como leído (en su app de origen) SIN necesidad de abrirlo.
  [[msg.read:N]] — con un chat YA ABIERTO: marca como LEÍDO (en su app de origen) el mensaje N de ESE chat.
  [[msg.dismiss:N]] — con un chat YA ABIERTO: descarta el mensaje N del widget SIN marcarlo leído en su app.
  [[msg.clear]] — marca como leído TODO lo que hay ahora en el widget (todos los chats).
  [[widget.data:mensajeria]]{"action":"hide","payload":{"n":N}} — silencia TODO el canal/chat del mensaje N (con un chat abierto) o del chat N (con la lista de chats): oculta sus mensajes actuales y futuros, sin marcar leído en la app. Seguro de usar (safe).
  [[widget.data:mensajeria]]{"action":"unhide","payload":{"platform":"...","chatId":...}} — reactiva un canal silenciado.
  [[widget.data:mensajeria]]{"action":"show_view","payload":{"platform":"all"}} — VOLVER a la lista principal unificada («la lista general/principal de mensajes»); con "whatsapp"|"telegram"|"email" filtra SOLO ese canal. Es la única forma de cambiar la vista: volver a mostrar el widget NO la cambia. Devuelve los chats que casan en `result.chats` — contesta con sus nombres.
Si el operador se refiere a alguien por nombre ("lo de mi madre", "el chat de fulano"), busca su número en la lista de abajo — NO le pidas que diga el número él (también vale {"action":"open","payload":{"name":"..."}})."""


def _platform_states() -> str:
    """One line per platform with its link state, so the brain knows whether a QR should be shown."""
    try:
        from connectors.whatsapp import service as wa
        wa_on = wa.enabled()
    except Exception:
        wa_on = False
    try:
        from connectors.telegram import service as tg
        tg_on = tg.enabled()
    except Exception:
        tg_on = False
    try:
        from connectors.email import service as em
        em_on = em.enabled()
    except Exception:
        em_on = False
    try:
        from connectors.messaging import store
        plats = store.load().get("platforms", {})
    except Exception:
        plats = {}
    # Per-app state: `enabled` = activated by the user from the UI; live status is written by the engine.
    # "error" gets words (V2-582): the raw status used to print as a bare "error", which reads as neither
    # connected nor disconnected — and the model filled the ambiguity in both directions in one session.
    hint = {"off": "SIN conectar", "no_creds": "sin conectar (falta introducir credenciales)",
            "starting": "arrancando", "connecting": "esperando que escanees el QR", "connected": "conectado",
            "error": "NO conectado (el último intento de conexión falló; se reconecta desde el widget)"}
    lines = []
    for pl, label, on in (("whatsapp", "WhatsApp", wa_on), ("telegram", "Telegram", tg_on),
                          ("email", "Email", em_on)):
        st = (plats.get(pl) or {}).get("status", "off") if on else "off"
        lines.append(f"{label}: {hint.get(st, st) if on else 'SIN conectar'}.")
    tail = (" NINGUNA app requiere que el operador toque ficheros: si quiere conectar/ver una app, emite "
            "[[show:mensajeria]] y el widget le GUÍA paso a paso (credenciales si hacen falta → QR). Guíale tú "
            "también de palabra ('te abro Mensajería, ahí tienes los pasos').")
    # Prefix with "CONNECTORS" (not just "Messaging"): the operator asks "which connectors are active?" and the
    # model must map THAT question to THIS data (which it already has) instead of going to web_search.
    # And it OUTRANKS the conversation (V2-582, measured live): the operator connected email mid-dialogue and
    # the model kept answering from its own earlier "it is not connected" — this line refreshes every turn, so
    # the window is the stale side, never this one. Naming what NOT to repeat is what makes the rule land
    # (V2-221: without the phrase inside, the model has nothing to check itself against).
    return "[CONECTORES activos (mensajería: WhatsApp/Telegram/Email) — respóndelo de aquí, no lo busques. " \
        "Esta línea es el estado EN VIVO de este preciso turno y MANDA sobre la conversación anterior, " \
        "incluidas TUS propias frases: el operador puede haberlo conectado o desconectado hace un momento " \
        "desde el widget. Si aquí pone «conectado», ESTÁ conectado aunque acabes de decir lo contrario — " \
        "no vuelvas a negar la conexión; y si pone NO conectado, jamás afirmes que sí.] " \
        + " ".join(lines) + tail


def for_brain() -> str:
    body = PROTOCOL + "\n" + _platform_states()
    try:
        from widgets.mensajeria import data
        v = data.view_data()
    except Exception:
        return body + "\n[Mensajería ahora] lista no disponible."

    active = v.get("active_chat")
    if active:
        # Open chat (by click or by [[msg.open:N]] from a previous turn): the numbered list becomes the MESSAGES in
        # that chat — msg.read/msg.dismiss target this list, not the chat list.
        items = v.get("active_items", [])
        plat = _LABEL.get(active.get("platform"), active.get("platform") or "?")
        name = next((it.get("group") or it.get("from") for it in items if it.get("group") or it.get("from")), "?")
        if not items:
            return body + f"\n[Mensajería — chat ABIERTO: {plat} · {name}] sin mensajes (usa [[msg.close]])."
        lines = []
        for it in items:
            who = it.get("from", "?")
            urg = "URGENTE " if it.get("urgencia") == "alta" else ""
            msgbody = (it.get("body") or "").replace("\n", " ")[:100]
            lines.append(f"  {it['n']}. {urg}{who}: \"{msgbody}\"")
        return (body + f"\n[Mensajería — chat ABIERTO: {plat} · {name} — usa msg.read/msg.dismiss/msg.close]\n"
                + "\n".join(lines))

    chats = v.get("chats", [])
    if not chats:
        return body + "\n[Mensajería ahora] nada pendiente que atender."
    lines = []
    for c in chats:
        plat = _LABEL.get(c.get("platform"), c.get("platform") or "?")
        urg = "URGENTE " if c.get("urgencia") == "alta" else ""
        para = " (para ti)" if c.get("dirigido_a_mi") else ""
        preview = (c.get("lastBody") or "").replace("\n", " ")[:100]
        pend = "1 mensaje" if c.get("count") == 1 else f"{c.get('count')} mensajes"
        lines.append(f"  {c['n']}. [{plat}] {urg}{c.get('name', '?')}{para} — {pend} pendientes: \"{preview}\"")
    return (body + "\n[Mensajería ahora — lista de CHATS, usa msg.open/msg.readchat/msg.clear]\n"
            + "\n".join(lines))
