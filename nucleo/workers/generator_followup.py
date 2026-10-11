"""What he says to a widget build WHILE it runs is applied to the widget it built — never dropped.

three-tasks-at-once (2026-10-11 11:34, ES and EN). The platform game was building (a one-shot `generate_widget`
call of up to eight minutes) when he said «make the jump higher» and «add coins». The turn sent them with
`send_to_worker`; the session queued them; and `GeneratorBackend.send` was `return` — «an atomic build does not
accept mid-turn injection». The game came out with neither, while the replies said «passing the higher, floatier
jump to the game build». A build cannot be re-opened mid-call, but its RESULT can be modified the moment it exists:
every message that arrived during the build becomes ONE `modify_widget` pass on the widget just created.
"""
from __future__ import annotations

#: Messages beyond this are folded anyway; the cap only bounds the instruction's length.
_MAX_CHARS = 1500


def instruction(messages: list[str]) -> str:
    """The modify request for the messages that arrived while the widget was being built ("" when none)."""
    msgs = [" ".join(str(m or "").split()) for m in messages or []]
    msgs = [m for m in msgs if m]
    if not msgs:
        return ""
    body = "\n".join(f"- {m}" for m in msgs)[:_MAX_CHARS]
    return ("Apply these changes the operator asked for while this widget was being built, keeping everything "
            f"that already works:\n{body}")


def summary_tail(applied: bool) -> str:
    """The sentence the result summary carries about those changes, in the session's language."""
    from i18n import langs as _lg
    lang = _lg.current_language()
    return lang.widget_changes_applied if applied else lang.widget_changes_not_applied
