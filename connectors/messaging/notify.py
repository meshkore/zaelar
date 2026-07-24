#
# notify.py — el AVISO PROACTIVO compartido (INI-015, promovido de connectors/whatsapp.service._announce). Cuando
# entra algo relevante de CUALQUIER plataforma y el operador no tiene el widget delante: voz por voice/proactive
# (throttle común ~45s) + nota [SISTEMA] por voice/brain_notes (SIEMPRE, para que el brain no invente el desenlace).
#
# El throttle es COMPARTIDO entre plataformas a propósito: no queremos que WhatsApp y Telegram griten a la vez.
#
import time

from loguru import logger

_last_announce = 0.0             # throttle del aviso hablado (compartido por todas las plataformas)
_ANNOUNCE_GAP = 45.0             # s mínimos entre avisos hablados
_last_note = 0.0                 # throttle de la NOTA [SISTEMA] al brain (V2-015 · T137)
_NOTE_GAP = 90.0                 # s mínimos entre notas al brain — se AGRUPAN, no una por cada batch/turno


def surface(verdicts: list[dict], seen: set) -> list[dict]:
    """Filtro común de 'merece atención': importante Y (dirigido a mí O urgencia alta) Y no visto ya.
    `seen` es el set de messageIds que el conector ya mostró (para no resucitar lo que el operador quitó)."""
    return [v for v in verdicts
            if v.get("importante") and (v.get("dirigido_a_mi") or v.get("urgencia") == "alta")
            and v.get("messageId") not in seen]


async def announce(platform_label: str, new_items: list[dict]) -> None:
    """Aviso proactivo (voz + nota [SISTEMA]). Throttle: no habla más de una vez cada _ANNOUNCE_GAP; la nota al
    brain SIEMPRE se deja. `platform_label` = "WhatsApp" | "Telegram" (para el texto hablado/nota).
    Filtra canales silenciados (muted_channels) para no interrumpir. Nunca lanza."""
    global _last_announce, _last_note
    if not new_items:
        return
    # Filtrar canales silenciados
    try:
        from connectors.messaging import store as msg_store
        db = msg_store.load()
        muted_keys = {(m.get("platform"), str(m.get("chatId")))
                      for m in db.get("muted_channels", [])}
        new_items = [
            it for it in new_items
            if (it.get("platform"), str(it.get("chatId"))) not in muted_keys
        ]
    except Exception:
        pass
    if not new_items:
        return
    # Nota [SISTEMA]: el brain sabe qué entró (para responder follow-ups sin inventar). THROTTLE (T137): NO se
    # inyecta una nota por cada batch/turno — se AGRUPAN por ventana (_NOTE_GAP). El detalle vive siempre en el
    # widget 'mensajeria', así que saltarse una nota no pierde información; sí evita inundar el FlashBrain (era
    # una causa de los turnos gigantes que enterraban los comandos).
    now = time.time()
    if now - _last_note >= _NOTE_GAP:
        try:
            from voice import brain_notes
            resumen = "; ".join(f"{i.get('from', '?')}"
                                + (f" (grupo {i['group']})" if i.get("isGroup") and i.get("group") else "")
                                + f": {(i.get('body') or '')[:80]}" for i in new_items[:5])
            brain_notes.push(f"[SISTEMA] {platform_label}: {len(new_items)} mensaje(s) nuevo(s) que le importan al "
                             f"operador: {resumen}. Están en el widget 'mensajeria' (di [[show:mensajeria]] para "
                             "enseñárselo).")
            _last_note = now
        except Exception:
            pass
    # Voz: solo si hay hueco (anti-spam) y algo urgente o dirigido a él.
    worth_speaking = any(i.get("urgencia") == "alta" or i.get("dirigido_a_mi") for i in new_items)
    if not worth_speaking or now - _last_announce < _ANNOUNCE_GAP:
        return
    _last_announce = now
    try:
        from voice import proactive
        from voice.engine.core import langs
        L = langs.current_language()
        if len(new_items) == 1:
            i = new_items[0]
            template = L.msg_notice_single_urgent if i.get("urgencia") == "alta" else L.msg_notice_single
            spoken = template.format(platform=platform_label, sender=i.get("from") or L.someone)
        else:
            spoken = L.msg_notice_multi.format(
                count=len(new_items), platform=platform_label,
                sender=new_items[0].get("from") or L.someone)
        await proactive.notify(platform_label, spoken, speak=True)
    except Exception as e:
        logger.debug(f"{platform_label} announce falló: {e}")
