"""nucleo/canvas_arbiter.py — ONE decision tree for every canvas mutation (V2-653, phase F0: SHADOW).

Thirty days of widget incidents were each fixed with a correct, measured guard — and the SUM is a
blacklist spread over ~10 modules and 2 channels that the next session walks around, and whose pieces
now collide with each other (the silent tail of session 7f77e2cc was two correct guards interacting).
This module inverts the posture: every canvas mutation is judged by ONE pyramidal decision tree with at
most a handful of options per level, and needs TWO credentials — PROVENANCE (who ordered it, a closed
set) and a LICENSE (what gives it the right: the operator's words in THIS turn, a task that owns the
surface, or the operator's own hands). The existing guard modules are reused as this tree's LEAVES
(`canvas_license`, `close_guards`, the manifest-driven `producers`/`actions`/`runtime` resolvers), so a
verdict here agrees with the doctrine each of them already proved live — the tree only puts them in ONE
place, in ONE order, with ONE observable answer to «why did/didn't this happen».

The license leaves are DERIVED FROM THE MANIFEST wherever they touch a specific widget (aliases via
`runtime.identify`, production via `producers.starts_production`, lenses via `actions.is_view`): a
widget forked or written by a user inherits the rails with zero code of ours.

## F0 — SHADOW, deliberately

`decide()` is pure and enforced nowhere yet. `shadow_tap()` hangs off the observer stream — the funnel
every canvas command already travels through as a `widget` event with `src` (V2-039), and every operator
turn as a `transcript` — assembles an approximate context, and emits a VERDICT (`kind="arbiter"`) for
every mutation: what the armed tree WOULD have done, with the rule and the evidence. The gate from
shadow to enforcement is the operator's own condition: zero false vetoes over his real sessions.
Kill-switch: `ZAELAR_ARBITER_SHADOW=0`.

Fail-open by construction in F0: any internal error produces NO verdict and never touches the event
that carried the mutation.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

# ── the verdict ──────────────────────────────────────────────────────────────────────────────────────────

ALLOW = "allow"
VETO = "veto"


@dataclass
class Verdict:
    allow: bool
    rule: str                       # ONE short kebab-case name — the tree branch that decided
    evidence: dict = field(default_factory=dict)


def _v(allow: bool, rule: str, **evidence) -> Verdict:
    return Verdict(allow=allow, rule=rule, evidence=evidence)


# ── the tree ─────────────────────────────────────────────────────────────────────────────────────────────

#: Provenance classes (closed set — anything unrecognized is judged like the model, the strictest branch).
_SRC_OPERATOR = ("user",)
_SRC_SYSTEM = ("system",)
_SRC_DETERMINISTIC = ("actionmap", "interrupt")


def decide(op: str, wid: str, src: str, *, action: str = "", payload: dict | None = None,
           text: str = "", turn_credit: bool = True, model_acted: bool = False,
           open_ids=(), recent_ids=(), last_reply: str = "", verdict: dict | None = None) -> Verdict:
    """The whole pyramid, pure. `op` ∈ show|close|data|screen. `src` is the V2-039 provenance string
    (`user`, `system`, `worker:<tid>`, `wall:<tid>`, `actionmap`, `flash`, `backstop`). `text` is the operator's
    turn; `turn_credit` is False only for a turn judged ambient. `verdict` is the turn's paid brief,
    `{key: (choice, confidence)}` for `canvas`, `screen_action`, `catalog_widget`. Never raises: an unreadable
    input is judged on the strictest branch rather than crashing a caller that sits near the hot path."""
    try:
        return _decide(op, wid, src, action=action, payload=payload or {}, text=text,
                       turn_credit=turn_credit, model_acted=model_acted,
                       open_ids=open_ids, recent_ids=recent_ids, last_reply=last_reply, verdict=verdict or {})
    except Exception as e:  # noqa: BLE001
        return _v(False, "arbiter-error", error=str(e)[:120])


#: The closed op vocabulary. Anything else is vetoed BEFORE the provenance ladder: an op the tree does
#: not know must not inherit anybody's pass (found by the garbage conformance case — `op=None` with an
#: unattributed src walked out as `lifecycle`).
_OPS = ("show", "close", "data", "screen")


def _decide(op, wid, src, *, action, payload, text, turn_credit, model_acted,
            open_ids, recent_ids, last_reply="", verdict=None) -> Verdict:
    op = (op or "").strip().lower()
    wid = (wid or "").strip().lower()
    base_src = (src or "system").split(":", 1)[0].strip().lower()
    if op not in _OPS:
        return _v(False, "unknown-op", op=op)

    # ── level 1 · WHO ────────────────────────────────────────────────────────────────────────────────
    if base_src in _SRC_OPERATOR:
        return _v(True, "operator-hands")
    from voice import canvas_src
    if src == canvas_src.CLIENT:
        return _v(True, "report")           # the canvas telling what it already did: nothing to obey or veto
    if base_src == "client":
        # V2-807 T-15: a change the canvas reports from its OWN code. A restore or a reset is lifecycle; the
        # echo of an engine command was judged at the command; any other client code (a fast path, an
        # unnamed cause) has no hand behind it and walks the license branch like the model.
        cause = canvas_src.cause_of(src)
        if cause in canvas_src.LIFECYCLE:
            return _v(True, "lifecycle", cause=cause)
        if cause == canvas_src.BY_ENGINE:
            return _v(True, "engine-echo")
    if base_src in _SRC_SYSTEM:
        return _v(True, "lifecycle")
    if base_src == "wall":
        return _v(True, "task-owned", tid=(src.split(":", 1) + [""])[1], via="wall")   # a task's own card
    if base_src.startswith("worker"):
        # F0: a worker mutation is admitted with its task on record; F1 adds the ownership check
        # (does this corr_id own the surface it touches) against the dispatcher's registry.
        return _v(True, "task-owned", tid=(src.split(":", 1) + [""])[1])
    if base_src in _SRC_DETERMINISTIC:
        # The seeded phrase IS the license (a human wrote the grammar, V2-539/V2-567); the executor's
        # own liveness veto (a close over live production declines to the model) stays where it is.
        return _v(True, "seeded-grammar")

    # ── level 2 · model / backstop share the license branch; a backstop must also not duplicate ─────
    if base_src == "backstop" and model_acted:
        return _v(False, "backstop-duplicate")
    if not turn_credit:
        return _v(False, "ambient-turn")

    # ── level 3 · the turn's PAID verdict licenses first (CRIT-K1); the word leaves only where it is silent ──
    licensed = _verdict_licence(op, wid, action, verdict or {})
    if licensed is not None:
        return licensed

    # ── level 4 · WHAT (closed op classes; the leaves are the proven license modules) ────────────────
    from nucleo.flash import canvas_license as _lic

    if op == "close":
        return (_v(True, "close-grammar") if _lic.close_license(text)
                else _v(False, "close-drag"))

    if op == "screen":
        direction = _lic.fullscreen_license(text)
        return (_v(True, "screen-grammar", direction=direction) if direction
                else _v(False, "screen-drag"))

    if op == "show":
        # A close order licenses no show (V2-567) — checked FIRST, because a show against a close
        # order is the model contradicting the operator, whatever else the words contain.
        if _lic.close_license(text):
            return _v(False, "show-against-close-order")
        if not _lic.reopen_license(wid, text, open_ids=open_ids, recent_ids=recent_ids,
                                   last_reply=last_reply):
            return _v(False, "reopen-unlicensed")
        if _mentions_widget(wid, text, open_ids, recent_ids):
            return _v(True, "turn-mention")
        if _lic.video_license(text, last_reply):
            return _v(True, "media-or-show-request")
        # A MOUNT is not a drag (V2-721). When a widget's output lives in its own card — the music player's
        # hidden iframe — an action the widget DECLARES as production cannot happen off screen, so the show
        # that follows it is part of the playback, not a second decision about the canvas. Without this the
        # shadow was counting the honest mount as a drag too: of the six `show-drag` verdicts over the music
        # card in twelve real sessions, FIVE were a `pause`/`stop`/`volume_up` putting the card back on his
        # screen (what V2-721 stops emitting) and ONE was the card going up so the play he had just asked
        # for could be heard. Arming the arbiter without this rule would have answered that one with silence.
        if _mounts_production(wid, action):
            return _v(True, "producer-mount")
        # CONTENT LANDING is a mount too (`show-real-photo-of-a-new-car__us`, 2026-10-11): the picture search
        # fills the viewer and its `show` was filed as a drag three times in one round, because the emit carried
        # no action. The declaration is the action's own `done_when` (`effects._fills_the_card`): the card goes
        # from empty to holding what he asked to SEE. A lens (`select`) over an open card still earns nothing.
        if _lands_content(wid, action):
            return _v(True, "content-mount")
        return _v(False, "show-drag")

    if op == "data":
        if _is_view_action(wid, action):
            return _v(True, "view-op")                 # a lens never writes anything to undo (V2-545)
        if _payload_in_turn(payload, text):
            return _v(True, "payload-in-turn")         # the turn names what it writes (V2-038's own escape)
        if _lic.replay_license(wid, action, text):
            return _v(True, "replay-order")            # declared production + conjugated request (V2-650)
        if _lic.video_license(text, last_reply):
            return _v(True, "conjugated-request")      # an order in this turn, target resolved by the tool
        return _v(False, "data-drag")

    return _v(False, "unknown-op", op=op)


#: A brief answer at or above this confidence licenses; a contrary one at or above `_SURE` vetoes.
_LICENCE_MIN = 0.5
_SURE = 0.85


def _verdict_licence(op: str, wid: str, action: str, verdict: dict) -> Verdict | None:
    """The brief's answer about THIS act, or None when it said nothing usable (the word leaves then decide).
    `screen_action` naming this card's action wins over `canvas`; `catalog_widget` naming the card licenses its
    show even under a sure `canvas=neither` — «neither» says the turn has no canvas verb, the catalogue says
    which card answers it."""
    base = wid.split("::", 1)[0]
    canvas, ccf = verdict.get("canvas") or ("", 0.0)
    target, tcf = verdict.get("screen_action") or ("", 0.0)
    card, kcf = verdict.get("catalog_widget") or ("", 0.0)
    if op == "data" and target == f"{base}:{action}" and tcf >= _LICENCE_MIN:
        return _v(True, "verdict-action", confidence=round(tcf, 2))
    if op == "close" and canvas == "close" and ccf >= _LICENCE_MIN:
        return _v(True, "verdict-close", confidence=round(ccf, 2))
    if op == "show":
        if canvas == "close" and ccf >= _LICENCE_MIN:
            return _v(False, "verdict-close-not-show", confidence=round(ccf, 2))
        if canvas == "show" and ccf >= _LICENCE_MIN:
            return _v(True, "verdict-show", confidence=round(ccf, 2))
        if card == base and kcf >= _LICENCE_MIN:
            return _v(True, "verdict-catalog", confidence=round(kcf, 2))
    if op in ("show", "close") and canvas and canvas != op and ccf >= _SURE:
        return _v(False, "verdict-against", canvas=canvas, confidence=round(ccf, 2))
    return None


# ── leaves that read the MANIFEST (fork-safe: a user widget brings its own vocabulary) ──────────────────

def _mentions_widget(wid: str, text: str, open_ids, recent_ids) -> bool:
    """The operator's own words resolve to this widget through the certainty resolver every show
    already uses (V2-082/V2-566: full aliases, never fragments)."""
    if not (wid and text):
        return False
    try:
        from widgets import runtime
        m = runtime.identify(text, open_ids=list(open_ids or []), recent_ids=list(recent_ids or [])) or {}
        return (m.get("match") or "").split("::", 1)[0] == wid.split("::", 1)[0]
    except Exception:  # noqa: BLE001
        return False


def _mounts_production(wid: str, action: str) -> bool:
    """Does the widget DECLARE that this action makes it produce? Same `runtime.produce` the replay license
    reads (V2-650) and `canvas_visibility` gates the emit with — one declaration, never two opinions."""
    if not (wid and action):
        return False
    try:
        from widgets import producers
        return bool(producers.starts_production(wid.split("::", 1)[0], action))
    except Exception:  # noqa: BLE001
        return False


def _lands_content(wid: str, action: str) -> bool:
    """Does the action DECLARE that the card ends up holding content it did not have (`effects.PRESENT_MOUNT`
    derived from its `done_when`)? Production is read by `_mounts_production`; this is the other mount."""
    if not (wid and action):
        return False
    try:
        from widgets import effects as _fx, producers
        base = wid.split("::", 1)[0]
        return _fx.carries(base, action, _fx.PRESENT_MOUNT) and not producers.starts_production(base, action)
    except Exception:  # noqa: BLE001
        return False


def _is_view_action(wid: str, action: str) -> bool:
    if not (wid and action):
        return False
    try:
        from widgets import actions as _wactions, runtime
        spec = ((runtime.get(wid.split("::", 1)[0]) or {}).get("actions") or {}).get(action)
        return _wactions.is_view(spec, action)
    except Exception:  # noqa: BLE001
        return False


def _payload_in_turn(payload: dict, text: str) -> bool:
    """Does the turn MENTION what the payload writes? (the V2-038 dedupe's own overlap test, applied as
    a positive license here)."""
    try:
        words = set()
        for v in (payload or {}).values():
            words.update(str(v).lower().split())
        turn = set((text or "").lower().split())
        return bool(words & turn)
    except Exception:  # noqa: BLE001
        return False


# ── F0 shadow: assemble context from the observer stream, judge, emit the verdict ──────────────────────

def _enabled() -> bool:
    return os.getenv("ZAELAR_ARBITER_SHADOW", "1") != "0"


_TURN_TTL_S = 25.0
_last_turn: dict = {"text": "", "ts": 0.0, "credit": True, "reply": ""}
_in_tap = False                     # re-entrancy guard: our own verdict emit must not re-enter the tap
#: trace → {key: (choice, confidence)}: the brief's answers, read off its `jev read <key>` events.
_reads: dict[str, dict] = {}
_READS_KEPT = 64


def _note_read(ex: dict) -> None:
    from nucleo.flash import turn_brief as _tb
    trace, key = str(ex.get("trace") or ""), str(ex.get("question") or "")
    if not trace or key not in (_tb.CANVAS_KEY, _tb.TARGET_KEY, _tb.CATALOG_KEY):
        return
    _reads.setdefault(trace, {})[key] = (str(ex.get("choice") or ""), float(ex.get("confidence") or 0))
    while len(_reads) > _READS_KEPT:
        _reads.pop(next(iter(_reads)))

#: op labels as they travel on the observer's `widget` events today.
_SHOW_LABELS = ("show",)
_CLOSE_LABELS = ("close",)


def _turn_text() -> tuple[str, bool]:
    if time.time() - _last_turn["ts"] <= _TURN_TTL_S:
        return _last_turn["text"], bool(_last_turn["credit"])
    return "", True


def shadow_tap(kind: str, label: str, text: str, role: str, extra: dict | None) -> None:
    """Called by `voice/observer.emit` for every recorded event (F0's ONLY wiring). Assembles the turn
    context from `transcript`/`ambient` events and judges every `widget` command, emitting a verdict as
    its own `arbiter` event. Approximate on purpose — shadow measures agreement and coverage; the armed
    phases (F1+) pass explicit context at the doors, where the turn text already lives. NEVER raises and
    never mutates the event it observes."""
    global _in_tap
    if _in_tap or not _enabled():
        return
    try:
        _in_tap = True
        ex = extra or {}
        if kind == "transcript" and role == "user":
            _last_turn.update(text=str(text or ""), ts=time.time(), credit=True)
            return
        if kind == "transcript" and role == "assistant":
            # V2-723: a bare «yes» licenses media only as the answer to something WE asked, so the tap
            # has to remember our side of the conversation too — one line, same shape as his.
            _last_turn["reply"] = str(text or "")
            return
        if kind == "brain" and str(label or "").startswith("jev read "):
            _note_read(ex)
            return
        if kind == "ambient":
            # the gate's own verdict for the turn: 🙉 removes credit, 👂 restores it
            if "🙉" in (label or ""):
                _last_turn["credit"] = False
            elif "dirigido" in (label or "") or "👂" in (label or ""):
                _last_turn["credit"] = True
            return
        if kind != "widget":
            return
        op, action = "", ""
        if label in _SHOW_LABELS:
            op, action = "show", str(ex.get("action") or "")   # V2-721: a mount names the action that produces
        elif label in _CLOSE_LABELS:
            op = "close"
        elif isinstance(label, str) and label.startswith("data:"):
            op, action = "data", label.split(":", 1)[1]
        elif label == "action":
            # The ORDER event both data funnels emit (`widget_action` for the UI, `brain_action` for
            # every non-UI door) — measured live 2026-09-10: a real click produced `action`, never
            # `data:*`, and the first shadow judged nothing. A flash-sourced `action` is skipped here
            # because the SAME order was already judged richer (with its payload) at the `data:*` log.
            op, action = "data", str(ex.get("action") or "")
        if not op:
            return
        wid = str(ex.get("id") or "").strip().lower()
        src = str(ex.get("src") or "") or _prov_src(wid)
        if label == "action" and src.split(":", 1)[0] == "flash":
            return
        if src == "client:engine":      # `voice.canvas_src.of(BY_ENGINE)`
            return          # the canvas echoing an engine command: that command was judged when it was issued
        # data:* events carry the ORIGINATING phrase in `text` AND (since V2-653) their payload in
        # `extra` (V2-039's action log); show/close do not, so those borrow the assembled last turn.
        turn, credit = (str(text or ""), True) if op == "data" and text else _turn_text()
        payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
        brief = dict(_reads.get(str(ex.get("trace") or ""), {}))
        verdict = decide(op, wid, src, action=action, payload=payload, text=turn, turn_credit=credit,
                         last_reply=str(_last_turn.get("reply") or ""), verdict=brief)
        _emit_verdict(op, wid, src, action, verdict, shadow=True, brief=brief)
    except Exception:  # noqa: BLE001
        pass
    finally:
        _in_tap = False


def _prov_src(wid: str) -> str:
    try:
        from widgets import provenance
        return provenance.who(wid)
    except Exception:  # noqa: BLE001
        return "system"


def _emit_verdict(op: str, wid: str, src: str, action: str, verdict: Verdict, *, shadow: bool,
                  brief: dict | None = None) -> None:
    try:
        from voice.observer import emit
        face = ("✅ permitiría" if verdict.allow else "⛔ vetaría") if shadow else \
               ("✅ permitida" if verdict.allow else "⛔ vetada")
        emit("arbiter", f"{face} · {verdict.rule}",
             text=f"{op} {wid}" + (f":{action}" if action else ""),
             role="system",
             extra={"op": op, "id": wid, "action": action, "src": src, "allow": verdict.allow,
                    "rule": verdict.rule, "shadow": shadow, "source": src,
                    "verdict": {k: {"choice": c, "confidence": round(f, 2)} for k, (c, f) in (brief or {}).items()},
                    **({"ev": verdict.evidence} if verdict.evidence else {})})
    except Exception:  # noqa: BLE001
        pass
