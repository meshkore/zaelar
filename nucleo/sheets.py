"""nucleo/sheets.py — the results SHEET as the surface of ONE errand (V2-276).

Extracted from `nucleo/dispatch.py` on 2026-08-24 to satisfy the architecture ratchet, which had been red
since the previous night because of MY commits: `dispatch.py` was 22 lines over its ceiling and that table's
rule is explicit — a file that grows calls for EXTRACTION, and its only precedent for being raised requires
being able to say what duplication was removed. I removed none, so it is extracted.

This section was chosen because the boundary was already drawn: it had its own banner since V2-227, and
`widgets/results/data.py` and `widgets/navegador/act_api.py` already imported from here through `dispatch` —
a widget layer asking a session manager what its box is called.

SHEET MODULE deliberately: it does not import `dispatch`. The three functions that need to traverse the live
registry receive the sessions as an argument (`sessions=`), and `dispatch` wraps them by passing its own. Doing
it the other way around — importing `_SESSIONS` from here — is the cycle V2-112 already paid for (`research.py`
grabbing a private name from `dispatch`, and only the ENTIRE suite caught it, at runtime).

Everything is re-exported from `dispatch`: this is a move, not an interface change.
"""
from __future__ import annotations

import time

from nucleo import surfaces
from nucleo.runtime_ids import boot_id as _boot_id

#: The phase ring: what fits in a tab without becoming a log. It lives here because it is the length
#: of what the SHEET renders; `dispatch.record_phase` re-imports it to trim the registry to the same figure.
#: How many PROCESS lines are retained. Raised from 40 to 150 in V2-345, and the number comes from measurement,
#: not taste: the real `search-buy-used-car` errand (session `7575e81a`, 21.6 min) produces **127 lines** with
#: the worker's narration included. With 40 the tab showed the last ~7 minutes and its own closing sentence
#: —«Esto es lo que hizo para llegar aquí»— stopped being true exactly when it was read most, at completion.
#: It is still a RING and still what the operator WATCHES, not the audit: that lives entirely in
#: observability, with its evidence. What changes is that a whole errand now fits.
PHASES_KEPT = 150

# ── the results SHEET as the progress surface (V2-227 scope C) ────────────────────────────────────────────────
# The live registry is the ONLY owner of «qué está pasando». The sheet does not store it: it READS it on every
# `view_data`, just like `counts`. Storing it would reproduce the state in two places and leave the stale copy
# on screen — exactly the failure this scope exists to remove.
def sheet_sessions(sessions, live_states) -> list:
    """The LIVE sessions whose surface is the sheet (`lista`/`item`). Other errands are not rendered here.

    Receives the registry instead of importing it: see the SHEET module note in the header.
    """
    return [r for r in list(sessions)
            if r.status in live_states and surfaces.opens_sheet(getattr(r, "surface", ""))]


def _phrases(rec) -> list:
    """The phases of a record, already readable and ordered, without the `{t, s}` scaffolding."""
    out = []
    for p in list(getattr(rec, "phases", None) or []):
        s = str((p.get("s") if isinstance(p, dict) else p) or "").strip()
        if s:
            out.append(s)
    return out


#: Seal of THIS process. `escalate._seq` returns to 0 on every startup, so a `task_id` does not identify an
#: errand beyond the engine's lifetime; a sheet id DOES have to, because the sheet is stored on disk and
#: survives restart (V2-233). Random and short: it need not be readable, it must not collide.
def sheet_id_for(task_id) -> str:
    """The SHEET id of an errand. ONE definition: record sealing and anyone who needs to reconstruct it use it,
    so there are not two ways to name the same box."""
    return f"{_boot_id()}-{str(task_id or '').strip()}"


def sheet_of(rec) -> str:
    """An errand's sheet, sealed ONCE (the same rule as `surfaces.set_once`: changing it midway moves what the
    operator is already watching). Returns "" if this errand has no sheet — the default is then used, which is
    correct for a browser with no errand behind it."""
    return str(getattr(rec, "sheet", "") or "")


