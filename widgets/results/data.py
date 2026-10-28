#
# results widget — backend. INTENTIONALLY does no searching of its own: it is the GENERIC PRESENTATION SURFACE of
# zaelar. Whoever DID the work (a Brain Worker that searched the web, the browser, the FlashBrain) hands it a
# finished result set and this widget just PERSISTS and RENDERS it. Works the same for pools, cars, holidays,
# open-source projects, emails, files — it never knows nor cares what the items are about.
#
# HOW IT GETS FILLED (the only way; there is no other channel):
#   a Brain Worker →  python -m nucleo.widget_cli data results present '{"title": "...", "items": [...]}'
#   the FlashBrain →  tool widget_data(widget_id="results", action="present", payload={...})
# Both land on apply_action() below → store.save() → the single SSE "this widget changed" event → the open card
# re-fetches view_data() and re-renders. Because the payload is PERSISTED (not ephemeral), it survives the
# re-render, a reconnect and a server restart — the operator does not lose a report he already paid for.
#
# HISTORY (2026-08-02): view_data() used to return a hardcoded demo list of the operator's projects
# (Pricewaterhouse / Mage Core / MeshKore…). Showing the widget for a pool search therefore painted "Proyectos" —
# which is exactly what the operator saw and reported ("I only see the projects widget open; it has nothing to do
# with this"). A generic presentation surface has NO content of its own: with nothing pushed it is an EMPTY
# SHEET, never someone else's data.
#
# HISTORY (2026-08-09): a result was strictly FLAT — one card = one thing. That cannot express what a real
# research answer looks like: the operator asked for holiday PROPOSALS, and a proposal is a BUNDLE (this hotel +
# that ferry crossing + maybe a restaurant), each piece with its own price, photo, link and times. Flattening a
# bundle into free text loses the structure the operator wants to compare on. So an item may now carry `parts`
# (the pieces it is made of) plus, for the DRILL-DOWN, `images`/`facts` (a photo gallery and the label→value
# sheet: check-in, port, cancellation policy...). And `view`/`focus` give the sheet a SECOND PAGE: "show me proposal
# 1 in detail" switches this same widget to the full dossier of one item instead of the compact grid.
#
# HISTORY (2026-08-12) — THE SHEET HAS FOUR TABS, not only the list. Operator rule: this surface will be used
# generically for MANY complex searches, and a complex search is not just its result. It is also HOW it is going, WITH
# WHICH criteria, and WHERE the data comes from. Until today the last three only existed verbally —you had to ask the
# agent— and therefore could not be checked:
#
#   · RESULTS (the important one) — cards, and a card's full record when opened.
#   · SUMMARY — work status + how many candidates were explored, how many remain on screen, what was done.
#   · SOURCES — which websites it entered and WHAT HAPPENED on each one: entered, could not due to auth, limited to
#               50 results, errored. This turns "I found nothing" into auditable data.
#   · CRITERIA — the task as currently executed (hard/soft/assumed/rubric) PLUS corrections the operator gives by
#                voice ("they should be 42 to 49 feet"). Seeded automatically from the BRIEF (`nucleo/research.py`),
#                so they do not depend on the worker remembering to write them.
#
# All four live in the SAME persisted payload as the list, and so does the active tab (`tab`) — just like
# `view`/`focus`: this way "show me where you got this from" is a voice command that moves the screen, and state
# survives re-render, reconnect, and restart. Zero new protocol: everything enters through DECLARED actions.
#
# And the RECORD is DYNAMIC (`blocks`): each result type needs to be shown differently — a boat does not read like a
# paper or an email. Instead of a fixed schema (which forces anything that does not fit into prose) or raw worker HTML
# (an injection waiting to happen: this payload comes from the open web), an item may bring a LIST OF BLOCKS from a
# closed vocabulary —text, facts, tags, gallery, meter, table, link, section— that the surface paints with
# `textContent`. Same composition freedom without handing the surface to a third party.
#
import time as _tm
import unicodedata as _ud

from .. import store
from i18n import langs as _langs, runtime as _i18n_rt  # noqa: F401 — V2-778 F3-30: hints are read back aloud, in the agent's language
from .sheet_names import (  # noqa: F401 — re-export: this module IS the sheet contract
    WIDGET_ID, _INSTANCE_SEP, _MAX_SHEETS, _safe_sheet, card_face, instance_id, prune_sheets, recent_faces,  # noqa: F401
    sheet_key, sheets)

