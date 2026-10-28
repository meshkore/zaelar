#
# results widget — backend. Does NO searching of its own: it is zaelar's GENERIC PRESENTATION SURFACE. Whoever did
# the work (a Brain Worker, the browser, the FlashBrain) hands it a finished result set; this widget PERSISTS and
# RENDERS it, never knowing what the items are about. With nothing pushed it is an EMPTY SHEET, never invented data.
#
# HOW IT GETS FILLED (the only way):
#   a Brain Worker →  python -m nucleo.widget_cli data results present '{"title": "...", "items": [...]}'
#   the FlashBrain →  tool widget_data(widget_id="results", action="present", payload={...})
# Both land on apply_action() → store.save() → the SSE "widget changed" event → the card re-fetches view_data().
# The payload is persisted, so it survives re-render, reconnect and restart.
#
# An item may be a BUNDLE (`parts`: hotel + ferry + restaurant) with a drill-down (`images`/`facts`); `view`/`focus`
# switch the sheet to one item's full dossier. FOUR TABS — results, summary, sources (what happened on each site),
# criteria (seeded from the brief in `nucleo/research.py`, plus spoken corrections) — and the active `tab` live in
# the same persisted payload, so voice moves the screen. A record is DYNAMIC (`blocks`) from a closed vocabulary
# painted with `textContent`, never worker HTML: this payload comes from the open web.
#
import time as _tm
import unicodedata as _ud

from .. import store
from i18n import langs as _langs, runtime as _i18n_rt  # noqa: F401 — V2-778 F3-30: hints are read back aloud, in the agent's language
from .sheet_names import (  # noqa: F401 — re-export: this module IS the sheet contract
    WIDGET_ID, _INSTANCE_SEP, _MAX_SHEETS, _safe_sheet, card_face, instance_id, prune_sheets, recent_faces,  # noqa: F401
    sheet_key, sheets)

# How one VALUE becomes paintable (rating, photos, lines, the closed block vocabulary) lives in `record.py`
# (V2-702); re-exported because this module is the sheet's contract (`data._MAX_LINES`).
from .record import (  # noqa: F401,E402 — re-export
    _BLOCK_KINDS, _MAX_BLOCKS, _MAX_CELL_CHARS, _MAX_CHIPS, _MAX_FACT_CHARS, _MAX_FACTS, _MAX_IMAGES,
    _MAX_LINE_CHARS, _MAX_LINES, _MAX_TABLE_COLS, _MAX_TABLE_ROWS,
    _clean_block, _clean_blocks, _clean_facts, _clean_images, _clean_lines, _clean_meta, _clean_score, _num)


# The closed schema of a pushed payload — fields, caps, the word-boundary clip — lives in `clean.py`; re-exported.
from .clean import (  # noqa: F401,E402 — re-export
    _CRIT_LISTS, _ITEM_FIELDS, _MAX_CRIT, _MAX_CRIT_CHARS, _MAX_DETAIL_CHARS, _MAX_ITEMS, _MAX_PART_LINES,
    _MAX_PARTS, _MAX_REJECTED, _MAX_SOURCES, _MAX_STEP_CHARS, _MAX_STEPS, _MAX_WHY_CHARS, _PART_FIELDS,
    _REJECTED_FIELDS, _SLOT_CLIP_KEYS, _SOURCE_FIELDS, _SOURCE_STATUS, _SUMMARY_NUMS, _SUMMARY_TEXT,
    _clean_criteria, _clean_item, _clean_items, _clean_part, _clean_parts, _clean_rejected, _clean_source,
    _clean_sources, _clean_summary, _clip, _clip_slot)

# ── THE TABS THAT ARE NOT THE LIST ───────────────────────────────────────────────────────────────────────────
# Every tab the widget can show must be here, or its click is not persisted and the next refresh pulls the operator
# back to Results (V2-227 C). «process» is not a tab: an errand's progress lives in the processes panel, never in
# its deliverable; the «proceso» alias makes the `tab` action open that panel (V2-822).
_TABS = ("results", "summary", "sources", "criteria")