def sheet_for_nav_task(nav_task: str, sessions=()) -> str:
    """The sheet of the ERRAND this browser task belongs to ("" if it belongs to none).

    V2-259 — the browser finds things and delivers them to the sheet (V2-257), but the sheet belongs to the ERRAND
    and the browser task has its own id: two browsers from the same search deliver to the SAME sheet. `_prepare_web`
    already stores `rec.nav_task`, so the route exists; what was missing was asking for it. With no errand behind it
    —the operator driving the browser manually— it returns "", the default sheet, which is correct.
    """
    tid = str(nav_task or "").strip()
    if not tid:
        return ""
    for r in list(sessions):
        if str(getattr(r, "nav_task", "") or "") == tid:
            return sheet_of(r)
    # V2-290 — AND BY THE ID OF THE ERRAND ITSELF, because not everyone driving the browser has a reserved tab.
    # `_prepare_web` creates the tab and stores `rec.nav_task` ONLY for `kind="web"`; any other errand that opens
    # the browser falls back to `nucleo/nav_cli.py` — «`ZAELAR_NAV_TASK` o, si no, `ZAELAR_TASK_ID`» — so its tab
    # is named after the TASK. That route did not exist here, and without it findings from that tab found no box.
    #
    # Measured in the 12:03 run, `search-buy-bicycle__es`: the research worker opened tab «3», extracted SEVEN real
    # bicycles with price and link, and all seven were written to bare `results` while `results::3fc631-1` —the
    # errand's open sheet with its title— remained empty. The same happened in the camera, with fourteen. The bare
    # box belongs to nobody since V2-259, so this was invisible by construction: the operator faced a blank card while
    # the results sat in a box nobody had opened for them.
    #
    # The applicable rule is the same one that resolves the id in the bridge, so it is written the same way: the tab
    # is named after its browser task if it has one, otherwise after its errand. Two ways to name the same thing in
    # two different places are how this crack began.
    for r in list(sessions):
        if str(getattr(r, "task_id", "") or "") == tid:
            return sheet_of(r)
    return ""


def sheet_for_delivery(nav_task: str, sessions=(), live_states=()) -> str:
    """The sheet where this tab should DELIVER what it just found, OPENING IT if its errand does not yet have one.

    V2-290 — the sheet opens when COMMISSIONED only when the brain declared the sheet as its surface
    (`surfaces.opens_sheet`), and that is correct: an empty box is not opened for someone who will not fill it. But an
    errand that did NOT declare it may end up driving the browser and extracting rows, so the premise no longer holds:
    there are findings with nowhere to put them. Measured in the 12:03 run: the RESEARCH worker for
    `search-buy-bicycle__es` extracted SEVEN bicycles with price and link and all seven fell into bare `results`,
    which belongs to nobody since V2-259; same in the camera, with fourteen. Invisible by construction.

    Opening it HERE rather than when commissioned is the difference between an empty box nobody asked for and one that
    appears with the first result inside. And only for a LIVE errand: a finding arriving after its errand died does not
    create a card on the screen of someone who has already moved on.
    """
    sheet = sheet_for_nav_task(nav_task, sessions)
    if sheet:
        return sheet
    tid = str(nav_task or "").strip()
    for r in list(sessions):
        if r.status not in live_states:
            continue
        if tid in (str(getattr(r, "nav_task", "") or ""), str(getattr(r, "task_id", "") or "")):
            _sheet_open(r)
            return sheet_of(r)
    return ""


def sheet_progress(sheet: str = "", sessions=(), live_states=()) -> dict:
    """`{alive, phases}` — what the sheet's PROCESS tab must render RIGHT NOW.

    `alive` means «an errand is in progress», not «it has said something»: the sheet opens before the first phase, and
    that gap of a few seconds is exactly when the operator is looking at the blank screen they asked to remove.

    `sheet` narrows this to ONE errand (V2-259: one sheet per errand, keyed by `task_id`). Without it, the old
    behavior remains —the phases of all live errands, interleaved IN TIME ORDER— which was the honest answer when
    there was one sheet: choosing one errand silently hid that another was working. Separate sheets make that
    unnecessary, but the sheet WITHOUT an instance still exists and still deserves the complete account.
    """
    rows = sheet_sessions(sessions, live_states)
    # V2-259 — with ONE sheet per errand, a box's account is that of ITS errand. The interleaving below was the honest
    # answer while there was one sheet (choosing one errand hid that another existed); now each has its own place,
    # and mixing them would tell the same story twice in two places.
    want = str(sheet or "").strip()
    if want:
        rows = [r for r in rows if sheet_of(r) == want]
    if not rows:
        return {"alive": False, "phases": []}
    seq = []
    for r in rows:
        for p in list(getattr(r, "phases", None) or []):
            s = str((p.get("s") if isinstance(p, dict) else p) or "").strip()
            if s:
                seq.append((float(p.get("t") or 0.0) if isinstance(p, dict) else 0.0, s))
    seq.sort(key=lambda x: x[0])
    return {"alive": True, "phases": [s for _, s in seq][-PHASES_KEPT:]}