# How one VALUE from a payload becomes something paintable — the rating, the photos, the lines and the closed
# block vocabulary of a dynamic record (`widgets/results/record.py`, V2-702; moved byte for byte to pay the
# ratchet). Re-exported because this module is the sheet's contract: callers and tests keep saying `data._MAX_LINES`.
from .record import (  # noqa: F401,E402 — re-export
    _BLOCK_KINDS, _MAX_BLOCKS, _MAX_CELL_CHARS, _MAX_CHIPS, _MAX_FACT_CHARS, _MAX_FACTS, _MAX_IMAGES,
    _MAX_LINE_CHARS, _MAX_LINES, _MAX_TABLE_COLS, _MAX_TABLE_ROWS,
    _clean_block, _clean_blocks, _clean_facts, _clean_images, _clean_lines, _clean_meta, _clean_score, _num)


# The closed schema of a pushed payload — fields, caps, the word-boundary clip — lives in `clean.py`
# (refactor2710-12, moved byte for byte); re-exported because this module is the sheet's contract.
from .clean import (  # noqa: F401,E402 — re-export
    _CRIT_LISTS, _ITEM_FIELDS, _MAX_CRIT, _MAX_CRIT_CHARS, _MAX_DETAIL_CHARS, _MAX_ITEMS, _MAX_PART_LINES,
    _MAX_PARTS, _MAX_REJECTED, _MAX_SOURCES, _MAX_STEP_CHARS, _MAX_STEPS, _MAX_WHY_CHARS, _PART_FIELDS,
    _REJECTED_FIELDS, _SLOT_CLIP_KEYS, _SOURCE_FIELDS, _SOURCE_STATUS, _SUMMARY_NUMS, _SUMMARY_TEXT,
    _clean_criteria, _clean_item, _clean_items, _clean_part, _clean_parts, _clean_rejected, _clean_source,
    _clean_sources, _clean_summary, _clip, _clip_slot)

# ── THE TABS THAT ARE NOT THE LIST ───────────────────────────────────────────────────────────────────────────
# «process» IS a tab like the others: if the operator selects it, the choice PERSISTS just like the others. It was
# missing from this tuple and the click returned `{"ok": false, "error": "pestaña «process» desconocida"}` —the tab
# was rendered (the widget switches it immediately), and on the next data refresh, which arrives with each phase
# during a live task, the derived state carried it back to Results. An unsaved click does not fail noisily: it fails
# by pulling the operator away from where they chose to look (V2-227 C).
# V2-822 — and «process» is no longer one: an errand's progress lives in the processes panel (the running process's
# entry), never inside its deliverable. The alias below still reads «proceso»: the `tab` action opens that panel.
_TABS = ("results", "summary", "sources", "criteria")

#: WHAT KIND OF THING the sheet found. This is CONTENT, not layout — which is the whole reason it is allowed to
#: come from outside. `widgets/presentation.py` rule 1 says the surface owns the layout and whoever fills it must
#: not send `columns`; saying «these are products» breaks none of that: it is a fact about the results, and
#: `widget.js::layoutFor` is still the one that turns it into a shape (photo left / gallery / plain rows). Absent
#: or unknown, the shape of the items decides on its own, exactly as before.
_KINDS = ("product", "place", "media", "photo", "document", "link", "plan")

#: WHICH TEMPLATE the list is drawn with. V2-703, and a deliberate reversal of `presentation.py` rule 1 («the
#: surface owns the layout»), by the operator's explicit decision: «tenemos varias [plantillas] que le ofrecemos
#: al Brainworker para que elija la más adecuada para cada lista de resultados […] sí debe elegir ese formato y
#: colocar dentro los datos que sean relevantes».
#:
#: The reason rule 1 existed has NOT gone away, so it survives as a guard instead of a veto. What the worker may
#: send is a NAME out of this closed set — never a width, a column count or a pixel — and `widget.js` refuses one
#: it cannot honour (a photo template over results with no photos) instead of drawing it badly. That is the line:
#: the worker chooses the SHAPE and fills the slots; the surface still owns the geometry of each slot.
_LAYOUTS = ("card", "tile", "row", "list", "compare", "split", "gallery", "rows")


