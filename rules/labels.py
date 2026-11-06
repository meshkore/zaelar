"""rules/labels.py — a scope in the person's own words (V2-806).

He never sees a scope, a key or an id: he says his rules and the system files them. Wherever a rule is SHOWN to
him (⚙ Settings → Rules, a spoken «these are your rules») its place is named from declared data, in his language:

  · `global` → «In general»; `voice` → «How it talks to you»            (i18n `rules.scope.*`)
  · a domain → «Messages», «Calendar», «Payments»…                     (i18n `rules.scope.d.<domain>`)
  · a channel → its catalog name («Email», «WhatsApp»), or the i18n name when one exists (`rules.scope.c.<id>`)
  · an act → «send new messages», «answer automatically»…              (i18n `rules.scope.a.<act>`)
  · a card → its own name (`widgets.<id>.name`, else the manifest's `title`)
  · an item → «one specific thing»

A part nobody named in his language is never printed raw: it falls back to its parent's words. Only the model's
own line (`rules/prompt.gate_line`) keeps technical scopes.
"""
from __future__ import annotations

from . import scope as _scope


def _t(key: str, default: str = "") -> str:
    try:
        from i18n import runtime as _rt
        return _rt.text(key, default)
    except Exception as e:  # noqa: BLE001 — no language table: the declared default stands
        import logging
        logging.getLogger("zaelar.rules").info(f"rules.labels: i18n unreadable ({e})")
        return default


def _channel(cid: str) -> str:
    named = _t(f"rules.scope.c.{cid}")
    if named:
        return named
    try:
        from connectors import catalog
        m = next((m for m in catalog.load_manifests() if str(m.get("id")).lower() == cid), None)
        return str((m or {}).get("label") or "")
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.rules").info(f"rules.labels: catalog unreadable ({e})")
        return ""


def _person(contact_id: str) -> str:
    """The name of one person of his directory, by id ("" when unknown)."""
    try:
        from widgets.contactos import data as _cd
        return str(next((c.get("name") for c in _cd.load_db().get("contacts", []) if str(c.get("id")) == contact_id), "") or "")
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.rules").info(f"rules.labels: directory unreadable ({e})")
        return ""


def _widget(wid: str) -> str:
    named = _t(f"widgets.{wid}.name")
    if named:
        return named
    try:
        from widgets import runtime
        return str((runtime.get(wid) or {}).get("title") or "")
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.rules").info(f"rules.labels: widget catalog unreadable ({e})")
        return ""


def human(scope: str) -> str:
    """The scope as he reads it. Never a raw scope, key or id."""
    sc = _scope.norm(scope)
    general = _t("rules.scope.global", "In general")
    if sc == _scope.GLOBAL:
        return general
    if sc == _scope.VOICE:
        return _t("rules.scope.voice", "How it talks to you")
    if sc.startswith("item:"):
        return _t("rules.scope.item", "One specific thing")
    if sc.startswith("subject:"):
        sid, _, tail = sc[len("subject:"):].partition("/")
        who = _t("rules.scope.subject", "With {name}").replace("{name}", _person(sid) or sid)
        segs = tail.split("/") if tail else []
        doing = _t(f"rules.scope.a.{segs[2]}") if len(segs) > 2 else ""
        where = _channel(segs[1]) if len(segs) > 1 and segs[1] != _scope.ANY else ""
        return " · ".join(x for x in (who, where, doing) if x)
    if sc.startswith("widget:"):
        wid, _, act = sc[len("widget:"):].partition("/")
        card = _widget(wid) or _t("rules.scope.card", "A card")
        doing = _t(f"rules.scope.a.{act}") if act else ""
        return f"{card} · {doing}" if doing else card
    segs = sc.split("/")
    domain = _t(f"rules.scope.d.{segs[0]}") or general
    where = _channel(segs[1]) if len(segs) > 1 and segs[1] != _scope.ANY else ""
    doing = _t(f"rules.scope.a.{segs[2]}") if len(segs) > 2 else ""
    head = where or domain
    return f"{head} · {doing}" if doing else head


def row_line(row: dict, *, with_value: bool = True) -> str:
    """One row as he reads it: his own words; a row he never worded (a default, an edit in Settings) is named by
    what it sets and its value, in his language — never by its key or id."""
    text = str(row.get("text") or "").strip()
    if text:
        return text
    if row.get("key") == "note":
        return str(row.get("value") or "").strip()
    what = _t(f"config.rules.k.{row.get('key')}") or human(row.get("scope") or "")
    if not with_value:
        return what
    v = row.get("value")
    said = _t(f"config.rules.v.{str(v).lower()}") or (str(v) if isinstance(v, (int, float)) else "")
    return f"{what}: {said}" if said else what


def grouped_line(rows: list[dict]) -> str:
    """His rows grouped by where they apply, as one spoken line: «Email · send new messages: ask me first. …»."""
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(human(r.get("scope") or ""), []).append(row_line(r))
    if not groups:
        return _t("rules.listing.none", "")
    return " ".join(f"{where}: {'; '.join(dict.fromkeys(lines))}." for where, lines in groups.items())
