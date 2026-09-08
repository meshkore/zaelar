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


def _email_backlog() -> str:
    """What is in the MAILBOX versus what is in the WIDGET — the two numbers the model kept collapsing (V2-606).

    Measured, session `43b7bf79`: the operator said «en mi bandeja de entrada de Gmail veo un montón de mensajes»
    and got «Es que no tienes mensajes nuevos sin leer, por eso sale vacío» — over 1088 unread. The model was not
    lying; it had a «connected» flag and an empty widget and invented the link between them, because nothing here
    told it the mailbox has a backlog the widget deliberately does not hold.

    Says nothing when it does not know: `-1` is «not measured» and must never render as zero, which is precisely
    the sentence this exists to make impossible.
    """
    try:
        from connectors.email import service as _em
        n = _em.unread_total()
        cap = _em.BACKFILL
    except Exception:  # noqa: BLE001
        return ""
    if n < 0:
        return ""
    if n == 0:
        return " Su buzón NO tiene correos sin leer (0), así que un widget de correo vacío es correcto."
    shown = min(n, cap)
    extra = ("" if n <= cap else
             f" Los otros {n - shown} NO están en el widget y no se pueden listar desde aquí: si los quiere ver, "
             f"es en su propio correo. NO digas que no los tiene.")
    return (f" ⚠️ Su BUZÓN tiene {n} correo(s) SIN LEER — ese es el número que se le contesta si pregunta cuántos "
            f"tiene. El widget es una lista TRIADA, no el buzón: lleva como mucho los {shown} más recientes, y "
            f"puede enseñar menos si el triaje descartó alguno. JAMÁS digas «no tienes mensajes sin leer» ni "
            f"expliques un widget vacío diciendo que no hay correo: di cuántos hay y qué parte estás enseñando.{extra}")


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
        lines.append(f"{label}: {hint.get(st, st) if on else 'SIN conectar'}.{_email_backlog() if pl == 'email' and on and st == 'connected' else ''}")
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


def _pro_state() -> str:
    """V2-624 — live state the manifest cannot carry: the active autoresponder(s) and any per-platform view
    criterion. Empty when nothing is set (zero prompt cost). Declared so the model neither narrates a
    capability that is off nor forgets one that is speaking for the operator right now."""
    try:
        from widgets.mensajeria import autorespond, data as _mdata
        db = _mdata.load_db()
    except Exception:  # noqa: BLE001
        return ""
    parts = []
    try:
        for p in autorespond.active_platforms(db):
            cfg = autorespond.config_for(db, p)
            win = f", franja {cfg['hours']}" if cfg.get("hours") else ""
            parts.append(f"AUTORRESPONDEDOR ACTIVO en {_LABEL.get(p, p)} («{cfg['text'][:60]}»{win}) — "
                         f"contesta solo, 1 vez/chat/24h; se apaga con clear_autoresponder")
    except Exception:  # noqa: BLE001
        pass
    try:
        for p, crit in (db.get("lens_criteria") or {}).items():
            win = float((crit or {}).get("window_h") or 0)
            if win > 0:
                parts.append(f"la vista de {_LABEL.get(p, p)} está fijada a ACTIVIDAD de las últimas "
                             f"{win:.0f} h (show_view con window_h:0 la quita)")
    except Exception:  # noqa: BLE001
        pass
    return (" [" + " · ".join(parts) + "]") if parts else ""


def for_brain() -> str:
    body = PROTOCOL + "\n" + _platform_states() + _pro_state()
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
        # V2-607 — WHERE he can see it, because the brain's list and his screen are no longer the same list.
        where = "" if c.get("highlight") else " [solo en su sección, NO en el resumen]"
        preview = (c.get("lastBody") or "").replace("\n", " ")[:100]
        pend = "1 mensaje" if c.get("count") == 1 else f"{c.get('count')} mensajes"
        lines.append(f"  {c['n']}. [{plat}] {urg}{c.get('name', '?')}{para}{where} — {pend} pendientes: "
                     f"\"{preview}\"")
    return (body + _summary_split(chats)
            + "\n[Mensajería ahora — lista de CHATS, usa msg.open/msg.readchat/msg.clear]\n"
            + "\n".join(lines))


def _summary_split(chats: list) -> str:
    """What HE sees versus what this list holds (V2-607).

    The brain gets every chat; his first tab shows only the ones meeting his criterion (by default, addressed to
    him). Two surfaces over one dataset that disagree is how the model ends up contradicting the screen — the
    same shape as V2-606, where a «connected» flag plus an empty card produced «no tienes correos sin leer» over
    1088 of them. So the split is stated, with the sentence it must not say.

    Also states that NOTHING interrupts by default, so the model neither promises to warn him nor apologises for
    not having warned him — and knows the door when he asks for it."""
    rest = [c for c in chats if not c.get("highlight")]
    if not rest:
        return ("\n[Aviso: por defecto NINGÚN canal te interrumpe cuando llega un mensaje. Si te pide que le "
                "avises («avísame cuando llegue algo»), es la acción set_notify del widget de mensajería.]")
    n = sum(int(c.get("count") or 1) for c in rest)
    return (f"\n[Lo que él VE ahora mismo: su resumen solo enseña lo que va DIRIGIDO A ÉL. Hay {len(rest)} "
            f"conversación(es) más, {n} mensaje(s), que están en la sección de su canal y NO en ese resumen — "
            f"marcadas abajo. Existen y las tienes aquí: si pregunta, dile cuántas hay y en qué canal, y ofrécele "
            f"abrir ese canal (msg.show_view). JAMÁS digas que no tiene nada ni que no han llegado. Y por "
            f"defecto NINGÚN canal le interrumpe al llegar un mensaje: si te pide que le avises, es set_notify.]")
