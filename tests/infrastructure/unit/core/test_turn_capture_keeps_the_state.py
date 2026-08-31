"""The forensic capture of a turn must preserve the part that CHANGES (V2-195).

`observer.turn_detail` exists to answer “what did the model see?”—its own docstring says: “why did it
re-escalate during an ambient turn? = look at which window/prompt it saw.” And it was saving `system[:8000]`
from a prompt measuring ~19,000 characters.

The static persona comes first and **`prompt.live_state()` is composed at the END**, so what got cut was
exactly the half that changes every turn: the time, background tasks, the browser block, a wall, a pending
confirmation.

On 2026-08-20, that truncation made five turns from a measured run appear never to have the browser block—
while the browser emitted 74 events in that same run. Three steps into concluding that an entire night of
fixes was invisible to the model, when the only thing missing was the artifact. A diagnosis that truncates
the very evidence it is asked for is worse than having none: it looks like an answer.
"""
from __future__ import annotations

from voice import observer


def _prompt(head: str = "PERSONA", tail: str = "ESTADO", filler: int = 30_000) -> str:
    return head + ("x" * filler) + tail


def test_the_TAIL_survives_because_that_is_where_the_live_state_goes():
    ex = observer._prompt_excerpt(_prompt())
    assert ex.endswith("ESTADO")


def test_and_the_head_too_because_the_rules_live_there():
    assert observer._prompt_excerpt(_prompt()).startswith("PERSONA")


def test_and_the_gap_is_NAMED_so_a_hole_is_not_read_as_an_absence():
    """That is the entire lesson of the finding: I read a gap as an absence. If the excerpt says how much is
    missing and where the state is, nobody else will make that mistake."""
    ex = observer._prompt_excerpt(_prompt())
    assert "OMITIDOS" in ex and "el estado vivo va al final" in ex


def test_a_short_prompt_is_kept_whole():
    assert observer._prompt_excerpt("corto") == "corto"


def test_and_a_REAL_turn_keeps_its_browser_block():
    """The check that matters, using the real prompt rather than filler."""
    from nucleo.flash import prompt as _p
    from widgets.navegador import tasks

    tasks._tasks.clear()
    tid = tasks.create("Reservar noche en el hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="chrome-error://chromewebdata/")
    try:
        system, _ = _p.build_flash_system(turn_text="¿lo tienes ya?")
        ex = observer._prompt_excerpt(system)
        assert "NAVEGADOR" in ex
        assert "· MURO: " in ex
    finally:
        tasks._tasks.clear()
