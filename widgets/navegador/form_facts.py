"""widgets/navegador/form_facts.py — a form that needs HIS data asks for the DATUM, once, in his language.

Measured in `rental-car-automatic-airport` (2026-10-11, ES and EN). A search form on DiscoverCars matched the
identity-field signals, `click_gate.needs_facts` said name · email · phone were missing, and the gate handed the
sentence «Para rellenar este formulario me falta tu nombre, tu email, tu teléfono» to `owner._confirm` — the
yes/no APPROVAL ask for an irreversible click. `_confirm` wraps whatever it gets as the label of a button:

    «Task 2 needs your OK to click «Para rellenar este formulario me falta t». Shall I?»

Three defects in one line, all from routing a request for data through the door for consent: the sentence was cut
at 40 characters as if it were a button label, it asked for an OK nobody could usefully give (a «yes» fills
nothing), and every retry of the click (three in the EN round) sent the same ping again — and waited 60 s each time
for an answer the gate then ignored. The Spanish text also reached the English operator, because it never went
through the language table.

The datum ask is its own act: a proactive note naming WHAT is missing, sent once per task and set of facts, with
no wait — the worker gets the refusal back at once and decides whether the errand even needs that form.
"""
from __future__ import annotations

#: (task id, missing facts) already asked. Process-lived: a restart may ask once more, which is the safe side.
_ASKED: set[tuple[str, tuple[str, ...]]] = set()


def sentence(task_id: str, missing: list[str]) -> str:
    """The note he reads: the task, and each missing datum by its name in his language."""
    from i18n import langs as _lg
    lang = _lg.current_language()
    names = dict(lang.form_fact_names)
    said = [names.get(m, m) for m in missing if m]
    if len(said) > 1:
        facts = ", ".join(said[:-1]) + f" {lang.receipt_and} " + said[-1]
    else:
        facts = "".join(said)
    return lang.form_needs_facts.format(task=task_id, facts=facts)


async def ask_once(task_id: str, missing: list[str]) -> bool:
    """Tell him which of his data this form needs. True when a note went out, False when it was already asked
    (same task, same facts) or there is nothing to ask. Never waits for the answer: the answer lands in memory
    through the normal turn, and the next attempt at the form reads it from there."""
    key = (str(task_id or ""), tuple(sorted(m for m in (missing or []) if m)))
    if not key[1] or key in _ASKED:
        return False
    _ASKED.add(key)
    try:
        from voice import proactive
        await proactive.notify("navegador", sentence(key[0], list(missing)), kind="notify")
    except Exception as e:  # noqa: BLE001 — a note that cannot go out must not break the click path
        try:
            from voice.observer import emit
            emit("widget", "form_facts: note not sent", text=f"{type(e).__name__}: {e}"[:160],
                 extra={"id": "navegador", "task": key[0]})
        except Exception:  # noqa: BLE001
            return False
    return True


def forget() -> None:
    _ASKED.clear()
