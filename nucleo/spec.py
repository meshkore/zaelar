"""nucleo/spec.py — a request is born with its END STATE (V2-776 L1).

## The incident

Demo pass 60, B1 (2026-09-29): «now let's make it prettier, find me the wallpaper cosmic eye in the sky by
tyler young». The turn escalated a worker whose brief was «Find the wallpaper/artwork titled…». The end state
the operator meant — *the desktop wallpaper has changed to that image* — was written nowhere: the escalation
travelled as `{src, surface, asked}`, the worker's own `done_when` is optional and its prompt exempted «a
search», and the turn harness knows one kind of goal (a shown card has content). B2 «set the first one as my
background» then completed, through the screen verdict, as `results:choose` on the only open sheet — the
monitors — and U2 had the worker asking for an OK to click a Dell. The same block had passed in 56, 58 and 59.
Nothing that existed could have caught it, because nothing knew what «done» meant for that request.

## The split (principles.md, the Brain Worker doctrine §2)

**The model writes the CONTENT of the spec; the engine owns the grammar, the check, the bound and the report.**
The same shape `party.py` has — one JSON, the engine executes — applied to endings. `workers/goal.py` already
said so; this makes it the door instead of the exception:

  · an INLINE widget action carries its postcondition in the widget's manifest (`actions.<a>.done_when`, a
    template over its payload) — the one place rails belong — rendered at the one door every data-op crosses;
  · an ESCALATION carries the spec the model wrote in the escalate call (`done_when`), in `verify.py`'s grammar;
    when it wrote none, the errand is asked for it once (`infer`, a model call the size of the errand namer) —
    «acabar de definir la request al principio» — and marked UNVERIFIABLE when nothing readable comes back;
  · the turn's own verdict (`end_state`, one more question of the brief) names which attestable end state the
    phrase implies, and a verdict COMPLETION is refused when the action it would fire attests a different one
    (B2: `results:choose` cannot attest `desktop:wallpaper`).

Unreadable is NEVER failure (V2-660, kept verbatim). A spec the engine cannot read says so and stays out of
every retry loop; the cure for unreadable is a readable widget (L2), never a guess.

## The ledger

RAM (`_OPEN`, bounded, 30 min) for the turn and the pulse; the `tasks` row's `spec` artifact for an errand,
so a restart does not lose what «done» meant. L3 makes the pulse re-verify this ledger and close on it.
"""
from __future__ import annotations

import copy
import json
import re
import time

from loguru import logger

TEMPLATE_KEY = "done_when"          # in a manifest action spec
END_KEY = "end_state"               # the brief question
ARTIFACT_SLOT = "spec"
TTL_S = 1800.0
_MAX = 24
_OPEN: list[dict] = []
_PLACEHOLDER = re.compile(r"^\{([a-zA-Z_][a-zA-Z0-9_]*)(\?)?\}$")


# ── templates: what a widget action declares it leaves true ───────────────────────────────────────────────

def _manifest(wid: str) -> dict:
    try:
        from widgets import runtime
        return runtime.get(str(wid or "").split("::", 1)[0].strip().lower()) or {}
    except Exception:  # noqa: BLE001
        return {}


def template_of(wid: str, action: str) -> dict | None:
    """The `done_when` template the widget declares for this action, or None."""
    spec = ((_manifest(wid).get("actions") or {}).get(str(action or "").strip()))
    tpl = spec.get(TEMPLATE_KEY) if isinstance(spec, dict) else None
    return copy.deepcopy(tpl) if isinstance(tpl, (dict, list)) else None


def _fill(node, payload: dict):
    """Placeholders `{key}` are the payload's values; `{key?}` is dropped (with its key) when absent. A required
    placeholder with no value makes the whole template unrenderable → None (unverifiable, never a guess)."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if isinstance(v, str) and (m := _PLACEHOLDER.match(v)):
                key, optional = m.group(1), bool(m.group(2))
                val = payload.get(key)
                if val in (None, "") or isinstance(val, (dict, list)):
                    if optional:
                        continue
                    return None
                out[k] = val
            else:
                got = _fill(v, payload)
                if got is None and v is not None:
                    return None
                out[k] = got
        return out
    if isinstance(node, list):
        out = []
        for v in node:
            got = _fill(v, payload)
            if got is None and v is not None:
                return None
            out.append(got)
        return out
    return node


#: Cards whose content lives in per-errand INSTANCES (`<base>::<sheet>`): a clause naming the bare base reads an
#: empty card (demo pass 64: «results.empty = false» read bare `results` while the monitors sat on
#: `results::135b0e-ls1`, so a delivered hunt was judged unmet and relaunched).
SHEET_CARDS = ("results",)


def bind_sheet(done_when, sheet: str):
    """`done_when` with every clause on a sheet card bound to the errand's own sheet. Pure; never raises."""
    sheet = str(sheet or "").strip()
    if not sheet or not isinstance(done_when, (dict, list)):
        return done_when
    import copy
    dw = copy.deepcopy(done_when)
    from nucleo import verify as _verify
    _mode, clauses = _verify._clauses(dw)
    for c in clauses:
        for key in ("widget", "canvas"):
            w = str(c.get(key) or "").strip()
            if w in SHEET_CARDS:
                c[key] = f"{w}::{sheet}"
    return dw


