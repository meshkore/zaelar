#
# notify.py — shared PROACTIVE NOTICE (promoted from connectors/whatsapp.service._announce). When something
# relevant arrives from ANY platform: ONE keyed notice through the out-of-turn mouth (`nucleo/pulse/notices`,
# shared throttle ~45s). The messages themselves live in the messaging card, which the turn reads (V2-851 F2: the
# grouped brain note beside the notice said the same news twice).
#
# The throttle is SHARED across platforms on purpose: we do not want WhatsApp and Telegram shouting at once.
#
import time

from loguru import logger

_last_announce = 0.0             # spoken-notice throttle (shared across all platforms)
_ANNOUNCE_GAP = 45.0             # minimum seconds between spoken notices


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
    """Proactive notice, keyed `msg:<platform>:<newest message>`. Throttle: at most once every _ANNOUNCE_GAP.
    `platform_label` = "WhatsApp" | "Telegram" (for spoken/note text). Filters muted channels
    (muted_channels) to avoid interruption. Never raises."""
    global _last_announce
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
    now = time.time()
    # Only if there is room (anti-spam), something is urgent or addressed to the operator, AND the connector's
    # policy allows speech (V2-532).
    from widgets.mensajeria import policy as _policy
    try:
        _pol = _policy.policy_for(db, (new_items[0].get("platform") or "?"))
    except Exception:
        _pol = dict(_policy.DEFAULT)
    if not _policy.wants_voice(_pol, new_items) or now - _last_announce < _ANNOUNCE_GAP:
        return
    _last_announce = now
    try:
        from nucleo.pulse import notices
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
        newest = new_items[-1]
        mark = newest.get("id") or newest.get("ts") or int(now)
        await notices.notify(platform_label, spoken, kind="info",
                             key=f"msg:{str(platform_label).lower()}:{newest.get('chatId') or ''}:{mark}")
    except Exception as e:
        logger.debug(f"{platform_label} announce falló: {e}")
