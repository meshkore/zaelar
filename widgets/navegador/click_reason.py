"""What the click gate SAYS when it stops a click: the reason in his language, and never cut mid-word.

find-direct-flight-budget (EN, 2026-10-14, sandbox 020044-en): a spontaneous ping in an English session read
«Task t1 needs your OK to click «Reload — el destino es una página de com…». Shall I?». Two defects in one line:

  · the gate's REASON was a Spanish literal (`click_gate.decide`), glued to the label and read to him as is;
  · the sentence clipped «label — reason» at 40 characters, so the reason was cut in the middle of a word.

The reasons are the session language's (`i18n.langspec`, `nav_click_why_*`), the label and its reason travel as
two parts of one sentence (`click_needs_ok_why`), and a long label is clipped on a word boundary.
"""
from __future__ import annotations

#: The separator `click_gate.may_act` puts between the button's label and the reason it asks about.
SEP = " — "
#: How much of a button's label is read out. A label is a button's text, a page title at worst: past this it is
#: the site's marketing line, and it is clipped on a word (`clip`).
LABEL_MAX = 60


def _lang():
    from i18n import langs as _lg
    return _lg.current_language()


def why(key: str, **kw) -> str:
    """The gate's reason `key` in the session's language: unreadable · button · secret · payment · checkout."""
    return str(getattr(_lang(), f"nav_click_why_{key}")).format(**kw)


def this_action() -> str:
    """What an unnamed control is called when the page gives it no label."""
    return str(_lang().nav_click_this_action)


def clip(text: str, limit: int = LABEL_MAX) -> str:
    """`text` clipped on a word boundary, with «…» when something was left out — never a mid-word cut."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    sp = cut.rfind(" ")
    if sp >= limit // 2:
        cut = cut[:sp]
    return cut.rstrip(" ,.;:—-") + "…"


def _parts(asked: str) -> tuple[str, str]:
    label, _, reason = str(asked or "").partition(SEP)
    return clip(label), reason.strip()


def needs_ok(task: str, asked: str) -> str:
    """The ping that asks him for the OK: the label (clipped on a word) and, apart, the whole reason."""
    label, reason = _parts(asked)
    lang = _lang()
    if reason:
        return lang.click_needs_ok_why.format(task=task, label=label, why=reason)
    return lang.click_needs_ok.format(task=task, label=label)


def card_question(asked: str) -> str:
    """The question the task's card shows while it waits for his yes or no."""
    label, _reason = _parts(asked)
    return _lang().nav_click_card_question.format(label=label)
