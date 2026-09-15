"""widgets/contract.py — a DESTRUCTIVE action with no selector is REFUSED, never widened (V2-705, Nivel 0).

## The measured incident

2026-09-15 18:03:25, session 878b0122. The operator said «remove the appointment tomorrow at seven — it was
just a test». The fast brain called `agenda.cancel_meeting` with `payload: {}`. The handler read «no title
and no date» as «every meeting», and for each row it called Google: **147 DELETE requests against his real
calendar in sixty seconds, 100 of them accepted**. Locally, every appointment was gone; what came back later
were the 46 rows another calendar re-synced.

It was not the first time. Every `cancel_meeting` the model has ever issued arrived with an empty payload —
3 of 3 in fourteen days (09-12 20:04 «Can you remove the appointment», 09-12 20:07, 09-15 18:03) — and the
manifest declares `title: string` for it. Nothing between the model and the handler read that declaration.

## The rule, and why it lives HERE

`server_api._dispatch` is the SINGLE funnel for every widget mutation — the UI button, the brain's
`widget_data`, the worker's `hbwidget`, cron. So this is the one place a contract can be enforced for all
of them at once, which is what «piensa en global» asks for. The rule is deliberately NARROW:

  · only an action that is DESTRUCTIVE — explicitly `confirm:true`, or NAMED as removing, cancelling,
    deleting, dropping, discarding, disconnecting (a closed verb set in both languages; the name, never the
    description's prose);
  · only when the manifest declares a SELECTOR for it — the key that names WHICH item it acts on
    (`refs.id_field_for_action`, else the first declared payload key, the convention every manifest
    already follows) — and that key is not marked optional;
  · and that selector arrives EMPTY.

Then the action is refused with the same shape every `apply_action` already answers (`ok: False`, a
speakable `message`, a diagnostic `error`), plus the `options` the widget's own `ref_index` lists for that
field, so the next turn can name one. An empty selector on a destructive action means «I did not understand
which one» — it can never mean «all of them». «All of them» has its own actions (`clear_all`, `clear_range`),
each behind a confirm gate.

What this does NOT touch: creations (`add_meeting` with a missing hour is the handler's business), view
actions, whole-wipe actions that declare no selector at all (their friction is the confirm gate), and any
selector the manifest itself calls optional. Measured against fourteen days of events before shipping: the
only data-ops this refuses are the three that emptied the calendar.
"""
from __future__ import annotations

import re

# A closed set: the verbs whose action REMOVES something. Same doctrine as `actions._IRREVERSIBLE_RE` (local
# to the widget layer, never a verb table about intent): it reads the action's NAME, never the operator's
# sentence and — see `is_destructive` — never the description either.
_DESTRUCTIVE_RE = re.compile(
    r"\b(cancel|cancels|remove|removes|delete|deletes|drop|drops|trash|wipe|wipes|forget|forgets|discard|"
    r"discards|unfollow|unsubscribe|disconnect|disconnects|"
    r"cancela|cancelar|elimina|eliminar|borra|borrar|quita|quitar|descarta|descartar|vac[ií]a|vaciar|"
    r"congela|congelar|desconecta|desconectar|olvida|olvidar|papelera)\b",
    re.I,
)

_OPTIONAL_RE = re.compile(r"opcional|optional", re.I)

#: The refusal's machine-readable reason. Stable: tests and the observability line read it.
SELECTOR_MISSING = "selector_missing"

_MAX_OPTIONS = 8


def _spec(widget_id: str, action: str) -> dict:
    try:
        from . import runtime
        return ((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}
    except Exception:  # noqa: BLE001
        return {}


def is_destructive(spec: dict | None, name: str = "") -> bool:
    """Does running this action REMOVE something? Explicit `confirm` counts; a view action never does."""
    spec = spec if isinstance(spec, dict) else {}
    if spec.get("view") is True:
        return False
    if spec.get("confirm") is True or spec.get("irreversible") is True:
        return True
    # The NAME only — never the prose. Measured on the whole catalog the day this shipped: reading the
    # description's own clause dragged in `not_now` («no la quita»), `filter_list` («q vacío quita el
    # filtro»), `create_playlist` («lista vacía») and `read` («quita el no-leído»), none of which removes a
    # thing. An action's name is the contract; its sentence is guidance about it.
    return bool(_DESTRUCTIVE_RE.search(str(name or "").replace("_", " ")))


def selector_for(widget_id: str, action: str, spec: dict | None = None) -> str:
    """The payload key that names WHICH item the action acts on, or "" when the action declares none or
    declares it optional. Read from the manifest, the way `refs` reads it — never guessed from a verb."""
    spec = spec if isinstance(spec, dict) else _spec(widget_id, action)
    payload = spec.get("payload")
    if not isinstance(payload, dict) or not payload:
        return ""
    key = ""
    try:
        from . import refs
        key = str(refs.id_field_for_action(widget_id, action) or "")
    except Exception:  # noqa: BLE001
        key = ""
    if not key or key not in payload:
        key = next(iter(payload))
    if _OPTIONAL_RE.search(str(payload.get(key) or "")):
        return ""
    return key


def _options(widget_id: str, field: str) -> list[str]:
    try:
        from . import refs
        rows = refs._ref_index(widget_id)
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for r in rows or []:
        if str(r.get("field") or "") != field:
            continue
        label = str(r.get("label") or "").strip()
        hint = str(r.get("hint") or "").strip()
        if label:
            out.append(f"{label} ({hint})" if hint else label)
        if len(out) >= _MAX_OPTIONS:
            break
    return out


def _spoken(menu: str) -> str:
    """The refusal the operator HEARS, from the language table (the `agenda._spoken` shape, V2-689)."""
    field = "widget_selector_missing" if menu else "widget_selector_missing_bare"
    try:
        from i18n import langs as _langs
        text = str(getattr(_langs.spec(), field, "") or "")
    except Exception:  # noqa: BLE001
        text = ""
    if not text:
        try:
            from dataclasses import fields as _fields
            from i18n.langs import LangSpec as _LS
            text = str(next(f.default for f in _fields(_LS) if f.name == field))
        except Exception:  # noqa: BLE001
            text = "?"
    return text.replace("{options}", menu)


def guard(widget_id: str, action: str, payload: dict | None) -> dict | None:
    """The refusal for this call, or None when the call may proceed. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        act = str(action or "").strip()
        spec = _spec(wid, act)
        if not spec or not is_destructive(spec, act):
            return None
        field = selector_for(wid, act, spec)
        if not field:
            return None
        pl = payload if isinstance(payload, dict) else {}
        if str(pl.get(field) if pl.get(field) is not None else "").strip():
            return None
        options = _options(wid, field)
        menu = ("; ".join(options[:5])) if options else ""
        return {
            "ok": False,
            "error": SELECTOR_MISSING,
            "field": field,
            "widget": wid,
            "action": act,
            "options": options,
            # `message` is the speakable half (data_ops.report_failure voices it) and comes from the language
            # table, never from a string written here (V2-676/V2-689); `error` is the diagnostic the model reads.
            "message": _spoken(menu),
            "detail": (f"`{act}` on `{wid}` needs `{field}` and it arrived empty — an empty selector never "
                       f"means «all of them»; ask which one" + (f" (options: {menu})" if menu else "") + "."),
        }
    except Exception:  # noqa: BLE001
        return None
