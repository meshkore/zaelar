"""rules/api.py — the HTTP face of the rules table (V2-806), for ⚙ Settings → Rules.

  · `GET    /api/rules`       — every row, grouped by scope: his rows and the factory defaults, each with its source.
  · `PATCH  /api/rules/{id}`  — `{value}` edits a row (a default's edit is a row of his at the same scope and key);
                                `{active}` turns one of his rows on or off.
  · `DELETE /api/rules/{id}`  — removes one of his rows. A default is overridden, never deleted.

A value is checked against its key's declared domain before it is stored — the same check a spoken rule's row
passes (`rules/shape.py`) — so the panel can never write a gate nobody can apply.
"""
from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

router = APIRouter()


def _choices(r: dict) -> list | None:
    """The values a row's key admits, when they are a closed set — what the panel offers as a select."""
    from rules import cascade, shape
    if r["key"] == "consent":
        return list(cascade.GATE_VALUES)
    if r["key"] == "ask_at":
        return list(shape._levels())
    return [True, False] if isinstance(r["value"], bool) else None


def _view(r: dict) -> dict:
    """A row for the panel. `id`, `scope`, `key` and `except` are the panel's handles; what it SHOWS is `label`
    (where it applies), `name` (his words, or what the row sets) and `except_labels` — all in his language."""
    from rules import cascade, labels
    return {**{k: r[k] for k in ("id", "scope", "kind", "key", "value", "except", "source", "text", "created_at",
                                 "active", "until")},
            "label": labels.human(r["scope"]), "name": labels.row_line(r, with_value=False),
            "except_labels": [labels.human(e) for e in r.get("except") or []],
            "live": cascade.live(r), "choices": _choices(r)}


@router.get("/api/rules")
def list_rules() -> dict:
    import rules
    groups: dict[str, list] = {}
    for r in rules.all_rows():
        groups.setdefault(r["scope"], []).append(_view(r))
    order = sorted(groups, key=lambda s: (s != rules.GLOBAL, s.startswith("widget:"), s))
    return {"ok": True, "groups": [{"scope": s, "label": groups[s][0]["label"], "rows": groups[s]} for s in order]}


def _checked(row: dict, value):
    """The value, coerced to the row's key domain; raises ValueError when it does not fit."""
    from rules import cascade, shape, vocabulary
    key = row["key"]
    if key == "consent":
        v = str(value).strip().lower()
        if v not in cascade.GATE_VALUES:
            raise ValueError(f"consent must be one of {', '.join(cascade.GATE_VALUES)}")
        return v
    if key == "ask_at":
        v = str(value).strip().lower()
        if v not in shape._levels():
            raise ValueError("ask_at must be a sensitivity level")
        return v
    if key == cascade.EXCLUDED:
        v = shape._names(value.split(",") if isinstance(value, str) else value)
        if not v:
            raise ValueError("excluded takes one or more names")
        return v
    knobs = vocabulary.knobs()
    if key in knobs:
        v = shape._typed(value, knobs[key])
        if v is None:
            raise ValueError(f"{key} takes a value like {knobs[key]!r}")
        return v
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError("a plain value")
    return value


@router.patch("/api/rules/{rule_id:path}")
def edit_rule(rule_id: str, payload: dict = Body(...)) -> JSONResponse:
    import rules
    row = rules.get(rule_id)
    if not row:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    p = payload or {}
    out = row
    if "value" in p:
        try:
            out = rules.set_value(rule_id, _checked(row, p["value"]))
        except ValueError as e:
            return JSONResponse({"ok": False, "error": "bad_value", "message": str(e)}, status_code=400)
    if "active" in p:
        if row["source"] != "user":
            return JSONResponse({"ok": False, "error": "default_rule"}, status_code=400)
        out = rules.set_active(rule_id, bool(p["active"]))
    return JSONResponse({"ok": True, "rule": _view(out)})


@router.delete("/api/rules/{rule_id:path}")
def delete_rule(rule_id: str) -> JSONResponse:
    import rules
    row = rules.get(rule_id)
    if not row:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    if row["source"] != "user":
        return JSONResponse({"ok": False, "error": "default_rule"}, status_code=400)
    rules.remove(rule_id)
    return JSONResponse({"ok": True, "id": rule_id})