#: WHAT KIND OF THING the sheet found — CONTENT, not layout, so it may come from outside; `widget.js::layoutFor`
#: still turns it into a shape. Absent or unknown, the shape of the items decides.
_KINDS = ("product", "place", "media", "photo", "document", "link", "plan")

#: WHICH TEMPLATE the list is drawn with (V2-703, a deliberate exception to `presentation.py` rule 1). The worker
#: sends a NAME from this closed set — never a width, column count or pixel — and `widget.js` refuses one it cannot
#: honour. The worker chooses the SHAPE; the surface owns each slot's geometry.
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


# The live PROCESS (derived from the dispatcher's record) lives in `live.py` (V2-296); re-exported.
from widgets.results.live import (  # noqa: E402,F401 — re-export
    _MAX_PHASES, _MAX_PHASE_CHARS, _browser, _clean_phases, _harvest, _progress)


# The derived fields (`_counts`, `_identity`) and the write that strips them (`_save`) live in `derived.py`.
from .derived import _counts, _identity, _save  # noqa: E402,F401 — re-export


def view_data(q: str = "") -> dict:
    """The LAST result set pushed here, verbatim. Nothing pushed yet → an empty sheet (never invented content).

    `q` is the INSTANCE: the canvas splits `results::<corr>` and hands the suffix over as `q` (V2-259).
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


# ── THE TASK OPENS AND CLOSES THE SHEET (`lifecycle.py`, V2-227 C / V2-530) ─────────────────────────────────────
# The dispatcher's gateways, deliberately NOT actions in `apply_action`: a worker must not decide when the sheet
# opens. Re-exported (`data.begin_task`).
from widgets.results.lifecycle import (  # noqa: E402,F401 — re-export
    begin_task, end_task, rename_task)


# Which item a reference names (`_find`), and what the brain sees (`ref_index`, `prompt_digest`) live in `find.py`;
# `widgets/refs.py` looks the two hooks up HERE by name.
from .find import _find, _named, _sheets_for_brain, prompt_digest, ref_index  # noqa: E402,F401 — re-export

# The prompt digest is pure functions over a sheet dict (`digest.py`, V2-287); `_digest_head`/`_digest_one` are
# re-exported for the surface tests.
from . import digest as _digest                                                              # noqa: E402,F401
from .digest import head as _digest_head, one as _digest_one, _MAX_HEAD_CHARS, _MAX_HEAD_ITEM  # noqa: E402,F401


# The sections merged alongside present/append, and the spoken tab names, live in `merge.py`.
from .merge import _TAB_ALIASES, _merge_sections  # noqa: E402,F401 — re-export


# The action handlers live in `actions.py` (which reads this module) (V2-778 F1-12).
from .actions import (  # noqa: E402,F401
    _a_present, _a_append, _a_clear, _a_choose, _a_detail, _a_list, _a_scroll, _a_layout, _a_tab, _a_sources,
    _a_rejected, _a_progress, _a_criteria, _a_auth_done)


# `apply_action` is a table lookup; the contract gate reads the table's keys (`widgets/validator._table_actions`).


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


# present/append/clear deliver the result set; `choose` PERSISTS the operator's pick; `detail`/`list` flip between
# the grid and one item's dossier. The view lives in the persisted payload so voice drives it.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    # WHICH sheet travels in the payload: the canvas sends actions to the BASE widget and stamps the instance as `q`
    # (`desktop.js`); `sheet` is the explicit name. Read both, or every click on an instance lands on the default
    # sheet (V2-259, V2-540). Neither → the default sheet.
    sheet = _safe_sheet(payload.get("sheet") or payload.get("q"))
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose · detail · "
                                      f"list · tab · sources · progress · criteria · auth_done)"}
    return handler(action, payload, sheet)
