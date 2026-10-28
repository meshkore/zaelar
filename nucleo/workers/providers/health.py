"""The chain's MEMORY of each rung: a failure noted with its reset, who is serving, the status the panel reads.
Part of nucleo.workers.providers; every package name is read through _p, so a patch of providers.<name> reaches it."""
from __future__ import annotations

from loguru import logger
import re
import time

from nucleo.workers import providers as _p


def note_tool_blindness(text: str, tool: str = "", provider: str = "") -> str:
    """Registra que el worker se ha quedado CIEGO y devuelve el detalle legible (o "" si no era eso).

    Alerta + timeline, sin tocar el relevo. Fila propia en el panel (`worker:tools`) para que no se confunda con
    «el proveedor de los workers está caído», que es otro problema con otra solución."""
    if not _p.classify_tool_failure(text):
        return ""
    # El culpable es el escalón con el que corría ESA sesión, no el primero de la cadena ahora: tras un relevo
    # son distintos, y nombrar al equivocado manda al operador a mirar el proveedor que sí funciona.
    name = provider or (_p.pick() or {}).get("name", "") or "el proveedor"
    when = _p._RESET_RE.search(text or "")
    detail = (f"las herramientas de búsqueda de «{name}» están sin cuota"
              + (f" (reset {when.group(1)})" if when else "")
              + " — el worker sigue razonando pero NO puede buscar ni leer páginas")
    logger.warning(f"brain worker CIEGO: {detail}")
    try:                     # V2-798: the next worker's step 0 learns it too, until the provider's own reset time
        from nucleo import source_outcomes as _so
        _so.note(f"search:{name}", _so.QUOTA, kind="search", detail=tool, until=_p._reset_epoch(text))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"source outcome for {name} not recorded: {e}")
    try:
        from voice import health_state
        health_state.record("worker_tools", "credit", detail)
    except Exception:
        pass
    try:
        from voice.observer import emit
        emit("alert", "🕶️ worker CIEGO — sin herramientas de búsqueda", text=detail, role="system",
             extra={"provider": name, "tool": tool, "reason": "tool_quota",
                    "raw": (text or "")[:300]})
    except Exception:
        pass
    return detail


def _reset_epoch(text: str) -> float:
    """Cuándo dice el proveedor que vuelve, en epoch local. 0.0 = no lo dice (el llamador aplica su suelo).

    Una hora SUELTA se resuelve sobre HOY; si ya pasó, es de mañana (a las 23:50 un «reset at 00:30» no es de hace
    23 horas). Sin esto, una hora del mismo día se leía como medianoche pasada y el cooldown nacía vencido."""
    m = _p._RESET_RE.search(text or "")
    if not m:
        return 0.0
    raw = m.group(1).strip().replace("T", " ")
    # `6:10am` → `6:10 AM`: strptime con %p exige el separador y no admite minúsculas pegadas.
    _mp = re.match(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s*(am|pm)$", raw, re.I)
    if _mp:
        raw = f"{_mp.group(1)} {_mp.group(2).upper()}"
    # Z.ai / BigModel write their stamp in THEIR clock, UTC+8, with no zone. Read as local it made the Madrid
    # cooldown six hours too long (measured 2026-09-28: «reset at 2026-09-29 01:39:02» on the API, «19:39» on the
    # operator's own usage page). Their errors carry a `[13xx]` business code; nobody else's do.
    if _p._ZAI_CODE_RE.search(text or ""):
        from datetime import datetime, timedelta, timezone
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone(timedelta(hours=8))).timestamp()
            except Exception:
                pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(raw, fmt))
        except Exception:
            pass
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):   # solo la hora → sobre el día de hoy
        try:
            hm = time.strptime(raw, fmt)
        except Exception:
            continue
        now = time.localtime()
        stamp = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                             hm.tm_hour, hm.tm_min, hm.tm_sec, 0, 0, -1))
        return stamp if stamp > time.time() else stamp + 86400.0
    return 0.0


