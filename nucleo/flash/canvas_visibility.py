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


def card_is_open(card_id: str, *, known=None):
    """Is THIS card — instance included — open right now? True / False, or None when the canvas has not
    reported since the engine started (unknown is not «closed»).

    `open_widgets` in the memory state is normalized to base ids (`results::c29838-ls1` → `results`), right
    for «is the browser up», wrong for «is THIS errand's sheet up»: with the monitors sheet closed and another
    results card open, the base answers yes (demo pass 30, S1). The raw instances are `open_instances()`."""
    cid = str(card_id or "").strip().lower()
    if not cid:
        return None
    if known is None:
        try:
            from server.voice_api import open_instances
            known = open_instances()
        except Exception:  # noqa: BLE001
            known = []
    ids = {str(w).strip().lower() for w in (known or []) if str(w).strip()}
    if not ids:
        return None
    return cid in ids


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
    # The CARD is what goes on screen: an instance keeps its suffix. Only the declaration checks read the base.
    # V2-776 (2026-09-27): «Show me the monitors» resolved to `results::94b220-ls1` and this door emitted bare
    # `results` — the empty base — so «Open the best value option» then failed on a box with nothing in it.
    _raw = str(widget_id or "").strip()
    card = (wid + "::" + _raw.split("::", 1)[1].strip()) if "::" in _raw and _raw.split("::", 1)[1].strip() else wid
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

    def _suppress(detail: str, already_open: bool = False) -> bool:
        _emit("widget", "🚫 presentación suprimida",
              {"id": wid, "src": src, "action": action, "reason": why, "detail": detail, "cat": "widget",
               "already_open": already_open})
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
    if is_open(wid, known=known) and not is_minimized(wid):
        return _suppress("ya está abierta", already_open=True)
    _emit("widget", "show", {"id": card, "src": src, "action": action, "reason": why})
    return True