def _snapshot(done_when) -> None:
    """A clause with `expect: changed` remembers what the value WAS at birth — the only honest reading of «set
    it as my background» when the phrase names an index, not a title."""
    from nucleo import verify as _verify
    _mode, clauses = _verify._clauses(done_when)
    for c in clauses:
        if str(c.get("expect") or "").lower() == "changed" and "baseline" not in c:
            c["baseline"] = _verify.current_value(c)


def render(wid: str, action: str, payload: dict | None) -> dict | None:
    """The action's postcondition, rendered over this payload, baselines taken. None = nothing declared or
    nothing renderable."""
    tpl = template_of(wid, action)
    if tpl is None:
        return None
    filled = _fill(tpl, dict(payload or {}))
    if not filled:
        return None
    # Demo pass 70, S2/S3: «compare them side by side» and «open the best deal» ran on `results::9642d4-ls1` and the
    # template's clauses — written over the BASE card — read the bare `results` sheet, empty: both read «unmet» over
    # an op that worked, and the circuit would have said so out loud. The op's own instance is what it changed.
    base, _, inst = str(wid or "").partition("::")
    if inst:
        from nucleo import verify as _verify
        for c in _verify._clauses(filled)[1]:
            for key in ("widget", "canvas"):
                if str(c.get(key) or "").strip().lower() == base.strip().lower():
                    c[key] = str(wid)
    try:
        _snapshot(filled)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"spec: baseline unreadable for {wid}:{action}: {e}")
    return filled


def target_of(done_when) -> str:
    """The attestable target a spec names: `desktop:wallpaper`, `agenda:meetings`, `youtube:videoId`,
    `canvas:results`. The FIRST clause names it; what the phrase is about is one thing."""
    from nucleo import verify as _verify
    _mode, clauses = _verify._clauses(done_when)
    for c in clauses:
        if c.get("desktop"):
            return f"desktop:{c['desktop']}"
        if c.get("canvas"):
            return f"canvas:{str(c['canvas']).split('::', 1)[0]}"
        wid = str(c.get("widget") or "").split("::", 1)[0].strip().lower()
        if wid and c.get("field"):
            return f"{wid}:{c['field']}"
        if wid:
            coll = str(c.get("collection") or "").strip()
            return f"{wid}:{coll}" if coll else wid
    return ""


def attestable(open_ids=None) -> dict[str, str]:
    """`target → what it means`, for the brief question and the escalate schema: every declared template of the
    cards on screen, plus the targets of the specs open now (a closed card whose end state is still owed — B2:
    imagenes was closed and the wallpaper was the thing he was talking about)."""
    out: dict[str, str] = {}
    seen_w = set()
    for wid in list(open_ids or []):
        base = str(wid or "").split("::", 1)[0].strip().lower()
        if not base or base in seen_w:
            continue
        seen_w.add(base)
        for name, spec in (_manifest(base).get("actions") or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get(TEMPLATE_KEY), (dict, list)):
                t = target_of(spec[TEMPLATE_KEY])
                if t and t not in out:
                    out[t] = f"{base}:{name} — {str(spec.get('desc') or '')[:120]}"
    for e in open_specs():
        t = target_of(e.get("done_when"))
        if t and t not in out:
            out[t] = f"the end state still owed by «{str(e.get('text') or '')[:80]}»"
    return out


