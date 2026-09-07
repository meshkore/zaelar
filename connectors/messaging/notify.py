#
# notify.py — shared PROACTIVE NOTICE (INI-015, promoted from connectors/whatsapp.service._announce). When something
# relevant arrives from ANY platform and the operator does not have the widget in front: voice via voice/proactive
# (shared throttle ~45s) + [SYSTEM] note via voice/brain_notes (ALWAYS, so the brain does not invent the outcome).
#
# The throttle is SHARED across platforms on purpose: we do not want WhatsApp and Telegram shouting at once.
#
import time

from loguru import logger

_last_announce = 0.0             # spoken-notice throttle (shared across all platforms)
_ANNOUNCE_GAP = 45.0             # minimum seconds between spoken notices
_last_note = 0.0                 # [SYSTEM] note throttle to the brain (V2-015 · T137)
_NOTE_GAP = 90.0                 # minimum seconds between brain notes — GROUPED, not one per batch/turn


def deserving(verdicts: list[dict]) -> list[dict]:
    """Which of these messages may INTERRUPT him, per each channel's configured policy (V2-532).

    Pure policy: no de-duplication, no knowledge of what is stored. Split out of `surface` in V2-607, when
    storing stopped implying notifying — the widget owner takes EVERYTHING triaged into the operator's inbox and
    then asks this, separately, who deserves a notice. Since that release the default answer is nobody, until he
    says otherwise (`set_notify`).

    A policy read that fails degrades to DEFAULT, which is silence — deliberately: the setting a broken store
    must not resurrect is the one that talks."""
    from widgets.mensajeria import policy as _policy
    try:
        from connectors.messaging import store as msg_store
        db = msg_store.load()
    except Exception:
        db = {}
    pols: dict[str, dict] = {}
    out = []
    for v in verdicts:
        plat = v.get("platform") or "?"
        pol = pols.get(plat)
        if pol is None:
            pol = pols[plat] = _policy.policy_for(db, plat)
        if _policy.wants_notice(pol, v):
            out.append(v)
    return out




async def announce(platform_label: str, new_items: list[dict]) -> None:
    """Proactive notice (voice + [SYSTEM] note). Throttle: speaks at most once every _ANNOUNCE_GAP; the brain note is
    ALWAYS left. `platform_label` = "WhatsApp" | "Telegram" (for spoken/note text). Filters muted channels
    (muted_channels) to avoid interruption. Never raises."""
    global _last_announce, _last_note
    if not new_items:
        return
    # Filter muted channels
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
    # [SYSTEM] note: the brain knows what came in (to answer follow-ups without inventing). THROTTLE (T137): do NOT
    # inject one note per batch/turn — GROUP them by window (_NOTE_GAP). Detail always lives in the 'mensajeria'
    # widget, so skipping a note loses no information; it does avoid flooding FlashBrain (one cause of giant turns
    # that buried commands).
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
    # Voice: only if there is room (anti-spam), something is urgent or addressed to the operator, AND the
    # connector's policy allows speech (V2-532: speak=False keeps the brain note above — silencing the voice must
    # not blind the brain — but never interrupts out loud).
    from widgets.mensajeria import policy as _policy
    try:
        _pol = _policy.policy_for(db, (new_items[0].get("platform") or "?"))
    except Exception:
        _pol = dict(_policy.DEFAULT)
    if not _policy.wants_voice(_pol, new_items) or now - _last_announce < _ANNOUNCE_GAP:
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