def note_failure(text: str, tier: dict | None = None) -> dict | None:
    """Un worker murió por el PROVEEDOR: marca el escalón, avisa, y devuelve **la CAUSA con su relevo**.

    Es el punto que faltaba: hasta hoy este 429 se entregaba al operador como texto de resultado («API Error…»)
    y moría ahí — ni alerta en el panel, ni cambio de proveedor, ni registro.

    ⚠️ V2-713 R4 — DEVUELVE `{"kind", "provider", "next", "detail"}`, no el escalón de relevo suelto. Antes
    devolvía `nxt`, y el adaptador (`claude_session.py`) tenía que RECONSTRUIR la clasificación para decidir si
    avisaba: `if nxt is not None or classify_failure(texto)`. Esa condición tiene un agujero medido — `broken`
    lo reconoce `is_broken_request`, NO `classify_failure`, así que un `broken` **sin relevo** ponía el escalón
    en cooldown y **no emitía ningún chip**: el operador veía morir al worker sin una sola palabra de por qué,
    con la causa perfectamente conocida una capa más arriba. En la base real del operador hay filas exactamente
    de esa forma (`API Error: 400 [1210]`, `ok:false`, `status:error`).

    La causa se calcula UNA vez, aquí, y viaja. Nadie aguas abajo vuelve a mirar el texto: `session.py` rotula
    por `kind`, que es dato, en vez de escribir siempre «proveedor sin cuota» — que era lo que hacía, incluso
    cuando la causa era una credencial rechazada.

    `None` solo cuando no hay nada que clasificar (rate-limit pasajero, licencia local): ausencia de causa, no
    ausencia de relevo. Los dos se distinguen ahora, y antes no.
    """
    kind = _p.classify_failure(text) or ("broken" if _p.is_broken_request(text) else "")
    if not kind:
        return None
    t = tier or _p.pick()
    if not t or not t.get("base_url"):
        return None                                  # la licencia local no se pone en cooldown por esto

    dry = _p.is_depleted(text)
    if kind == "broken":
        until = time.time() + _p._BROKEN_COOLDOWN_S     # V2-682 — see `is_broken_request`
    elif kind == "exhausted":
        # Same floor as `nucleo/llm/provider_chain.py` (2026-08-09): an already PAST reset date freed the tier
        # at once → self-relay loop. V2-243: an empty BALANCE has nothing to wait for.
        until = (time.time() + _p._DEPLETED_COOLDOWN_S) if dry \
            else max(_p._reset_epoch(text), time.time() + _p._DEFAULT_COOLDOWN_S)
    elif kind == "auth":
        until = time.time() + _p._AUTH_COOLDOWN_S
    else:
        return None                                  # rate-limit pasajero: no releves, se reintenta solo

    _p._store.set(t["name"], until)

    nxt = _p.pick()
    when = time.strftime("%d %b %H:%M", time.localtime(until))
    # V2-243: the operator acts on this panel text — a quota says «wait», a balance says «top up»; a time where
    # nothing will happen is worse than none.
    if kind == "broken":
        estado = f"RECHAZA nuestras peticiones (no es cuota ni credencial) — reintento a las {when}"
    elif dry:
        estado = "SIN SALDO — no vuelve solo, hay que recargar"
    else:
        estado = f"sin cuota hasta el {when}"
    detail = (f"«{t['name']}» ({t.get('plan', '')}) {estado}"
              + (f" → relevo a «{nxt['name']}»" if nxt else " · SIN RELEVO disponible"))
    logger.warning(f"brain worker: {detail}")

    # (1) al panel de ALERTAS, por el mismo canal reactivo que usan los demás proveedores
    try:
        from voice import health_state
        health_state.record("code_agent",
                            {"exhausted": "credit", "auth": "auth"}.get(kind, "outage"), detail)
    except Exception:
        pass
    # (2) al timeline, con el mismo peso que una degradación del motor
    try:
        from voice.observer import emit
        emit("perf", f"🔌 proveedor de workers: {detail}", role="system",
             extra={"provider": t["name"], "kind": kind, "until": until,
                    "next": (nxt or {}).get("name", ""), "text": (text or "")[:300]})
    except Exception:
        pass
    return {"kind": kind, "provider": t["name"], "next": (nxt or {}).get("name", ""), "detail": detail}


