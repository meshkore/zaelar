"""The assistant's own names inside an inferred end state: a vocative is never what an errand is about (V2-807 T-16).

Split out of `spec.py` by concern (V2-852): the end-state grammar stays there, the names it must ignore live here."""
from __future__ import annotations


def _assistant_names() -> set[str]:
    """Every name the assistant answers to, normalized (the attention gate's own list)."""
    try:
        from nucleo.flash import presence as _presence
        return {n for n in _presence.assistant_names() if n}
    except Exception:  # noqa: BLE001
        return set()


def _without_the_assistants_name(done_when: dict) -> dict | None:
    """A term that is only the assistant's NAME is how he addressed us, never what the errand is about (V2-807 T-16).

    «…and, <assistant name>, I want it synced in real time» was inferred as `mensajeria.items[title~=<name>]` — the vocative
    became the goal, the check could never pass, and the worker was told for seven minutes that a row titled with
    the assistant's name was still missing. A `where` term or a `has` value equal to a name the assistant answers
    to is removed; a clause left with nothing to look for goes; nothing left → None (honestly unverifiable)."""
    names = _assistant_names()
    if not names:
        return done_when
    from nucleo.circuit import verify as _verify
    from nucleo.flash import presence as _presence

    def _is_name(v) -> bool:
        return isinstance(v, str) and _presence._norm(v) in names

    mode, clauses = _verify._clauses(done_when)
    kept: list[dict] = []
    for c in clauses:
        c = dict(c)
        if isinstance(c.get("where"), dict):
            where = {k: v for k, v in c["where"].items() if not _is_name(v)}
            if c["where"] and not where:
                continue
            c["where"] = where
        if _is_name(c.get("has")):
            continue
        kept.append(c)
    return {mode or "all": kept} if kept else None