def catalogue() -> dict[str, str]:
    """Every declared template in the catalogue, `target → widget:action` — what the escalate schema lists."""
    out: dict[str, str] = {}
    try:
        from widgets import runtime as _rt
        for w in _rt.catalog():
            base = str(w.get("id") or "").strip().lower()
            for name, spec in ((_manifest(base).get("actions") or {}) if base else {}).items():
                if isinstance(spec, dict) and isinstance(spec.get(TEMPLATE_KEY), (dict, list)):
                    t = target_of(spec[TEMPLATE_KEY])
                    if t:
                        out.setdefault(t, f"{base}:{name}")
    except Exception:  # noqa: BLE001
        pass
    return out


# ── the brief question and the completion gate ────────────────────────────────────────────────────────────

END_INSTRUCTIONS = (
    "When this order is DONE, which of these end states will be true? They are what the widgets can attest "
    "(a wallpaper set, a meeting in the calendar, a video playing, a message sent, a section of the document "
    "in view). Answer 'none' when the order leaves none of them true — a question, a remark, a close, a scroll.")


def end_state_question(open_ids=None) -> dict | None:
    """One enumerated question over the attestable end states, or None when there is nothing to enumerate."""
    targets = attestable(open_ids)
    if not targets:
        return None
    criteria = {t: text[:160] for t, text in list(targets.items())[:40]}
    criteria["none"] = "the order leaves none of these true"
    return {"instructions": END_INSTRUCTIONS, "criteria": criteria}


def end_state_verdict(brief) -> str:
    """The target the brief named, sure; "" when none, unsure, absent or 'none'."""
    if not brief:
        return ""
    try:
        from nucleo.flash import turn_brief as _tb
        choice, _info = _tb.read(brief, END_KEY, "")
        raw = str(choice or "").strip()
        return "" if raw in ("", "none") else raw
    except Exception:  # noqa: BLE001
        return ""


def gate_completion(brief, wid: str, action: str) -> str:
    """Why a verdict COMPLETION of `wid:action` must not fire, or "" when it may.

    B2 (pass 60): the phrase's end state was the wallpaper; the only open card was the monitors sheet, and the
    empty turn was completed as `results:choose`. A completion is the ENGINE's own inference (the model called
    nothing), so it is held to the engine's own reading of the phrase: when the brief names an attestable end
    state, the completed action has to be one that attests it. A valid call of the model is not gated here
    (V2-754: a valid call runs, whatever the verdict says)."""
    want = end_state_verdict(brief)
    if not want:
        return ""
    tpl = template_of(wid, action)
    have = target_of(tpl) if tpl is not None else ""
    if have == want:
        return ""
    return (f"the phrase's end state is «{want}» and {str(wid).split('::', 1)[0]}:{action} attests "
            + (f"«{have}»" if have else "nothing"))


# ── the ledger ────────────────────────────────────────────────────────────────────────────────────────────

SETTLED_S = 300.0                  # a met/unverifiable spec stays readable for five minutes (the pulse, the prompt)


def _sweep(now: float) -> None:
    def keep(e: dict) -> bool:
        age = now - float(e.get("born") or 0)
        return age < TTL_S if e.get("status") == "open" else (now - float(e.get("met_at") or e.get("born") or 0)) < SETTLED_S
    _OPEN[:] = [e for e in _OPEN if keep(e)]
    del _OPEN[:-_MAX]


def _emit(label: str, e: dict, **extra) -> None:
    try:
        from nucleo import verify as _verify
        from voice.observer import emit
        ex = {"id": e.get("id"), "target": e.get("target"), "source": e.get("source"),
              "task_id": e.get("task_id"), "status": e.get("status"), "cat": "spec", **extra}
        if e.get("trace"):
            ex["trace"] = e["trace"]
        emit("spec", label, text=_verify.describe(e.get("done_when")) or str(e.get("text") or "")[:120],
             role="system", extra=ex)
    except Exception:  # noqa: BLE001
        pass


def open(done_when, *, text: str = "", source: str = "", widget: str = "", action: str = "",
         task_id: str = "", trace: str = "", now: float | None = None) -> dict | None:  # noqa: A001
    """Remember one end state that is now owed. None when there is nothing readable to remember."""
    from nucleo import verify as _verify
    if not _verify._clauses(done_when)[1]:
        return None
    now = time.time() if now is None else now
    _sweep(now)
    e = {"id": f"s{int(now * 1000) % 10_000_000}", "done_when": copy.deepcopy(done_when),
         "target": target_of(done_when), "text": str(text or "")[:300], "source": str(source or ""),
         "widget": str(widget or ""), "action": str(action or ""), "task_id": str(task_id or ""),
         "trace": str(trace or ""), "born": now, "status": "open", "last": None, "checks": 0, "tries": 0}
    _OPEN.append(e)
    del _OPEN[:-_MAX]
    if e["task_id"]:
        persist(e["task_id"], e)
    _emit("🎯 spec: nace con la petición", e)
    return e


