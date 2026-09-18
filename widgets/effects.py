"""widgets/effects.py — WHAT AN ACTION ACTUALLY DOES, as a declared set (V2-723).

## Why this exists (external audit of the widget layer, 2026-09-18)

> «Authorizing an action is not the same as authorizing all its effects. […] An action cannot manufacture
> permission for its own side effects.»

Measured the day before, and it is the whole recurring failure class: `musica:pause` is a control action the
operator asked for, and executing it re-opened a card he had closed — because the result said
`surface: "widget"` and the voice lane read that as «put it on screen». One authorization (run `pause`) was
silently spending a second one (present the card).

The declarations needed to tell those apart ALREADY EXIST in this tree; what did not exist is a place where
they are one vocabulary instead of four unrelated flags read by four different callers:

    widgets/actions.py     classify()    → fast / confirm / escalate   «how much friction does running cost»
    widgets/actions.py     is_view()     → display-only                «does it write anything to undo»
    widgets/producers.py   runtime.produce / suspend / output          «does it make the widget produce»
    manifest              consent_class  → the class the consent rule keys on

So this module DERIVES the effect set from what each widget already declares, and a manifest may add
`"effects": [...]` to an action to declare one that cannot be derived. It reads; it never decides. The
deciding is each door's job, and the point of a shared vocabulary is that the doors stop inventing
overlapping ones.

## The vocabulary

    data.read        a lens: changes what the card DISPLAYS, writes nothing
    data.write       creates / patches / deletes rows the operator would have to undo
    present.mount    the action's own output cannot happen off screen (the player's hidden iframe)
    output.start     makes the widget produce on its channel (audio, video)
    output.stop      suspends what it is producing
    external.send    reaches the world outside this machine

`external.send` is the one that is NOT derivable today: a `consent_class` says an action is sensitive, not
that it leaves the machine, and guessing from names is exactly what this repo's doctrine forbids. It is
reported only when a manifest declares it. That gap is written down rather than papered over — a derivation
that quietly guesses would be worse than an honest hole.
"""
from __future__ import annotations

DATA_READ = "data.read"
DATA_WRITE = "data.write"
PRESENT_MOUNT = "present.mount"
OUTPUT_START = "output.start"
OUTPUT_STOP = "output.stop"
EXTERNAL_SEND = "external.send"

#: Everything a manifest may name in an action's `effects`. A name outside this set is ignored: a typo must
#: never become an effect nobody implements, and it must never silently authorize one either.
KNOWN = frozenset({DATA_READ, DATA_WRITE, PRESENT_MOUNT, OUTPUT_START, OUTPUT_STOP, EXTERNAL_SEND})


def _manifest(wid: str) -> dict:
    try:
        from . import runtime
        return runtime.get(str(wid or "").split("::", 1)[0].strip().lower()) or {}
    except Exception:  # noqa: BLE001
        return {}


def declared(wid: str, action: str) -> frozenset:
    """Only what the action's manifest spec names in `effects` — the refinement half, nothing derived."""
    spec = ((_manifest(wid).get("actions") or {}).get(str(action or "").strip()))
    raw = (spec or {}).get("effects") if isinstance(spec, dict) else None
    if not isinstance(raw, (list, tuple, set)):
        return frozenset()
    return frozenset(str(e).strip() for e in raw if str(e).strip() in KNOWN)


def of(wid: str, action: str) -> frozenset:
    """The effects this action carries: derived from the widget's own declarations, plus whatever its
    manifest declares outright. An action the widget does not declare at all carries NOTHING — which is
    what makes «no declared effect» mean «no authorization to spend», instead of «unknown, so allow»."""
    w, a = str(wid or "").split("::", 1)[0].strip().lower(), str(action or "").strip()
    if not w or not a:
        return frozenset()
    man = _manifest(w)
    spec = (man.get("actions") or {}).get(a)
    out = set(declared(w, a))
    if isinstance(spec, dict):
        try:
            from . import actions as _wa
            out.add(DATA_READ if _wa.is_view(spec, a) else DATA_WRITE)
        except Exception:  # noqa: BLE001
            pass
    try:
        from . import producers
        if producers.starts_production(w, a):
            out.add(OUTPUT_START)
            # The MOUNT rides the production, and only when the output lives in the card. `runtime.output`
            # names the channel; a widget whose sound comes out of a remote device (Spotify) needs no
            # surface, and that is why this is read per widget instead of assumed for every producer.
            if str((man.get("runtime") or {}).get("output") or "").strip():
                out.add(PRESENT_MOUNT)
        if str((man.get("runtime") or {}).get("suspend") or "").strip() == a:
            out.add(OUTPUT_STOP)
    except Exception:  # noqa: BLE001
        pass
    return frozenset(out)


def carries(wid: str, action: str, effect: str) -> bool:
    """Does this action carry that effect? The predicate the doors ask, so nobody re-derives the set."""
    return str(effect or "") in of(wid, action)