def _serving() -> set[str]:
    """Qué escalones están sirviendo AHORA MISMO a una sesión viva.

    «EN USO» y «el que se elegiría» son preguntas DISTINTAS, y confundirlas hacía mentir al panel: tras un relevo,
    el que trabaja es el de relevo y el que se elegiría vuelve a ser el primero de la cadena en cuanto su cooldown
    expira. La fila decía «EN USO · disponible» de un proveedor que no estaba haciendo nada (hallazgo de un e2e
    real, 2026-08-10). Best-effort: si el registro de sesiones no está disponible, se cae al comportamiento de antes.
    """
    try:
        from nucleo import dispatch
        by_url = {t.get("base_url", ""): t["name"] for t in _p.chain()}
        out = set()
        for r in dispatch._SESSIONS.values():
            if r.status not in ("queued", "running"):
                continue
            s = getattr(r, "session", None)
            url = getattr(s, "_base_url", "") if s else ""
            name = by_url.get(url or "")
            if name:
                out.add(name)
        return out
    except Exception:
        return set()


def status() -> list[dict]:
    """Estado de cada escalón para el panel: `[{name, plan, state, detail, active, serving}]`."""
    now = time.time()
    active = _p.pick()
    serving = _p._serving()
    out = []
    for t in _p.chain():
        until = _p._store.until(t["name"])
        if until > now:
            state = "error"
            detail = f"sin cuota hasta el {time.strftime('%d %b %H:%M', time.localtime(until))}"
        else:
            state = "ok"
            detail = "disponible"
        # `serving` = está trabajando de verdad · `active` = es el que se elegiría para el próximo worker. Con un
        # relevo en marcha no son el mismo, y el panel tiene que poder decir cuál es cuál.
        out.append({"name": t["name"], "plan": t.get("plan", ""), "state": state, "detail": detail,
                    "serving": t["name"] in serving,
                    "active": bool(active and active["name"] == t["name"])})
    return out


def clear(name: str = "") -> None:
    """Levanta el cooldown (el operador recargó el plan y no quiere esperar al reset)."""
    _p._store.clear(name)


def exhausted_until() -> float:
    """Epoch at which the chain gets its first healthy tier back — `0.0` when one is available RIGHT NOW.

    `pick() is None` means TWO different worlds and no caller can tell them apart:

      · an EMPTY chain — self-host with no keys — where `env_for_worker()` returning `{}` is the fail-open this
        module promises: run the local Claude license exactly as before;
      · a chain whose every tier is in COOLDOWN, where `{}` means «run the local license» too — except the
        license is itself one of those tiers, and we put it there ourselves because it just answered
        «You've hit your session limit».

    So the cooldown we record for the LICENSE tier could never bite: measured in `find-concert-tickets__es`
    (2026-08-25 10:53-10:56), the license was marked out-of-quota until 14:20 and then spawned into TWICE more
    inside three minutes — 1.8 s, 3.9 s, 1.9 s of life, three dead workers, four minutes of the round, and a
    person told three times that a search was starting. Eleven of the twenty-eight empty-sheet rounds have this
    shape.

    The distinction lives here, next to `chain()`, because that is the only place that knows whether the chain is
    empty or merely asleep. Reading it anywhere else means recomputing the chain, and two readings derive.
    """
    ch = _p.chain()
    if not ch:
        return 0.0                                  # nothing configured: the license path, as always
    now = time.time()
    untils = [_p._store.until(t["name"]) for t in ch]
    if any(u <= now for u in untils):
        return 0.0                                  # at least one tier is healthy → spawn away
    return min(untils)                              # the earliest one back is when work becomes possible again


def exhausted_reason() -> str:
    """One operator-facing sentence for `exhausted_until()`, or `""` when work is possible.

    Carries the HOUR because that is the only actionable part: «no quota» invites a retry in ten seconds,
    «back at 14:20» does not."""
    until = _p.exhausted_until()
    if not until:
        return ""
    from i18n import langs as _lg   # the operator's language (2026-10-11: an EN round was told this in Spanish)
    return _lg.current_language().worker_chain_asleep.format(hour=time.strftime('%H:%M', time.localtime(until)))