# ── PRESENTATION QUALITY CONTROL — the trace half (the clip half is `clean._clip`) ──────────────────────────────
def _audit(payload: dict) -> list[str]:
    try:
        from widgets import presentation
        issues = presentation.audit(WIDGET_ID, payload)
    except Exception:
        return []
    if issues:
        try:
            from voice.observer import emit
            emit("widget", "🎨 presentación: calidad de los datos", text=" · ".join(issues)[:400],
                 role="system", extra={"id": WIDGET_ID, "n": len(issues), "issues": issues[:12]})
        except Exception:
            pass
    return issues


def default_title() -> str:
    """The filler title of a sheet nothing named, in the instance's language («Results» / «Resultados»)."""
    try:
        return _i18n_rt.text("widgets.results.name", default="Results")
    except Exception:  # noqa: BLE001
        return "Results"


def note_text(key: str, default: str) -> str:
    """One of the sheet's own notes («No results.», «Searching in depth…») in the instance's language."""
    try:
        return _i18n_rt.text(f"widgets.results.{key}", default=default)
    except Exception:  # noqa: BLE001
        return default


def _empty() -> dict:
    return {"title": default_title(), "subtitle": "", "items": []}


# The live PROCESS lives in `widgets/results/live.py` (V2-296): everything there is derived from the dispatcher's
# record, while this module contains the sheet's content. It is re-exported because this is a move, not an interface
# change —the tests and `view_data` continue calling these names as before.
from widgets.results.live import (  # noqa: E402,F401 — re-export
    _MAX_PHASES, _MAX_PHASE_CHARS, _browser, _clean_phases, _harvest, _progress)


# The derived fields (`_counts`, `_identity`) and the write that strips them (`_save`) live in `derived.py`.
from .derived import _counts, _identity, _save  # noqa: E402,F401 — re-export


def view_data(q: str = "") -> dict:
    """The LAST result set pushed here, verbatim. Nothing pushed yet → an empty sheet (never invented content).

    `q` is the INSTANCE (V2-259): the canvas already splits `results::<corr>` and hands the suffix over as `q`
    (`desktop.js::show`), so this signature did not have to change — it just stopped ignoring the argument.
    """
    db = store.load(sheet_key(q), _empty())
    if not isinstance(db, dict):
        db = _empty()
    data = dict(db)
    data.setdefault("title", default_title())
    data["items"] = _clean_items(data.get("items"))
    data["sources"] = _clean_sources(data.get("sources"))
    data["summary"] = _clean_summary(data.get("summary"))
    data["criteria"] = _clean_criteria(data.get("criteria"))
    if data.get("tab") not in _TABS:
        data.pop("tab", None)                    # without a valid tab, results wins (the widget decides)
    # V2-591: a scroll request EXPIRES — re-applying a stale one on a reload would move what the operator is
    # reading with no order behind it. 120 s covers the voice round-trip with margin.
    _sc = data.get("scroll") or None
    if _sc:
        if not (float(_sc.get("at") or 0) and (_tm.time() - float(_sc.get("at") or 0)) <= 120):
            data.pop("scroll", None)
    data["empty"] = not data["items"]                # V2-776 L2 — the harness reads emptiness, never guesses it
    if not data["items"]:
        data.setdefault("note", note_text("no_results", "No results yet."))
        data.pop("view", None)                   # no items ⇒ there is nothing to be showing the detail OF
        data.pop("focus", None)
    stored = _clean_phases(data.get("process"))
    if stored:
        data["process"] = stored
    else:
        data.pop("process", None)            # without history, the blank sheet remains blank
    data["counts"] = _counts(data)
    data["progress"] = _progress(data, _safe_sheet(q))
    data["harvest"] = _harvest(data, _safe_sheet(q))
    data["browser"] = _browser(data, _safe_sheet(q))     # V2-571/822: what the browser needs HIM to do (wall, login)
    data["identity"] = _identity()                       # V2-601 T-10: rides the payload; widget.js may not fetch
    return data


