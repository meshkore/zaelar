#
# brief.py — lo que el BRAIN necesita saber de la mensajería: el protocolo de tags [[msg.*]] + la lista NUMERADA
# viva del store unificado (WhatsApp + Telegram + …), AGRUPADA POR CHAT (2026-07-08) — la misma agrupación que ve
# el operador en el widget. Cuando NO hay ningún chat abierto, la lista numerada es de CHATS (uno por conversación,
# con cuántos mensajes tiene pendientes) y el N direcciona [[msg.open:N]]/[[msg.readchat:N]]. Cuando el operador
# (o una voz anterior) abrió un chat, la lista numerada pasa a ser la de MENSAJES de ESE chat y el N direcciona
# [[msg.read:N]]/[[msg.dismiss:N]] — son dos numeraciones DISTINTAS, nunca activas a la vez.
#
# COMPACTO y NO BLOQUEANTE: lee el store unificado (stdlib, rápido); se re-inyecta cada turno. Nunca lanza.
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
Si el operador se refiere a alguien por nombre ("lo de mi madre", "el chat de fulano"), busca su número en la lista de abajo — NO le pidas que diga el número él."""


def _platform_states() -> str:
    """Una línea por plataforma con su estado de vínculo, para que el brain sepa si hay que enseñar un QR."""
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
    # Estado por-app: `enabled` = activado por el usuario desde la UI; el status vivo lo escribe el motor.
    hint = {"off": "SIN conectar", "no_creds": "sin conectar (falta introducir credenciales)",
            "starting": "arrancando", "connecting": "esperando que escanees el QR", "connected": "conectado"}
    lines = []
    for pl, label, on in (("whatsapp", "WhatsApp", wa_on), ("telegram", "Telegram", tg_on),
                          ("email", "Email", em_on)):
        st = (plats.get(pl) or {}).get("status", "off") if on else "off"
        lines.append(f"{label}: {hint.get(st, st) if on else 'SIN conectar'}.")
    tail = (" NINGUNA app requiere que el operador toque ficheros: si quiere conectar/ver una app, emite "
            "[[show:mensajeria]] y el widget le GUÍA paso a paso (credenciales si hacen falta → QR). Guíale tú "
            "también de palabra ('te abro Mensajería, ahí tienes los pasos').")
    # Prefijo con "CONECTORES" (no solo "Mensajería"): el operador pregunta "¿qué conectores tienes activos?" y
    # el modelo debe mapear ESA pregunta a ESTE dato (que ya lo tiene) en vez de irse a web_search.
    return "[CONECTORES activos (mensajería: WhatsApp/Telegram/Email) — respóndelo de aquí, no lo busques] " \
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
        # Chat abierto (por clic o por [[msg.open:N]] de un turno anterior): la lista numerada pasa a ser la de
        # MENSAJES de ese chat — msg.read/msg.dismiss direccionan aquí, no a la lista de chats.
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