def open_specs(now: float | None = None) -> list[dict]:
    """The end states still OWED (status open). `settled()` has the ones that just closed."""
    _sweep(time.time() if now is None else now)
    return [e for e in _OPEN if e.get("status") == "open"]


def settled(now: float | None = None) -> list[dict]:
    _sweep(time.time() if now is None else now)
    return [e for e in _OPEN if e.get("status") != "open"]


def reset() -> None:
    _OPEN.clear()


def attest(e: dict | None, *, now: float | None = None) -> bool | None:
    """Read the spec against the product now: True met (closed), False unmet (stays open), None unreadable."""
    if not e:
        return None
    from nucleo import verify as _verify
    e["checks"] = int(e.get("checks") or 0) + 1
    try:
        out = _verify.check(e.get("done_when"), now)
    except Exception:  # noqa: BLE001
        out = None
    e["last"] = out
    if out is True:
        e["status"] = "met"
        e["met_at"] = time.time() if now is None else now
        _emit("✅ spec: cumplida", e)
    elif out is False:
        _emit("❌ spec: sin cumplir todavía", e, missing="; ".join(_verify.missing(e.get("done_when"), now))[:300])
    elif e.get("last_seen") != "unreadable":
        _emit("🫥 spec: no verificable — la tarjeta no lo declara", e)
    e["last_seen"] = {True: "met", False: "unmet"}.get(out, "unreadable")
    if e.get("task_id"):
        persist(e["task_id"], e)
    return out


def open_for_action(wid: str, action: str, payload: dict | None, *, text: str = "", source: str = "flash",
                    trace: str = "") -> dict | None:
    """The one call the data-op door makes BEFORE the op runs (the baseline of a `changed` clause is what the
    value was before): the action's rendered postcondition becomes an open spec, or nothing when the widget
    declares none."""
    try:
        dw = render(wid, action, payload)
        if not dw:
            return None
        return open(dw, text=text, source=source, widget=wid, action=action, trace=trace)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"spec: no spec for {wid}:{action}: {e}")
        return None


# ── durability ────────────────────────────────────────────────────────────────────────────────────────────

def persist(task_id: str, e: dict) -> None:
    try:
        from nucleo import tasks as _tasks
        _ts = _tasks.store()   # nucleo/tasks is memory.tasks_store's one importer
        _ts.artifact_put(task_id, ARTIFACT_SLOT, {
            "done_when": e.get("done_when"), "target": e.get("target"), "source": e.get("source"),
            "text": e.get("text"), "born": e.get("born"), "status": e.get("status"), "last": e.get("last"),
            "checks": e.get("checks"), "tries": e.get("tries"), "unverifiable": bool(e.get("unverifiable"))})
    except Exception:  # noqa: BLE001
        pass


def of_task(task_id: str) -> dict | None:
    try:
        from nucleo import tasks as _tasks
        _ts = _tasks.store()   # nucleo/tasks is memory.tasks_store's one importer
        got = _ts.artifact_get(task_id, ARTIFACT_SLOT)
        return got if isinstance(got, dict) else None
    except Exception:  # noqa: BLE001
        return None


# ── the errand: born with it, asked for once, told to the worker ──────────────────────────────────────────

def born(rec, ctx: dict | None = None) -> None:
    """Called where every commission is recorded (`nucleo/tasks.opened`). With a `done_when` on the record it
    opens the spec and persists it; without one it asks for it ONCE, off the hot path, and tells the worker.
    Never raises, never waits."""
    try:
        import asyncio
        dw = dict(getattr(rec, "done_when", None) or {})
        uid = str(getattr(rec, "uid", "") or "")
        if dw and not (ctx or {}).get("relay_gen"):
            # Demo pass 62: the model's own `done_when` on `escalate` was born without a baseline («the wallpaper
            # CHANGED» could never be judged → «unverifiable», and the ending said «I couldn't verify it») and
            # unsanitised (`documento.documents`, a collection nobody declares). It goes through what an inferred
            # one does; nothing readable left → inferred, as if it had come without one.
            dw = _sanitize(dw) or {}
            if dw:
                dw = bind_sheet(dw, (ctx or {}).get("sheet") or getattr(rec, "sheet", ""))
                _snapshot(dw)
                try:
                    rec.done_when = dw
                except Exception:  # noqa: BLE001
                    pass
        if dw:
            e = open(dw, text=str(getattr(rec, "goal", "") or ""), source=str((ctx or {}).get("src") or "worker"),
                     task_id=uid, trace=str(getattr(rec, "trace_id", "") or ""))
            if e:
                _schedule(_tell_worker(rec, e))
            return
        if (ctx or {}).get("relay_gen"):
            return                          # a relay continues an errand whose spec is already on the row
        _schedule(_ask_once(rec, ctx or {}))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"spec: born skipped: {e}")


