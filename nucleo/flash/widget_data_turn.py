"""Ejecutar una data-op de widget desde un turno (extraído de `probe.py`, V2-383).

No cambia nada de lo que hacía: sale de `probe.py` porque es la MISMA preocupación que `music_turn` y
`video_turn` —un turno que ejecuta una operación de widget por el rail de la voz— y porque `probe.py` es un
fichero-dios con trinquete, así que meter la ejecución del vídeo obliga a sacar de él lo que ya no le
pertenece. La historia del bloque, que es la que explica por qué existe, viaja con él:

EJECUCIÓN REAL de una data-op (2026-07-25): sin esto el probe validaba el ROUTING pero nunca ENVIABA —
imposible reproducir e2e «manda a zalo …». Si la acción es FAST se despacha por el MISMO camino que la voz
(`widgets.dispatch_tag` → `apply_action` del widget). CONFIRM no se auto-confirma (requiere el sí del
operador); se reporta como pendiente. (V2-086: enviar al cluster ya NO pasa por aquí — es la tool
`cluster_send`, no una data-op de widget.)
"""
from __future__ import annotations


def _primera_clave(widget_id: str, action: str) -> str:
    """La PRIMERA clave del payload declarado de esta acción, o "" — leída del manifest, no supuesta.

    Es a donde va una referencia en lenguaje natural cuando la acción no declara campo de id: la primera
    clave es, por convención de todos los manifests, el dato principal de la acción (`url` en `youtube.add`,
    `item` en `imagenes.select`, `playlist` en `musica.add_to_playlist`). Data-driven a propósito: la
    alternativa era una tabla de widgets, que es justo lo que este árbol no quiere.
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
    """Despacha las data-ops del turno y devuelve el parte, o dice cuál saltó y POR QUÉ.

    V2-391 — VARIAS, no una. Cuáles entran lo decide `data_ops.admite_data_op`, compartido con la voz
    para que no pueda divergir: mismo widget y misma acción con payloads DISTINTOS sí (dos enlaces pegados),
    duplicado exacto no (la cita doble), acción distinta sobre el mismo widget tampoco (la enumeración).
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

    # V2-394 — `brain_action` y NO `dispatch_tag`: aquel se traga el resultado y devuelve None, así que con él
    # el turno NO PUEDE saber si la operación ocurrió, y la boca dice «Hecho.» pase lo que pase. Es la misma
    # razón exacta que ya está escrita en `video_turn.execute`, aquí en el caso general.
    from widgets.server_api import brain_action as _brain_action
    hechas, saltadas, fallidas = [], [], []
    for a in admitidas:
        wid = str(a.get("widget_id") or "").strip().lower()
        act = str(a.get("action") or "").strip()
        pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
        # LA REFERENCIA AL ITEM VIAJA (V2-463). La tool declara `item` como argumento propio («referencia en
        # lenguaje natural, nunca un id inventado») y este camino lo TIRABA: solo pasaba `payload`, así que
        # «ponme la 1, la del Spider» llegaba al widget como un select sin item — tres fallos medidos en una
        # ronda con el modelo diciendo «te la dejo puesta» encima. Se resuelve con el MISMO mecanismo que la
        # voz (`widgets.refs.resolve`, el id real contra lo que hay en pantalla, jamás inventado); si no
        # resuelve, el texto crudo viaja igual en el campo del id para que el resolver PROPIO del widget
        # (p. ej. el de `imagenes`, que casa por tokens) tenga su oportunidad y su negativa enseñe el menú.
        _ref = str(a.get("item") or "").strip()
        if _ref:
            try:
                from widgets import refs as _refs
                _rr = _refs.resolve(wid, act, _ref, pl)
                if getattr(_rr, "ok", False) and isinstance(_rr.payload, dict):
                    pl = _rr.payload
                # DÓNDE cae la referencia lo dice el MANIFEST, no una clave inventada (V2-467). Primero el
                # campo de id declarado; si la acción no tiene ninguno, su PRIMERA clave de payload, que es
                # la que el widget lee de verdad. Poner un literal `"item"` fue un defecto medido: el
                # operador pegó dos enlaces de YouTube, el modelo llamó a `add` con la referencia, y el
                # payload salió `{"item": "<enlaces>"}` — `youtube.add` lee `url`, así que contestó «dime
                # qué vídeo añado» con los dos enlaces delante. Con `imagenes.select` no se vio porque su
                # clave se llama, justamente, `item`.
                _campo = _refs.id_field_for_action(wid, act) or _primera_clave(wid, act) or "item"
                # Un manifest sin campo de id declarado hace que `resolve` conteste «ok, nada que resolver»
                # con el payload intacto — y la referencia se perdería. Si el modelo dio una y no aterrizó,
                # viaja cruda en esa clave: el resolver PROPIO del widget decide, y su negativa enseña el menú.
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
        # LA TARJETA SE ABRE DONDE ATERRIZAN LOS DATOS (V2-463, ahora también en el caso genérico). Medido
        # en `build-a-video-playlist-from-links`: el modelo ejecutó `name_list` y el informe marcó «ESCRITOS
        # PERO NUNCA ABIERTOS» — el operador no vio nada, así que «hecho» era invisible. Una data-op que
        # ESCRIBE es exactamente lo que el frontend ya usa para repintar una tarjeta abierta; que además la
        # abra cuando no lo está es la misma decisión, no una nueva. Idempotente en el navegador.
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
    # `widget`/`act` singulares se conservan: son la forma que ya leen el informe y los guardas de antes, y
    # cambiarla por una lista rompería la lectura sin avisar. Lo nuevo va al lado.
    parte = {"executed": "widget_data", "widget": hechas[0]["widget"], "act": hechas[0]["act"],
             "ops": hechas}
    # Lo que NO se hizo se DICE, en vez de dejar el parte contando solo lo que salió bien.
    if len(todas) > len(hechas):
        parte["descartadas"] = len(todas) - len(hechas)
    if saltadas:
        parte["sin_permiso"] = saltadas
    # Una op que salió mal viaja aunque OTRA saliera bien: «he añadido uno y el otro no lo encontré» es la
    # respuesta honesta, y quedarse con la buena es cómo un «Hecho.» a medias pasa por completo.
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


def named_ack(parte: dict, ack: str, operator_text: str = "") -> str:
    """A bare «Hecho.» to a QUESTION is a non-answer (V2-469, `build-a-video-playlist` 23:05): «¿Y qué hay
    en la lista?» → mute model over a redundant `add` → «Hecho.», twice, watchdog nudging both times and
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
    if "?" not in str(operator_text or ""):
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
            # The hint travels (V2-469, round 10): «¿y qué está sonando?» got the enumeration WITHOUT
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
    """Lo que se DICE tras una data-op. `ack` es el enlatado del idioma, solo para el caso bueno.

    «Hecho.» sobre una operación que el widget RECHAZÓ es la sexta vez que una frase enlatada nuestra es la
    que miente (V2-176 sobre una tarea recién arrancada, V2-209 sobre una tarjeta vacía, V2-377 sobre el
    encargo de otro, V2-380 sobre una reproducción que no existía, V2-383 sobre un vídeo que no cargó).
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
    # Salió bien una y mal otra: se dice lo que NO salió, que es lo que el operador no puede ver.
    return ack.rstrip(".") + f", pero una no: {str(fallidas[0].get('message') or '').strip() or 'el widget la rechazó.'}"
