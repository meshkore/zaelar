"""Deterministic handles on pills: the memory clock, canonical slots and their value at a past instant (`as_of`),
the text anchors `[widget:<id>]` / `[task:<id>]`, and the pills a same-conversation correction may reach."""
from .. import db as _db
from .. import writer as _writer
from ..clock import now as _clock_now


def now() -> int:
    """The memory's clock, THROUGH the facade — never `time.time()` in a caller.

    `memory/clock.py` supports `travel()` so the timeline corpus can replay simulated days; a caller reading the
    wall clock would date its pills wrongly. Re-exported so no caller reaches into a memory internal."""
    return _clock_now()


def canon_slot(slot: str | None) -> str | None:
    """The canonical key for a slot name/alias, THROUGH the facade. Re-exported (not reimplemented): the registry
    in `memory/slots.py` stays the single vocabulary; this only spares callers a direct reach into the writer."""
    return _writer.canon_slot(slot)


def as_of(slot: str, ts: int | None = None) -> dict | None:
    """Bi-temporal (V2-111 §9.2): the value a canonical slot had at a PAST instant — which `updated` cannot answer
    (reinforcement and level promotion touch it too). Returns the newest row whose `valid_at` had arrived at `ts`
    and that was not yet invalidated at `ts`. `None` if the slot did not exist yet or is not a recognised
    canonical key — never raises, never invents a value.

    `ts=None` means NOW. The clock is the memory's business: a mandatory `ts` pushed every caller to import
    `memory.clock` across the boundary."""
    if ts is None:
        ts = _clock_now()
    canon = _writer.canon_slot(slot)
    if not canon:
        return None
    db = _db.get_db()
    keys = []
    try:
        from .. import slots as _slots
        keys = list(_slots.equivalent_keys(canon) or [canon])
    except Exception:
        keys = [canon]
    ph = ",".join("?" * len(keys))
    row = db.query_one(
        f"SELECT id, level, kind, text, importance, weight, slot, meta, created, updated, valid_at, "
        f"invalidated_at FROM memories WHERE slot IN ({ph}) AND valid_at <= ? "
        f"AND (invalidated_at IS NULL OR invalidated_at > ?) ORDER BY valid_at DESC, id DESC LIMIT 1",
        (*keys, ts, ts),
    )
    return dict(row) if row is not None else None


def correction_targets(window_s: float = 2700.0, limit: int = 6) -> list[dict]:
    """The durable SLOTLESS pills a same-conversation correction may reach (V2-565): id + text, newest first.

    Two consumers, deliberately one function so they cannot drift: the distiller is OFFERED these (it cannot
    correct what it never sees), and the memory agent uses the same list as the WHITELIST for the model's
    `supersedes` answer, so the model can only name ids it was shown.

    Slotless only: slotted facts already have exact supersede, and keeping identity/state out of this path is what
    makes it safe to let the model aim. The window is the practical «this conversation». `created`, not
    `updated`: decay and reinforcement touch `updated`. Clock via `now()` (clock.travel)."""
    db = _db.get_db()
    since = now() - float(window_s)
    rows = db.query(
        "SELECT id, text FROM memories WHERE valid=1 AND slot IS NULL AND level IN ('mid','long') "
        "AND kind NOT IN ('conv') AND created >= ? "
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        "ORDER BY created DESC, id DESC LIMIT ?", (since, int(limit)))
    return [{"id": int(r["id"]), "text": r["text"]} for r in rows]


def widget_trace_ids(widget_id: str, limit: int = 4) -> list[int]:
    """The valid pills anchored to a widget — ids of `[widget:<id>]`-prefixed rows, newest first (V2-577).

    One consumer, `widgets/lifecycle.py`: each lifecycle transition writes its own `[widget:<id>]` pill and passes
    THIS list as `supersedes`, so only the newest chapter stays valid and recall never serves a birth announcement
    beside its own tombstone. Capped to the writer's supersede cap; the chain keeps the valid set at ~1."""
    return _anchored_ids("widget", widget_id, limit)


def task_trace_ids(task_id: str, limit: int = 4) -> list[int]:
    """The valid pills anchored to a TASK — ids of `[task:<id>]`-prefixed rows, newest first (V2-728).

    Same door, same reason as `widget_trace_ids`: a commission can close more than once (a relay, a re-dispatch),
    and without the supersede chain recall serves «found nothing» next to «found 5 flats» for the same errand."""
    return _anchored_ids("task", task_id, limit)


def _anchored_ids(prefix: str, ref: str, limit: int) -> list[int]:
    """Valid pills whose text opens with `[<prefix>:<ref>]`, newest first.

    ONE implementation for both anchors: two copies of a LIKE-escape rule are two chances to escape it
    differently. Matching is by the TEXT PREFIX, the only deterministic handle those pills carry — matching by
    content invents targets. `_` is escaped (a LIKE wildcard that is also a legal slug character)."""
    r = (ref or "").strip().lower()
    if not r:
        return []
    db = _db.get_db()
    esc = r.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = db.query(
        "SELECT id FROM memories WHERE valid=1 AND slot IS NULL AND kind != 'conv' "
        "AND text LIKE ? ESCAPE '\\' ORDER BY created DESC, id DESC LIMIT ?",
        (f"[{prefix}:{esc}]%", int(limit)))
    return [int(r0["id"]) for r0 in rows]