_BG: set = set()


def _schedule(coro) -> None:
    import asyncio
    try:
        t = asyncio.ensure_future(coro)
        _BG.add(t)
        t.add_done_callback(_BG.discard)
    except RuntimeError:
        coro.close()


async def _ask_once(rec, ctx: dict) -> None:
    """The errand came without its end state: one model call the size of the errand namer writes it in the
    grammar, or says there is none readable — and then the errand is UNVERIFIABLE, which is a state the
    operator hears at the end, never «It is done»."""
    dw = await infer(str(getattr(rec, "goal", "") or ""))
    uid = str(getattr(rec, "uid", "") or "")
    if not dw:
        e = {"id": f"u{int(time.time() * 1000) % 10_000_000}", "done_when": {}, "target": "",
             "text": str(getattr(rec, "goal", "") or "")[:300], "source": str(ctx.get("src") or "worker"),
             "task_id": uid, "born": time.time(), "status": "unverifiable", "unverifiable": True,
             "last": None, "checks": 0, "tries": 0}
        try:
            rec.spec_unverifiable = True
        except Exception:  # noqa: BLE001
            pass
        if uid:
            persist(uid, e)
        _emit("🫥 spec: el encargo no acaba en nada que un widget pueda atestiguar", e)
        return
    dw = bind_sheet(dw, ctx.get("sheet") or getattr(rec, "sheet", ""))
    try:
        rec.done_when = dict(dw)
    except Exception:  # noqa: BLE001
        pass
    e = open(dw, text=str(getattr(rec, "goal", "") or ""), source=f"{ctx.get('src') or 'worker'}+inferred",
             task_id=uid, trace=str(getattr(rec, "trace_id", "") or ""))
    if e:
        await _tell_worker(rec, e)


def worker_line(done_when) -> str:
    from nucleo import verify as _verify
    said = _verify.describe(done_when)
    if not said:
        return ""
    return ("OBJETIVO MEDIBLE (nació con el encargo; el motor lo comprueba contra la verdad del producto al "
            f"acabar y te relanza con lo que falte): {said}. Si al entender el encargo ves que la condición es "
            "otra, afínala con 'python -m nucleo.agent_report goal @objetivo.json'; nunca la retires.")


async def _tell_worker(rec, e: dict, *, wait_s: float = 90.0) -> None:
    """The worker hears what «done» means as its first injected turn. Waits for the session to exist; a
    record still queued in the pool gets it by piggyback, as any injection does."""
    import asyncio
    line = worker_line(e.get("done_when"))
    if not line:
        return
    t0 = time.time()
    while getattr(rec, "session", None) is None and time.time() - t0 < wait_s:
        if str(getattr(rec, "status", "") or "") in ("done", "error", "cancelled", "relevada"):
            return
        await asyncio.sleep(0.5)
    try:
        if getattr(rec, "session", None) is not None:
            await rec.session.inject(line)
        else:
            from nucleo.workers.session import Inject
            rec.injects.append(Inject(text=line, ts=time.time()))
    except Exception as ex:  # noqa: BLE001
        logger.debug(f"spec: could not tell the worker its goal: {ex}")


_INFER_TIMEOUT_S = 12.0


def _readable() -> dict[str, dict]:
    """What each card DECLARES a spec can read — its collections (manifest) and whether it declares `empty`
    (its view). Live pass 62, A1: the model wrote `results.view[title~=27]` for a monitor hunt — a collection no
    card declares — and the spec was born unverifiable. It can only name what is here."""
    out: dict[str, dict] = {}
    try:
        from widgets import rows as _rows, runtime as _rt
        from nucleo import truth as _truth
        for w in _rt.catalog():
            base = str(w.get("id") or "").strip().lower()
            if not base:
                continue
            cols = sorted(_rows.declared(base))
            view = _truth.widget_view(base) or {}
            has_empty = isinstance(view, dict) and "empty" in view
            if cols or has_empty:
                out[base] = {"collections": cols, "empty": has_empty}
    except Exception:  # noqa: BLE001
        pass
    return out