def sheet_harvest(sheet: str = "", sessions=(), live_states=()) -> dict:
    """This sheet's HARVEST: how much has been viewed and what survived each cutoff (V2-296).

    Sibling of `sheet_progress` with the same division: that one counts WHAT it is doing, this one HOW MUCH it has
    done. They remain separate because one is an account and the other arithmetic, and because the account is trimmed
    to the last `PHASES_KEPT` lines while totals cannot be trimmed without lying.

    DERIVED on every read, just like phases: the browser tab (`widgets.navegador.tasks`) owns the numbers, and the
    sheet READS them. Keeping a copy here would be the defect already documented by `_progress` —the same state in
    two places, with the stale one always remaining on screen—.

    It is SUMMED across the sheet's errands because one errand can open more than one tab (searching two sites): two
    viewed pages are two, wherever they came from. With no live errand it returns `{}`, allowing the sheet to fall
    back to what it saved on close instead of rendering zeroes —a zero says «se miró y no había», which is not the
    same as «ya no lo sabemos».
    """
    rows = sheet_sessions(sessions, live_states)
    want = str(sheet or "").strip()
    if want:
        rows = [r for r in rows if sheet_of(r) == want]
    if not rows:
        return {}
    try:
        from widgets.navegador import tasks as _nav
    except Exception:  # noqa: BLE001
        return {}
    total, seen = {}, set()
    for r in rows:
        tid = str(getattr(r, "nav_task", "") or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        for k, v in ((_nav.get(tid) or {}).get("tally") or {}).items():
            if k in _nav.TALLY_KEYS:
                total[k] = int(total.get(k, 0)) + int(v or 0)
    return total if any(total.values()) else {}


def title_of(rec) -> str:
    """How this errand is NAMED on screen: its title when one has been composed, its brief otherwise (V2-530).

    One function because there are three readers — the sheet's header, the disambiguation question that names
    open sheets, and the voice relaying a worker's question — and a rule written three times is how it comes to
    be missing from one of them.
    """
    try:
        from nucleo import errand_title as _et
        t = str(getattr(rec, "title", "") or "").strip()
        return t or _et.provisional((getattr(rec, "goal", "") or "").strip())
    except Exception:  # noqa: BLE001
        return (getattr(rec, "goal", "") or "").strip()


def retitle(rec) -> None:
    """Rename an OPEN sheet once its title has been composed. Fail-soft: the provisional name is already
    truthful, so a failure here costs nothing and must never reach the errand."""
    try:
        from widgets.results import data as _sheet
        _sheet.rename_task(title_of(rec), sheet=sheet_of(rec))
    except Exception:  # noqa: BLE001
        pass


def _sheet_open(rec) -> None:
    """OPEN the sheet when COMMISSIONED, which is the entire gesture of scope C: without this the operator sees nothing
    until there is a response, leaving the screen contract fulfilled in a test and absent in the product.

    ONE SHEET PER ERRAND (V2-259), keyed by `task_id`. It used to be unique, so the choice was between opening it
    —deleting what another errand still writing had delivered— and reusing it, which showed the previous search's
    results as though they belonged to this one. Neither was good, and the first is literally the «error de borrar
    búsquedas» the operator asked to remove. With one key per errand the dilemma disappears: each opens its own and
    nobody overwrites anybody.

    Everything is fail-soft: a failure here must not bring down an escalation.
    """
    # The SEAL, once and before anything else: everything written to this sheet must name it the same way.
    #
    # A RELAY IS NOT A NEW ERRAND (measured 2026-08-23, `cheapest-monitor`). When the provider runs out of
    # quota, `session._finish` relaunches the SAME goal on the next tier — and that relaunch minted a fresh
    # `task_id`, so it minted a fresh SHEET: the operator ended up with `results::…-1` empty and `results::…-2`
    # holding the 13 findings, two boxes for one errand, and the turn saying "they are in your results widget"
    # about the wrong one. Same for the context-overflow handoff (V2-117). If the escalation arrives carrying
    # its predecessor's sheet, it is INHERITED — this is the continuation of the same thing, not another one.
    # INHERITED is asked by comparing against MY OWN, never by checking whether the field is filled. The first
    # version read "already has a sheet ⇒ it came from someone else" and turned a V2-259 test red — rightly: an
    # errand can arrive with ITS OWN sheet already sealed, and that does not make it a relay. A relay's sheet is
    # its PREDECESSOR's, so it does not derive from this `task_id`.
    _mine = ""
    try:
        _mine = sheet_id_for(rec.task_id)
    except Exception:  # noqa: BLE001
        pass
    _inherited = bool(getattr(rec, "sheet", "")) and str(rec.sheet) != _mine
    if not getattr(rec, "sheet", ""):
        rec.sheet = _mine
    _sid = sheet_of(rec)
    try:
        from widgets.results import data as _sheet
        # V2-259 — ITS sheet. `fresh` is no longer a difficult decision: a new sheet is a new KEY, so opening one
        # can no longer delete someone else's content (which is literally what the operator asked to avoid).
        #
        # …except when the sheet is INHERITED, where `fresh` is precisely the damage: `present` REPLACES the
        # items, so starting the predecessor's sheet fresh wipes whatever it had already delivered before running
        # out of quota. Inheriting without this turns "two boxes" into "one empty box", which is worse.
        # V2-530 — the sheet is named by the errand's TITLE, falling back to its brief. The brief is the
        # operator's raw turn on purpose (see `SessionRecord.title`), and a raw turn read as a name gave the
        # operator a box called «Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres…».
        _sheet.begin_task(title_of(rec), fresh=not _inherited, sheet=_sid)
        _sheet.prune_sheets()          # the sheet persists deliberately; N instances cannot grow without a ceiling
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice.observer import emit
        from widgets.results import data as _sheet2
        emit("widget", "show",
             extra={"id": _sheet2.instance_id(_sid), "src": f"worker:{rec.task_id}"})
    except Exception:
        pass


def _sheet_close(rec) -> None:
    """The errand is OVER: the loader stops and the history remains with the report.

    Two things can only be done here. (1) Nobody else announces the end: the phase emitter fires only when a phase
    CHANGES, so without this write the card would keep saying «Trabajando…» about a worker that no longer exists.
    (2) The live registry is discarded on completion, along with its phrases; the sheet IS persistent —a report that
    survives a restart with its explanation of how it was reached erased tells only half the story.
    """
    try:
        from widgets.results import data as _sheet
        _sheet.end_task(_phrases(rec), sheet=sheet_of(rec))
    except Exception:  # noqa: BLE001
        pass


def record_phase(rec, phase: str, phases_kept: int = 0) -> bool:
    """Write ONE line to the journal read by the PROCESS tab. Returns whether it was added.

    SHEET MODULE (V2-281): receives the REGISTRY, does not look it up — `dispatch` has it and wraps this module.

    It is the ONLY home for that rule because it has TWO unlike doors: what the worker narrates (`hbnote`, via
    `session_phase`) and what we do when translating its tool steps into a phrase (`nucleo/workers/progress.phrase`,
    via the backend stream). Until 2026-08-21 the latter did not pass through here, and the effect was not a worse line:
    it was **no line at all**. The operator's `ed9df756` session proves it —the worker opened Google Maps, closed the
    overlay, captured, snapshotted and clicked twice, extracted the route with traffic, and the tab said «trabajando»
    for two and a half minutes because the only two entries reaching this ring were the ones the worker chose to narrate,
    and they arrived at the end.

    It is DEDUPLICATED against the last entry: three consecutive `scroll`s produce «recorriendo la página» three
    times, and three identical lines convey nothing —they look like progress without being it. The ring is short on
    purpose: this is what the operator WATCHES, not the audit (which already lives in observability, complete and with evidence).
    """
    r, _p = rec, (phase or "").strip()
    if r is None or not _p:
        return False
    # V2-358 — a step that CLAIMS something about the operator's sheet that the sheet does not support is MARKED as
    # what it is: the worker's word. Here rather than in `dispatch.session_phase` because this is where the ring is
    # written and the record is already in hand — and because the architecture ratchet asked for it to be extracted.
    # The reason for the mark is in `live_blocks.worker_phase_is_a_claim`. It deliberately comes BEFORE deduplication:
    # the marked and unmarked lines are the same phrase, and collapsing them would hide precisely that distinction.
    try:
        from nucleo.flash import live_blocks as _lb
        if _lb.worker_phase_is_a_claim(_p, sheet_of(r)):
            _p = "💬 " + _p
    except Exception:  # noqa: BLE001
        pass
    if r.phases and r.phases[-1].get("s") == _p:
        return False
    r.phases.append({"t": time.time(), "s": _p})
    del r.phases[:-(phases_kept or PHASES_KEPT)]
    # …and let the open card know. `widgets/store.py` emits this on SAVE, and there is nothing to save here:
    # the process is a view of the live registry, not sheet data. Without this notice the tab would remain still
    # until the next data change —a progress panel that does not advance.
    if surfaces.opens_sheet(getattr(r, "surface", "")):
        try:
            from voice.observer import emit as _emit_w
            from widgets.results import data as _sheet3
            _emit_w("widget", "data",
                    extra={"id": _sheet3.instance_id(sheet_of(r)), "src": "worker"})
        except Exception:
            pass
    return True