# ── THE TASK OPENS AND CLOSES THE SHEET (V2-227 scope C · extracted to `widgets/results/lifecycle.py`, V2-530) ─
# The three gateways the dispatcher uses so the operator can SEE the work as it proceeds. They are not actions in
# `apply_action`'s vocabulary: no prompt requests them; the task lifecycle triggers them —putting them there would
# expose them to a worker, which is precisely who must not decide when the sheet is opened.
# They are re-exported here —the same move and gesture as `live.py` (V2-296)— because this module IS the sheet's
# contract for everyone using it: callers continue saying `data.begin_task`.
from widgets.results.lifecycle import (  # noqa: E402,F401 — re-export
    begin_task, end_task, rename_task)


# Which item a reference names (`_find`), and what the brain sees of the sheets (`ref_index`, `prompt_digest`)
# live in `find.py` (refactor2710-12); `widgets/refs.py` looks the two hooks up HERE by name.
from .find import _find, _named, _sheets_for_brain, prompt_digest, ref_index  # noqa: E402,F401 — re-export

# V2-287 — the prompt digest lives in its own module (`digest.py`): pure functions over a sheet dict, with no store
# and no writes. The two names that DO need storage remain here —which sheets exist and what is inside them—, and
# `_digest_head`/`_digest_one` remain re-exported because they are the contract already used by the surface tests.
from . import digest as _digest                                                              # noqa: E402,F401
from .digest import head as _digest_head, one as _digest_one, _MAX_HEAD_CHARS, _MAX_HEAD_ITEM  # noqa: E402,F401


# The sections merged alongside present/append, and the spoken tab names, live in `merge.py` (refactor2710-12).
from .merge import _TAB_ALIASES, _merge_sections  # noqa: E402,F401 — re-export


# V2-778 F1-12 — the action handlers live in `actions.py`, imported back under their names (that module
# reads this one).
from .actions import (  # noqa: E402,F401
    _a_present, _a_append, _a_clear, _a_choose, _a_detail, _a_list, _a_scroll, _a_layout, _a_tab, _a_sources,
    _a_rejected, _a_progress, _a_criteria, _a_auth_done)


# V2-778 F1-12 — one function per action (in `actions.py`), and `apply_action` is the table lookup. Each body
# is the branch it was, moved verbatim; the contract gate reads the table's keys
# (`widgets/validator._table_actions`).


ACTIONS = {
    "present": _a_present,
    "append": _a_append,
    "clear": _a_clear,
    "choose": _a_choose,
    "detail": _a_detail,
    "list": _a_list,
    "scroll": _a_scroll,
    "layout": _a_layout,
    "tab": _a_tab,
    "sources": _a_sources,
    "rejected": _a_rejected,
    "progress": _a_progress,
    "criteria": _a_criteria,
    "auth_done": _a_auth_done,
}


# present/append/clear = how the result set is delivered. `choose` lets the operator PICK one of the shown items
# (e.g. "quiero esa"); unlike before it now PERSISTS the pick, because the list itself is persisted — the old
# comment about avoiding store.save() described the ephemeral-push era and no longer applies.
# `detail`/`list` flip this same sheet between the compact grid and ONE item's full dossier. The view lives in
# the persisted payload (not in the browser) so the operator's voice drives it: the widget has no state of its own.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    # V2-259 — WHICH sheet. It travels in the payload rather than the URL for the same reason as `task_id` in the
    # browser: the canvas sends actions to the BASE widget and puts the instance inside (`desktop.js`). Without
    # `sheet`, this continues operating on the default sheet, which keeps the change from breaking anyone.
    #
    # ...and `q` is the SAME THING under the canvas's own name, which is the whole bug of V2-540. `ctx.action`
    # stamps the instance into every payload as `q` (`desktop.js`, one place, for every widget) while this read
    # only ever looked for `sheet`, a key the canvas has never sent. So EVERY click on an instantiated sheet —
    # «Ver detalle», «choose», switching tab — was answered against the DEFAULT sheet, found nothing there and
    # came back `{ok:false}`. Reported by the operator as «el botón de ver detalle no es clic», which is exactly
    # what a working button looks like when its request lands on the wrong sheet.
    # `view_data(q)` has read the instance out of `q` since V2-259; the writer simply never followed.
    sheet = _safe_sheet(payload.get("sheet") or payload.get("q"))
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose · detail · "
                                      f"list · tab · sources · progress · criteria · auth_done)"}
    return handler(action, payload, sheet)