def _sanitize(done_when: dict) -> dict | None:
    """Keep only the clauses the product can read: a rows clause needs a DECLARED collection; one over an
    undeclared collection of a card that declares `empty` becomes «the card is not empty» (what the model meant:
    something landed there). Nothing readable left → None, and the spec is honestly unverifiable at birth."""
    from nucleo import verify as _verify
    from widgets import rows as _rows
    mode, clauses = _verify._clauses(done_when)
    kept: list[dict] = []
    for c in clauses:
        if _verify.kind_of(c) != "rows":
            kept.append(c)
            continue
        wid = str(c.get("widget") or "").strip().lower().split("::", 1)[0]
        coll = str(c.get("collection") or "").strip()
        if coll and coll in _rows.declared(wid):
            kept.append(c)
            continue
        try:
            from nucleo import truth as _truth
            view = _truth.widget_view(wid) or {}
        except Exception:  # noqa: BLE001
            view = {}
        if isinstance(view, dict) and "empty" in view:
            repl = {"widget": wid, "field": "empty", "is": "false"}
            if repl not in kept:
                kept.append(repl)
    if not kept:
        return None
    return {mode or "all": kept}


def _infer_messages(goal: str) -> list[dict]:
    cat = catalogue()
    listing = "\n".join(f"  · {t} ({wa})" for t, wa in list(cat.items())[:40]) or "  (none)"
    readable = _readable()
    cards = "\n".join(
        f"  · {w}: " + ", ".join(([f"collections {', '.join(d['collections'])}"] if d["collections"] else [])
                                + (["field `empty` (\"is\": \"false\" = something landed on the card)"] if d["empty"] else []))
        for w, d in list(readable.items())[:30]) or "  (none)"
    return [
        {"role": "system",
         "content": (
             "You write the END STATE of an errand a personal assistant was given, as a condition its engine can "
             "CHECK against its own widgets when the errand ends. Return ONLY a JSON object in this grammar, or "
             "exactly - when the errand ends in nothing a widget can attest (a report, an answer in words).\n"
             "Grammar: {\"all\": [clause, ...]} — every clause must hold.\n"
             "Clauses:\n"
             "  {\"widget\": W, \"collection\": C, \"where\": {\"title~\": \"text\"}, \"expect\": \"present\"}  a row exists\n"
             "  {\"widget\": W, \"field\": \"path\", \"is\": \"value\"} / \"has\": \"text\" / \"expect\": \"changed\"\n"
             "  {\"desktop\": \"wallpaper\", \"has\": \"text\"} / \"expect\": \"changed\"\n"
             "  {\"canvas\": W, \"expect\": \"visible\"}\n"
             "Prefer \"expect\": \"changed\" when the errand only says WHICH by index or by «that one». Never invent "
             "a target that is not listed. A search or a hunt whose findings land on a card ends with that card's "
             "`empty` field false. Targets the widgets attest (target → widget:action):\n" + listing
             + "\nWhat each card declares a clause may read (only these collections and fields):\n" + cards)},
        {"role": "user", "content": (goal or "").strip()[:1200]},
    ]


async def infer(goal: str, *, timeout: float = _INFER_TIMEOUT_S) -> dict | None:
    """The spec of an errand that came without one — one small model call, the errand namer's shape. None when
    the model says there is none, when it wrote something the grammar cannot read, or when it did not answer."""
    if not (goal or "").strip():
        return None
    try:
        import asyncio

        from nucleo import errand_title as _et
        from nucleo.flash.fast_client import FastClient
        spec = _et._spec_for_naming()
        if spec is None:
            return None
        out = await asyncio.wait_for(
            FastClient().complete(_infer_messages(goal), spec=spec, max_tokens=300, no_thinking=True), timeout=timeout)
    except Exception as e:  # noqa: BLE001
        logger.info(f"spec: sin condición inferida ({str(e)[:80]})")
        return None
    return parse(out)


def parse(text) -> dict | None:
    """A model's answer → a `done_when` the grammar reads, or None."""
    raw = str(text or "").strip()
    if not raw or raw == "-":
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    from nucleo import verify as _verify
    if not isinstance(got, dict) or not _verify._clauses(got)[1]:
        return None
    got = _sanitize(got)
    if got is None:
        return None
    try:
        _snapshot(got)
    except Exception:  # noqa: BLE001
        pass
    return got
