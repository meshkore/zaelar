"""Execute a widget data-op from a turn (extracted from `probe.py`, V2-383).

It changes nothing about what it did: it was moved out of `probe.py` because it is the SAME concern as
`music_turn` and `video_turn`—a turn that executes a widget operation through the voice rail—and because
`probe.py` is a ratcheted god file, so adding video execution requires taking out what no longer belongs
there. The block's history, which explains why it exists, travels with it:

REAL EXECUTION of a data-op (2026-07-25): without this, the probe validated ROUTING but never SENT—making
it impossible to reproduce e2e «manda a zalo …». If the action is FAST, it is dispatched through the SAME
path as voice (`widgets.dispatch_tag` → the widget's `apply_action`). CONFIRM is not auto-confirmed (it
requires the operator's yes); it is reported as pending. (V2-086: sending to the cluster NO longer goes
through here—it is the `cluster_send` tool, not a widget data-op.)
"""
from __future__ import annotations


def _primera_clave(widget_id: str, action: str) -> str:
    """The FIRST key in this action's declared payload, or ""—read from the manifest, not assumed.

    This is where a natural-language reference goes when the action declares no id field: by convention in
    all manifests, the first key is the action's primary data (`url` in `youtube.add`, `item` in
    `imagenes.select`, `playlist` in `musica.add_to_playlist`). Deliberately data-driven: the alternative
    was a widget table, which is precisely what this tree does not want.
    """
    try:
        from widgets import runtime
        spec = ((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}
        payload = spec.get("payload")
        if isinstance(payload, dict):
            for k in payload:
                return str(k)
    except Exception:  # noqa: BLE001
        pass
    return ""


async def execute(tool_calls: list) -> dict:
    """Dispatch the turn's data-ops and return the report, or say which was skipped and WHY.

    V2-391—SEVERAL, not one. Which ones enter is decided by `data_ops.admite_data_op`, shared with voice
    so they cannot diverge: the same widget and action with DIFFERENT payloads yes (two pasted links), an
    exact duplicate no (the double quote), and a different action on the same widget neither (the listing).
    """
    from nucleo.flash import frontend as _fe
    from nucleo.flash import data_ops as _rg
    from widgets import actions as _wa

    todas = [t.get("args") or {} for t in (tool_calls or []) if t.get("name") == "widget_data"]
    admitidas: list[dict] = []
    for a in todas:
        if _rg.admite_data_op(a, admitidas):
            admitidas.append(a)
    if not admitidas:
        return {"executed": "widget_data_skipped", "mode": "sin data-op utilizable", "widget": "", "act": ""}

    # V2-394—`brain_action` and NOT `dispatch_tag`: the former swallows the result and returns None, so with
    # it the turn CANNOT know whether the operation happened, and the mouth says «Hecho.» regardless. It is
    # exactly the same reason already written in `video_turn.execute`, here in the general case.
    from widgets.server_api import brain_action as _brain_action
    hechas, saltadas, fallidas = [], [], []
    for a in admitidas:
        wid = str(a.get("widget_id") or "").strip().lower()
        act = str(a.get("action") or "").strip()
        pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
        # THE ITEM REFERENCE TRAVELS (V2-463). The tool declares `item` as its own argument («natural-language
        # natural language, never an invented id»), and this path DROPPED it: it only passed `payload`, so
        # «ponme la 1, la del Spider» reached the widget as a select without an item—three failures measured
        # in one round, with the model saying «te la dejo puesta» on top. It is resolved through the SAME
        # mechanism as voice (`widgets.refs.resolve`, the real id against what is on screen, never invented);
        # if it does not resolve, the raw text travels in the id field as well so the widget's OWN resolver
        # (e.g. the one in `imagenes`, which matches by tokens) gets its chance and its refusal can show the menu.
        _ref = str(a.get("item") or "").strip()
        if _ref:
            try:
                from widgets import refs as _refs
                _rr = _refs.resolve(wid, act, _ref, pl)
                if getattr(_rr, "ok", False) and isinstance(_rr.payload, dict):
                    pl = _rr.payload
                # WHERE the reference lands is specified by the MANIFEST, not an invented key (V2-467). First the
                # declared id field; if the action has none, its FIRST payload key, which is the one the
                # widget actually reads. Using the literal `"item"` was a measured defect: the operator
                # pasted two YouTube links, the model called `add` with the reference, and the payload came
                # out as `{"item": "<enlaces>"}`—`youtube.add` reads `url`, so it replied «dime qué vídeo añado»
                # with both links in front of it. This was not seen with `imagenes.select` because its key is,
                # precisely, named `item`.
                _campo = _refs.id_field_for_action(wid, act) or _primera_clave(wid, act) or "item"
                # A manifest without a declared id field makes `resolve` answer «ok, nothing to resolve»
                # with the payload intact—and the reference would be lost. If the model supplied one and it
                # did not land, it travels raw in that key: the widget's OWN resolver decides, and its refusal
                # shows the menu.
                if not str(pl.get(_campo) or "").strip():
                    pl = {**pl, _campo: _ref}
            except Exception:  # noqa: BLE001
                pl = {**pl, "item": _ref}
        mode = _fe.action_mode(wid, act)
        if mode != _wa.FAST:
            saltadas.append({"widget": wid, "act": act, "mode": str(mode)})
            continue
        res = await _brain_action(wid, act, pl)
        res = res if isinstance(res, dict) else {}
        if res.get("error") or res.get("ok") is False:
            fallidas.append({"widget": wid, "act": act,
                             "message": str(res.get("message") or res.get("error") or "")[:160]})
            continue
        hechas.append({"widget": wid, "act": act})
        # THE CARD OPENS WHERE THE DATA LANDS (V2-463, now also in the generic case). Measured
        # in `build-a-video-playlist-from-links`: the model executed `name_list` and the report marked «WRITTEN
        # BUT NEVER OPENED»—the operator saw nothing, so «hecho» was invisible. A data-op that WRITES is
        # exactly what the frontend already uses to repaint an open card; opening it as well when it is not
        # open is the same decision, not a new one. Idempotent in the browser.
        try:
            from voice.observer import emit as _emit
            _emit("widget", "show", extra={"id": wid, "src": "flash"})
        except Exception:  # noqa: BLE001
            pass
    if not hechas:
        if fallidas:
            f0 = fallidas[0]
            return {"executed": "widget_data_failed", "widget": f0["widget"], "act": f0["act"],
                    "message": f0["message"], "fallidas": fallidas}
        s0 = saltadas[0]
        return {"executed": "widget_data_skipped", "mode": s0["mode"], "widget": s0["widget"], "act": s0["act"]}
    # Singular `widget`/`act` are preserved: this is how the report and previous guards already read them,
    # and changing them to a list would break reading without warning. The new data goes alongside them.
    parte = {"executed": "widget_data", "widget": hechas[0]["widget"], "act": hechas[0]["act"],
             "ops": hechas}
    # What was NOT done is STATED, rather than leaving the report to count only what went well.
    if len(todas) > len(hechas):
        parte["descartadas"] = len(todas) - len(hechas)
    if saltadas:
        parte["sin_permiso"] = saltadas
    # An operation that failed travels along even if ANOTHER succeeded: «I added one and could not find the
    # other» is the honest response, and keeping only the successful one is how a partial «Hecho.» passes as complete.
    if fallidas:
        parte["fallidas"] = fallidas
    return parte


_YT_LINK = None  # compiled lazily below


def complete_pasted_links(tool_calls: list, operator_text: str) -> list:
    """The links the operator PASTED all travel (V2-469, `build-a-video-playlist` 23:17): two links in one
    message, the model's single `add` carried one — «Hecho» over half the errand, and the user had to
    correct it. The multi-link add already works (V2-384 bis); what failed was the payload. The links are
    the operator's own words verbatim, so appending the ones his turn carries invents nothing. Narrow on
    purpose: only youtube `add`, only links present in THIS turn's text, no-op everywhere else.
    """
    global _YT_LINK
    import re as _re
    if _YT_LINK is None:
        _YT_LINK = _re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([0-9A-Za-z_-]{11})\S*")
    text = str(operator_text or "")
    pasted = [(m.group(0), m.group(1)) for m in _YT_LINK.finditer(text)]
    if not pasted or not isinstance(tool_calls, list):
        return tool_calls
    adds = [t for t in tool_calls
            if isinstance(t, dict) and t.get("name") == "widget_data"
            and str(((t.get("args") or {}).get("widget_id") or "")).strip().lower() == "youtube"
            and str(((t.get("args") or {}).get("action") or "")).strip() == "add"]
    if not adds:
        return tool_calls
    covered = " ".join(
        str(((t.get("args") or {}).get("payload") or {}).get(k) or "")
        for t in adds for k in ("url", "urls", "query", "item")) + " ".join(
        str((t.get("args") or {}).get("item") or "") for t in adds)
    faltan = [url for url, vid in pasted if vid not in covered]
    if not faltan:
        return tool_calls
    args = adds[0].get("args") or {}
    pl = dict(args.get("payload") if isinstance(args.get("payload"), dict) else {})
    pl["url"] = (str(pl.get("url") or "").strip() + " " + " ".join(faltan)).strip()
    adds[0]["args"] = {**args, "payload": pl}
    return tool_calls


def ensure_failure_named(spoken: str, parte: dict) -> str:
    """The failure rides along even when the model SPOKE (V2-469, round 11 turn 7): «I’m showing you the
    next one on screen» over `widget_data_failed` («There are no more videos in the list»)—the honest canned
    line only replaced a MUTE turn, so a spoken narration lied over a failure the system had in hand.
    Sibling of `video_turn.ensure_delivery_named`, the failure direction. A mute turn is left alone: the
    canned replacement downstream already owns it.
    """
    spoken = (spoken or "").strip()
    parte = parte if isinstance(parte, dict) else {}
    if not spoken:
        return spoken
    msgs = []
    if parte.get("executed") == "widget_data_failed":
        msgs.append(str(parte.get("message") or "").strip() or "el widget no lo aceptó.")
    else:
        for f in (parte.get("fallidas") or []):
            m = str((f or {}).get("message") or "").strip()
            if m:
                msgs.append(m)
    if not msgs:
        return spoken
    cola = "No he podido: " + msgs[0]
    if cola.lower() in spoken.lower() or msgs[0].lower() in spoken.lower():
        return spoken
    return spoken.rstrip() + " " + cola


_ASKS = None


def _asked_something(text: str) -> bool:
    """A question without a question mark is still a question: «tell me what is playing» (measured, round 11
    turn 1) carries no «?». Tiny closed set of ASK shapes — not intent classification, just the asking
    surface — plus the literal question mark."""
    global _ASKS
    import re as _re
    import unicodedata as _ud
    if "?" in str(text or ""):
        return True
    plano = "".join(c for c in _ud.normalize("NFKD", str(text or "").lower()) if not _ud.combining(c))
    if _ASKS is None:
        _ASKS = _re.compile(r"\b(dime|dimelo|me dices|me cuentas|cuentame|tell me|what's playing)\b")
    return bool(_ASKS.search(plano))


def named_ack(parte: dict, ack: str, operator_text: str = "") -> str:
    """A bare «Done.» to a QUESTION is a non-answer (V2-469, `build-a-video-playlist` 23:05): «And what is
    in the list?» → mute model over a redundant `add` → «Done.», twice, watchdog nudging both times and
    the user asking FIVE times before getting the titles.

    When the operator's turn ASKED something and the model said nothing, the ack enumerates what the
    acted-on widget now holds — read live from its `ref_index`, the same contract reference-resolution
    already uses, so it is generic (agenda, player list, photo strip) and never invented: a widget that
    publishes nothing keeps the plain ack. Failures keep `spoken_for`'s honest message untouched.
    """
    parte = parte if isinstance(parte, dict) else {}
    base = spoken_for(parte, ack)
    if parte.get("executed") != "widget_data" or parte.get("fallidas"):
        return base
    if not _asked_something(operator_text):
        return base
    wid = str(parte.get("widget") or "").strip()
    if not wid:
        return base
    try:
        from widgets import refs as _refs
        labels = []
        for i in _refs._ref_index(wid):
            l = str(i.get("label") or "").strip()
            if not l:
                continue
            # The hint travels (V2-469, round 10): «and what is playing?» got the enumeration WITHOUT
            # marking which one — the labels answered a different question than the one asked.
            h = str(i.get("hint") or "").strip()
            labels.append(f"{l[:80]} ({h})" if h else l[:80])
    except Exception:  # noqa: BLE001
        labels = []
    if not labels:
        return base
    en = False
    try:
        from voice.engine.core import langs as _langs
        en = _langs.current_code() == "en"
    except Exception:  # noqa: BLE001
        pass
    vista = " · ".join(f"«{l}»" for l in labels[:4])
    resto = len(labels) - 4
    if resto > 0:
        vista += (f" and {resto} more" if en else f" y {resto} más")
    return (f"Done. Right now it holds: {vista}." if en else f"Hecho. Ahora mismo hay: {vista}.")


def spoken_for(parte: dict, ack: str) -> str:
    """What is SAID after a data-op. `ack` is the canned line for the language, only for the successful case.

    «Hecho.» for an operation the widget REJECTED is the sixth time one of our canned lines lies (V2-176 for
    a task just started, V2-209 for an empty card, V2-377 for someone else's request, V2-380 for playback
    that did not exist, V2-383 for a video that did not load).
    """
    parte = parte if isinstance(parte, dict) else {}
    ejec = parte.get("executed")
    if ejec == "widget_data_failed":
        return "No he podido: " + (str(parte.get("message") or "").strip() or "el widget no lo aceptó.")
    if ejec != "widget_data":
        return ack
    fallidas = parte.get("fallidas") or []
    if not fallidas:
        return ack
    # One succeeded and another failed: say what did NOT succeed, which is what the operator cannot see.
    return ack.rstrip(".") + f", pero una no: {str(fallidas[0].get('message') or '').strip() or 'el widget la rechazó.'}"
