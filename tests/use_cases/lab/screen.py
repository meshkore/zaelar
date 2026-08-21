"""What is ON SCREEN right now — read from the engine, never from a browser.

The judge's question is «did the right thing open, with the right content in it». A screenshot answers
it badly: it needs a browser, it costs seconds, and it turns "the agent opened the results sheet with
three plumbers in it" into pixels somebody then has to interpret. Every fact needed is already served
by the engine, so this reads it.

TWO SOURCES THAT DO NOT SAY THE SAME THING, and keeping them apart is the whole point:

  · WHAT THE AGENT ORDERED — the `widget` events (`show` / `close` / `data`) the server emitted. This is
    the intent, it exists whether or not anyone is watching, and it is what a headless round can judge.
  · WHAT THE CANVAS CONFIRMS — `state.open_widgets`, written by the FRONTEND, which is authoritative
    about the canvas (V2-035). With no browser connected it is EMPTY, and empty here means «nobody was
    looking», never «nothing opened». Reporting the two as one number would invent a fact: it would say
    the agent failed to open a widget it did open.

`layout` is the server's geometry safety net (`GET /api/canvas/layout`, kept in `sys_kv` since V2-117) —
position and size as the last browser left them, which is what survives a refresh.
"""
from __future__ import annotations

import json
import urllib.request

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _get(base: str, path: str, timeout: float = 10.0):
    req = urllib.request.Request(base + path, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def _ordered_by_events(base: str, limit: int = 2000) -> tuple[list[str], list[dict]]:
    """Replay the server's own `widget` events and return (open set, the trail that produced it).

    In order, because `show` then `close` on the same id is a widget that is NOT on screen and a set
    built by union would say it is. The trail comes back too: a judge that only gets the final set
    cannot tell «never opened» from «opened and closed again», and those are different failures.
    """
    ev = _get(base, f"/api/observability/events?limit={limit}") or {}
    rows = [e for e in (ev.get("events") or []) if str(e.get("kind")) == "widget"]
    rows.sort(key=lambda e: e.get("id") or 0)
    live: list[str] = []
    trail: list[dict] = []
    for e in rows:
        label = str(e.get("label") or "")
        wid, src = _widget_of(e)
        trail.append({"id": e.get("id"), "label": label, "widget": wid, "src": src,
                      "ts": e.get("ts_ms") or e.get("ts"), "corr": e.get("corr_id") or e.get("corr")})
        if not wid:
            continue
        if label == "show" and wid not in live:
            live.append(wid)
        elif label in ("close", "delete") and wid in live:
            live.remove(wid)
        elif label == "closeAll":
            live.clear()
    return live, trail


def _widget_of(e: dict) -> tuple[str, str]:
    """(widget id, who ordered it) — read from the event's own `payload`, not guessed from its text.

    The row served by `/api/observability/events` carries the columns the sink promotes (`kind`, `label`,
    `corr_id`…) and keeps everything else inside `payload` AS A JSON STRING. The first version of this
    reader took the tail of `text`, which is empty on these events, so every widget came back nameless
    and the screen read «(nada)» while four cards were open. A field read at the wrong level does not
    fail — it invents a fact, and the fact it invented here was that the agent had opened nothing.

    `src` is worth as much as the id: `system` is the engine, `worker:1` is a Brain Worker opening its
    own card. «Did the right thing open» and «did the right ACTOR open it» are different questions.
    """
    pl = e.get("payload")
    if isinstance(pl, str):
        try:
            pl = json.loads(pl)
        except Exception:
            pl = {}
    if not isinstance(pl, dict):
        pl = {}
    wid = str(pl.get("id") or "").strip()
    if not wid:
        x = e.get("extra") or {}
        wid = str(x.get("widget") or x.get("id") or "").strip()
    return wid, str(pl.get("src") or "").strip()


def read(base: str, *, with_data: bool = True) -> dict:
    ordered, trail = _ordered_by_events(base)
    mem = _get(base, "/api/memory/map") or {}
    state = mem.get("state") or {}
    canvas = [str(w) for w in (state.get("open_widgets") or [])]
    layout = ((_get(base, "/api/canvas/layout") or {}).get("items")) or []
    tasks = ((_get(base, "/api/tasks") or {}).get("sessions")) or []

    data: dict = {}
    if with_data:
        for wid in ordered:
            base_id = wid.split("::")[0]
            d = _get(base, f"/widgets/{base_id}/data")
            if d is not None:
                data[wid] = d
    return {
        "opened_by_agent": ordered,       # what the server ordered onto the canvas, in order
        "confirmed_by_canvas": canvas,    # what a live browser reports back — EMPTY means nobody watched
        "watched": bool(canvas),
        "layout": layout,
        "tasks": tasks,
        "widget_trail": trail,
        "data": data,
    }


def _summary(wid: str, d: dict) -> str:
    """One line saying what is INSIDE a widget, so the judge does not have to read a JSON dump.

    Deliberately generic: `title` + how many `items`, plus the live-progress fields of the results
    sheet. Naming a specific widget here would make the reader work for the cases it was written
    against and go quiet on the next one.
    """
    if not isinstance(d, dict):
        return "(sin datos)"
    bits = []
    t = str(d.get("title") or "").strip()
    if t:
        bits.append(f"«{t[:70]}»")
    items = d.get("items")
    if isinstance(items, list):
        bits.append(f"{len(items)} item(s)")
    pr = d.get("progress")
    if isinstance(pr, dict):
        bits.append(f"progreso: {'vivo' if pr.get('alive') else 'parado'}, "
                    f"{len(pr.get('phases') or [])} fase(s)")
    return " · ".join(bits) or "(sin título ni items)"


def render(snap: dict) -> str:
    out = []
    op = snap["opened_by_agent"]
    out.append(f"PANTALLA · el agente ordenó abrir: {', '.join(op) if op else '(nada)'}")
    if snap["watched"]:
        out.append(f"           el canvas confirma:    {', '.join(snap['confirmed_by_canvas'])}")
    else:
        out.append("           el canvas no confirma nada — NO hay navegador conectado "
                   "(vacío aquí no significa que no se abriera)")
    for wid in op:
        out.append(f"   ▸ {wid}: {_summary(wid, snap['data'].get(wid) or {})}")
    if snap["layout"]:
        pos = ", ".join(f"{it.get('id')}@({it.get('x')},{it.get('y')} {it.get('w')}×{it.get('h')})"
                        for it in snap["layout"][:6])
        out.append(f"   geometría guardada (sobrevive a un refresh): {pos}")
    tasks = snap["tasks"]
    out.append(f"PROCESOS · {len(tasks)}")
    for t in tasks[:6]:
        out.append(f"   ▸ [{t.get('id')}] {t.get('kind')} · {t.get('status')} · {t.get('phase')} · "
                   f"{t.get('age_s')}s callado {t.get('silent_s')}s · "
                   f"{str(t.get('goal') or '')[:60]}")
    return "\n".join(out)