def present_for_call(widget_id: str, action: str, *, brief=None, card: str = "", src: str = "flash",
                     emit=None, known=None) -> bool:
    """A card ACTION this turn is about to run (a repair pass, the catalogue card instead of a worker): does it
    bring its card on screen? True when the show was emitted. The ONE rule every such path asks (V2-815).

    Measured on a phone, 2026-10-26: «busca el programa que está en tu web», «retoma la búsqueda», «check hacker
    news, locate my post» — the brief said `canvas = neither` every time, the arbiter would have vetoed the show,
    and the browser card took the whole screen three times anyway, because the catalogue rung and the promise
    repair presented every call as a `turn-order`. A search is work done BEHIND the screen; its findings reach
    the sheet the errand owns (`task-owned`). The main tool path already worked this way — a write is not
    presented — and only the repair rungs did not.

    The card comes up when one of these is TRUE, never on habit:
      · the action's output only exists on screen (`present.mount`: the player, the picture viewer);
      · the action is a LENS (`data.read`) over a closed card — a view nobody can see is a silent nothing;
      · the turn's verdict says `canvas = show` — he asked to see it.
    Otherwise the call runs and the visibility flag stays where he left it; the refusal is emitted."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    target = str(card or widget_id or "").strip()
    if not wid or not target:
        return False
    from loguru import logger
    try:
        from widgets import effects as _fx
        fx = _fx.of(wid, str(action or "").strip())
        if _fx.PRESENT_MOUNT in fx:
            return present(target, reason="producer-mount", action=action, src=src, known=known, emit=emit)
        if _fx.DATA_READ in fx and not is_open(wid, known=known):
            return present(target, reason="turn-order", action=action, src=src, known=known, emit=emit)
    except Exception as e:  # noqa: BLE001 — an unreadable declaration is not a reason to cover the screen
        logger.debug(f"present_for_call: declaration of {wid}:{action} unreadable — {e!r}")
    try:
        from nucleo.flash import turn_brief as _tb
        verb, info = _tb.read(brief, _tb.CANVAS_KEY, "")
        if info is not None and str(verb or "") == "show":
            return present(target, reason="turn-order", action=action, src=src, known=known, emit=emit)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"present_for_call: canvas verdict unreadable — {e!r}")
    _say(emit, "🚫 presentación suprimida", {
        "id": wid, "src": src, "action": action, "reason": "turn-order", "cat": "widget",
        "detail": "la acción corre detrás de la pantalla: el turno no pidió ver la tarjeta"})
    return False


def a_view_is_not_the_deliverable(widget_id: str, action: str, brief=None, declared: str = "") -> bool:
    """Is this call a VIEW (a lens, `data.read`) standing in for an errand whose deliverable has its OWN box — a
    document to read, pictures to look at — on a turn that did not ask to see the card? Then it is not the errand.

    V2-820, measured: «¿podrías crear un widget que leyera mis mensajes enviados… y fuera componiendo un archivo que
    describiera cómo escribo?» — the brief read `errand_surface = informe` (0.93) and `canvas` unsure; the catalogue
    rung took `mensajeria:mail_folder {folder: sent}` instead of the worker, and because a lens over a closed card
    is presented (`present_for_call`), his mail card opened. Talking ABOUT a card's content, or an errand that will
    read it, is not an order to look at it. Read from the verdict and the action's declaration, never from words.
    A sure `canvas = show` (he asked to see it) or a view of the deliverable's own box is never refused.

    The deliverable is the verdict's surface when it is sure and, when it is not, the one the escalation itself
    declares (`declared` — the `surface` the model wrote on its own `escalate_to_slowbrain`). Measured on the next
    live turn (2026-10-27 11:23:54, T61): he answered «solo de correo… céntrate en el correo y en los mensajes
    enviados»; the model escalated with `surface = informe` and a document `done_when`, the verdict's surface was
    unsure (informe 0.52 → read 0.42), and with only the verdict to go by the same `mail_folder {sent}` stood in
    for the errand again — «voy con el correo enviado…», and nothing ran."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    if not wid or (brief is None and not str(declared or "").strip()):
        return False
    try:
        from widgets import effects as _fx
        if _fx.DATA_READ not in _fx.of(wid, str(action or "").strip()):
            return False
        from nucleo import surfaces as _sf
        from nucleo.flash import turn_brief as _tb
        verb, info = _tb.read(brief, _tb.CANVAS_KEY, "") if brief is not None else ("", None)
        if info is not None and str(verb or "") == "show":
            return False
        surface, s_info = (_tb.read(brief, _sf.SURFACE_KEY, "", min_confidence=0.7) if brief is not None
                           else ("", None))
        # the verdict when it is sure (today's reading, untouched); unsure, the escalation's own declaration
        surface = _sf.normalize(surface if s_info is not None and surface else declared)
        return bool(surface) and _sf.not_a_sheet(surface) and _sf.normalize(wid) != surface   # its own box is it
    except Exception as e:  # noqa: BLE001 — unreadable: today's path
        from loguru import logger
        logger.debug(f"canvas_visibility: view check for {wid}:{action} skipped — {e!r}")
        return False


def unless_a_view(got, brief, outcome: dict | None = None, declared: str = ""):
    """`got` (a rung's or a pass's call), or None when it is a view that is not the deliverable — said on the timeline,
    and a promise pass's outcome recorded as JUDGED: there was nothing to run on the card (V2-820). Never raises."""
    try:
        if not got or not a_view_is_not_the_deliverable(got.get("widget_id"), got.get("action"), brief,
                                                         declared=declared):
            return got
        from voice.observer import emit
        emit("brain", "🔁 la segunda pasada no dio llamada", text=f"{got.get('widget_id')}: a view is not the errand",
             role="system", extra={"cat": "flash", "widget": got.get("widget_id"), "action": got.get("action"),
                                   "why": "view_not_deliverable"})
        if outcome is not None:
            from nucleo.turn import promise_kept as _pk
            outcome["kind"] = _pk.JUDGED
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"canvas_visibility: unless_a_view failed — {e!r}")
    return None


def _say(emit, label: str, extra: dict) -> None:
    """Emit on the stream the caller gave, or the observer's. A broken stream is logged, never raised."""
    from loguru import logger
    try:
        if emit is None:
            from voice.observer import emit as observer_emit
            emit = observer_emit
        emit("widget", label, extra=extra)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"canvas_visibility: could not emit {label!r} — {e!r}")


def is_minimized(widget_id: str) -> bool:
    """Open on the canvas but put away in the rail — not in front of him. A show brings it back (desktop.js)."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    try:
        from memory import api as _memapi
        return bool(wid) and wid in {str(w).strip().lower() for w in ((_memapi.state() or {}).get("minimized_widgets") or [])}
    except Exception:  # noqa: BLE001
        return False


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
