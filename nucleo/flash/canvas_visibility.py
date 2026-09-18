"""nucleo/flash/canvas_visibility.py — what may OPEN a card, and what may not (V2-721).

## The measured incident

Session `c553a1e0`, 2026-09-17. Music was playing; the operator paused it, opened other things, closed
everything, and four minutes later — talking about headphones, not about music — the music card came back on
screen twice and the player woke up. His words afterwards:

> «ha habido como un baile de abrir y cerrar widgets sin mi permiso […] los widgets no dejan de ser un
> catálogo y deben tener un flag de si están abiertos o cerrados. A menos que haya una acción concreta que
> interprete que uno de esos widgets tiene que cambiar el flag de visibilidad […] no deberíamos en absoluto
> tener ningún problema con eso.»

The flag he describes already exists and is authoritative: the canvas reports what is open on every change
(`/api/canvas/state` → `memory.state()["open_widgets"]`). What was missing is this: **who is allowed to move
it**. The voice lane opened the music card on EVERY successful music action, because the connector's result
says `surface: "widget"` — and `pause`, `volume_up`, `seek` and `queue` all say it too. That field answers
«where does the sound come from» (a hidden iframe in the card, versus a Spotify device), which is a fact
about AUDIO and not an instruction about the screen. Read as an instruction, pausing re-opened a card the
operator had closed, and «turn the volume down» put it back in front of him.

## The rule

An action may open a card only if the widget DECLARES that this action makes it produce — `runtime.produce`
in its manifest, the same declaration `producers.py` has owned since V2-092 and the replay license reads
since V2-650. `musica` declares `["play", "resume", "next", "previous", "play_playlist", "ended"]`: those
need the surface mounted, because that is where the audio is. `pause`, `volume_up`, `set_volume`, `seek`,
`queue` are not there, and they now change nothing about what is on screen.

And the second half, which is what makes it a FLAG and not a habit: if the card is already open there is
nothing to open. A `show` on an open card is not free — it raises and refocuses it, which is the other half
of the dance he described, with the widget jumping in front of whatever he was reading.

Deliberately NOT here: deciding whether the action itself should have happened. A `resume` nobody asked for
is a misrouted action, and its home is the canvas arbiter's rules, which already judge exactly that. This
module answers one question — «does what just happened move the visibility flag?» — and for everything it
cannot read it answers no, which leaves the card where the operator put it.
"""
from __future__ import annotations


def open_ids() -> frozenset:
    """The ids the canvas reports as OPEN right now. The frontend is authoritative and re-reports on every
    change; an unreadable state answers «nothing known open», which only ever costs an extra `show`."""
    try:
        from memory import api as _memapi
        st = _memapi.state() or {}
        return frozenset(str(w).split("::", 1)[0].strip().lower()
                         for w in (st.get("open_widgets") or []) if str(w).strip())
    except Exception:  # noqa: BLE001
        return frozenset()


def is_open(widget_id: str, *, known=None) -> bool:
    """Instance ids collapse to their base here as they do in the canvas report: `navegador::t2` IS the
    browser being open, and a second card of the same widget is not a reason to raise a third."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    ids = open_ids() if known is None else frozenset(str(w).split("::", 1)[0].strip().lower() for w in known)
    return bool(wid) and wid in ids


#: WHY a card is being put on screen. A presentation effect is spent by some authorization, and the emitter
#: is the only one who knows which — so it says so, in a closed vocabulary, and the door checks what it can
#: check. This is the audit's «explicit, scoped effects as the contract» at its smallest useful size: not a
#: permission system, but the end of anonymous side effects, and the reason travels into the trace.
REASONS = {
    # the operator's own hands on the canvas — the frontend reports these, they are never judged
    "operator-hands",
    # this turn's words asked for this card; the caller has already run the license that says so
    "turn-order",
    # the action's own output CANNOT happen off screen (the player's hidden iframe). Checked below against
    # the widget's declaration: a caller claiming this over an action that declares no mount is refused.
    "producer-mount",
    # a worker or errand delivering what its task was opened for
    "task-owned",
    # one widget handing over to another's surface (a torrent handing its file to the library)
    "widget-handoff",
    # boot, restore, and the rest of the lifecycle
    "lifecycle",
}


def present(widget_id: str, *, reason: str, action: str = "", src: str = "flash",
            known=None, emit=None) -> bool:
    """THE ONE DOOR a card goes through to appear (V2-723). True when the show was emitted.

    Three mechanical refusals, and each one is a measured incident rather than a policy:

      · **no reason** — an anonymous show is an effect nobody authorized. Before this door there were
        thirteen call sites emitting `show` directly and the canvas could not tell them apart.
      · **a claim the declaration does not back** — «producer-mount» is only true if the widget says the
        action makes it produce (V2-721). A caller that says it over `pause` is refused, not believed.
      · **already open** — a `show` on an open card raises and refocuses it, jumping in front of whatever
        the operator was reading. Nothing to open means nothing to do.

    A refusal is EMITTED, not swallowed: «suppressed effects» are the half of a trace that explains why
    the screen did not change, and without them this door would be a new silence."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    why = str(reason or "").strip()

    def _emit(kind, label, extra):
        fn = emit
        if fn is None:
            try:
                from voice.observer import emit as fn  # type: ignore[no-redef]
            except Exception:  # noqa: BLE001
                return
        try:
            fn(kind, label, extra=extra)
        except Exception:  # noqa: BLE001
            pass

    def _suppress(detail: str) -> bool:
        _emit("widget", "🚫 presentación suprimida",
              {"id": wid, "src": src, "action": action, "reason": why, "detail": detail, "cat": "widget"})
        return False

    if not wid:
        return False
    if why not in REASONS:
        return _suppress("sin motivo declarado")
    if why == "producer-mount":
        try:
            from widgets import effects as _fx
            if not _fx.carries(wid, action, _fx.PRESENT_MOUNT):
                return _suppress("la acción no declara que su salida necesite la tarjeta")
        except Exception:  # noqa: BLE001
            return _suppress("no se pudo leer la declaración del widget")
    if is_open(wid, known=known):
        return _suppress("ya está abierta")
    _emit("widget", "show", {"id": wid, "src": src, "action": action, "reason": why})
    return True


def mount_needed(extra: dict | None, action: str, *, known=None) -> bool:
    """Does this result need its widget's card ON SCREEN, and is it not there already?

    `extra` is the connector's result block: `surface` says where the output lives and `widget` names the
    card. Both are read as facts about the OUTPUT — the decision below is the manifest's."""
    ex = extra if isinstance(extra, dict) else {}
    wid = str(ex.get("widget") or "").strip().lower()
    if not wid or str(ex.get("surface") or "").strip() != "widget":
        return False
    if is_open(wid, known=known):
        return False
    try:
        from widgets import producers
        return bool(producers.starts_production(wid, str(action or "").strip()))
    except Exception:  # noqa: BLE001 — an unreadable declaration never moves the flag
        return False
