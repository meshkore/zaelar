"""nucleo/acts/canvas_arbiter.py — ONE decision tree for every canvas mutation (V2-653; armed by refactor2710-04).

Every canvas mutation is judged by ONE pyramidal tree and needs TWO credentials: PROVENANCE (who ordered it, a
closed set) and a LICENSE — the turn's paid verdict first (CRIT-K1), then the declared leaves (the manifest's
production, lenses and aliases), the operator's words only where the verdict is silent. A widget forked or
written by a user inherits the rails with zero code of ours.

ARMED at the door: `nucleo.acts.canvas.apply` judges every show and close before the canvas hears it (promoted
once the replay over the operator's archive gave zero false vetoes, `tests/arbiter_replay.py`). `shadow_tap()`
keeps listening to the observer stream — it assembles the turn the door reads (his words, their credit, the
brief's `jev read` answers by trace) and still judges, unenforced, what does not cross the door (data-op logs).
An internal error is the verdict `arbiter-error`, never a crash at a caller; the door lets that act through.
"""
from __future__ import annotations

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
           open_ids=(), recent_ids=(), last_reply: str = "", verdict: dict | None = None,
           card_closed: bool = False, answered: bool = False) -> Verdict:
    """The whole pyramid, pure. `op` ∈ show|close|data|screen. `src` is the V2-039 provenance string
    (`user`, `system`, `worker:<tid>`, `wall:<tid>`, `actionmap`, `flash`, `backstop`). `text` is the operator's
    turn; `turn_credit` is False only for a turn judged ambient. `verdict` is the turn's paid brief,
    `{key: (choice, confidence)}` for `canvas`, `screen_action`, `catalog_widget`. Never raises: an unreadable
    input is judged on the strictest branch rather than crashing a caller that sits near the hot path."""
    try:
        v = _decide(op, wid, src, action=action, payload=payload or {}, text=text,
                    turn_credit=turn_credit, model_acted=model_acted,
                    open_ids=open_ids, recent_ids=recent_ids, last_reply=last_reply, verdict=verdict or {},
                    card_closed=card_closed, answered=answered)
        return v if isinstance(v, Verdict) else _v(False, "arbiter-error", error="a branch gave no verdict")
    except Exception as e:  # noqa: BLE001
        return _v(False, "arbiter-error", error=str(e)[:120])


#: The closed op vocabulary: anything else is vetoed before the provenance ladder, never inheriting a pass.
_OPS = ("show", "close", "data", "screen")


def _decide(op, wid, src, *, action, payload, text, turn_credit, model_acted,
            open_ids, recent_ids, last_reply="", verdict=None, card_closed=False, answered=False) -> Verdict:
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
        # A restore or reset is lifecycle, an engine echo was judged at its command; other client code walks
        # the licence branch like the model (V2-807 T-15).
        cause = canvas_src.cause_of(src)
        if cause in canvas_src.LIFECYCLE:
            return _v(True, "lifecycle", cause=cause)
        if cause == canvas_src.BY_ENGINE:
            return _v(True, "engine-echo")
    if base_src in _SRC_SYSTEM:
        return _v(True, "lifecycle")
    if base_src in ("wall", "recall", "sheet"):
        # a task's own card: its wall raising it, the errand this turn reopened, the sheet a tool just filled
        return _v(True, "task-owned", tid=(src.split(":", 1) + [""])[1], via=base_src)
    if base_src.startswith("worker"):
        return _v(True, "task-owned", tid=(src.split(":", 1) + [""])[1])
    if base_src in _SRC_DETERMINISTIC:
        return _v(True, "seeded-grammar")       # the seeded phrase IS the licence (V2-539/V2-567)

    # ── level 2 · model / backstop share the license branch; a backstop must also not duplicate ─────
    if base_src == "backstop" and model_acted:
        return _v(False, "backstop-duplicate")
    if not turn_credit:
        return _v(False, "ambient-turn")

    # ── level 3 · the turn's PAID verdict licenses first (CRIT-K1); the word leaves only where it is silent ──
    if answered and op in ("show", "close"):
        return _v(True, "verdict-answer")       # his answer to the question WE asked about which card (`answers`)
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
        if _lic.close_license(text):
            return _v(False, "show-against-close-order")
        if not _lic.reopen_license(wid, text, open_ids=open_ids, recent_ids=recent_ids,
                                   last_reply=last_reply):
            return _v(False, "reopen-unlicensed")
        if _mentions_widget(wid, text, open_ids, recent_ids):
            return _v(True, "turn-mention")
        if _lic.video_license(text, last_reply):
            return _v(True, "media-or-show-request")
        # A MOUNT is not a drag (V2-721): output that lives in its card (a declared production) needs the card.
        if _mounts_production(wid, action):
            return _v(True, "producer-mount")
        if card_closed and _reads_the_card(wid, action):
            return _v(True, "lens-mount")              # a declared lens over a CLOSED card brings the card
        # Content landing mounts too: the action's `done_when` fills an empty card; a lens over an open one does not.
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
    # A show that carries one of the card's own actions mounts the card for that act — «neither» is about canvas
    # verbs, and this is not one; only a bare show or close stands against a sure contrary verdict.
    if op in ("show", "close") and not action and canvas and canvas != op and ccf >= _SURE:
        return _v(False, "verdict-against", canvas=canvas, confidence=round(ccf, 2))
    return None


# ── leaves that read the MANIFEST (fork-safe: a user widget brings its own vocabulary) ──────────────────

def _mentions_widget(wid: str, text: str, open_ids, recent_ids) -> bool:
    """His words name this widget through the certainty resolver (V2-082/V2-566: full aliases, never fragments)."""
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


def _reads_the_card(wid: str, action: str) -> bool:
    """Does the action DECLARE it reads the card (`effects.DATA_READ`)? A lens nobody can see is a silent nothing."""
    if not (wid and action):
        return False
    try:
        from widgets import effects as _fx
        return _fx.carries(wid.split("::", 1)[0], action, _fx.DATA_READ)
    except Exception as e:  # noqa: BLE001
        _note(f"declaration of {wid}:{action} unreadable: {e!r}")
        return False


def _note(what: str) -> None:
    from loguru import logger
    logger.debug(f"canvas_arbiter: {what}")


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
