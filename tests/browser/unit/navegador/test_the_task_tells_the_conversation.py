
from nucleo.events import task_event  # noqa: E402 — the matters a task was told (V2-851 F4)
"""V2-215 — the wall and the question were recorded everywhere and said nowhere.

Measured 2026-08-20 by the use-case harness, reading the task registry of two rounds:

  · `cancel-subscription-before-charge__es` (16:34) → status="working", wall="la página pidió resolver un
    captcha", phase_active=false, walls_hit=1 — and the turn still narrating that the cancellation was going
    ahead.
  · `find-theatre-tickets__es` (16:26) → status="needs_input", question="Voy a pulsar «COMPRAR ENTRADAS».
    ¿Lo confirmo?", walls_hit=2 — asked at 16:22:18, and at 16:24:45 the worker moved on without an answer.
  · brain-notes in BOTH rounds: 0.

`_announce_wall` does three things and every one of them lands on a surface the operator has to be LOOKING at:
a milestone in the card's feed, the phase with its spinner off, and the card opened. `ask()` does less — the
card's feed and nothing else. `active_progress()` does carry both into the prompt (V2-202/V2-207), but that
only helps when the operator ASKS how it is going; if he says nothing, nothing reaches him.

So the missing half is a note that enters the NEXT turn on its own. It is the seam a FINISHED task has used
since the browser-agent work (`owner.py`), for the same reason: a fact the operator can act on has to arrive by itself.

Since V2-851 F4 the matter goes to its task (`nucleo.events.task_event.told`), and F5 removed the notes mailbox.
"""
import pytest

from widgets.navegador import tasks


@pytest.fixture(autouse=True)
def _clean():
    """The registry is module-level and the mailbox is process-level: both are shared state, so a test that
    leaves either dirty writes the next one's result."""
    task_event.drain()
    tasks._tasks.clear()
    yield
    task_event.drain()
    tasks._tasks.clear()


def _wall(goal="resérvame mesa esta noche en Casa Lucio"):
    tid = tasks.create(goal)
    tasks.update_view(tid, url="https://www.netflix.com/es/login", page_title="t",
                      page_text="Please verify you are human")
    return tid


def test_a_wall_reaches_the_conversation():
    tid = _wall()
    notes = task_event.drain()
    assert len(notes) == 1, "the wall never entered the conversation"
    n = notes[0]
    assert tid                       # the matter is keyed by its task (`nav:<id>:wall`, V2-851 F4)
    assert "blocked" in n            # what happened


def test_the_wall_note_carries_the_REASON_and_a_way_out():
    """“It is blocked” is a diagnosis. What the operator can act on is WHY and WHAT NOW — the same lesson the
    four bridges learned today, applied to the one reader who is a person."""
    _wall()
    n = task_event.drain()[0]
    assert "verificación anti-robot" in n or "captcha" in n or "robot" in n
    assert "another site" in n and "leave it" in n


def test_it_does_NOT_promise_the_task_will_finish_by_itself():
    """V2-185: the reassuring half is FALSE in front of a wall, and it is what kept the operator waiting."""
    _wall()
    n = task_event.drain()[0]
    assert "will not finish by itself" in n.lower()
    # V2-835: one instruction per note — the FACT («it will not finish by itself») is what rules the reassurance out;
    # the note no longer adds a second order naming the phrase to avoid.
    assert "sigue" not in n.split("—", 1)[-1].lower().replace("no va a terminar sola", "")


def test_an_ordinary_page_says_NOTHING():
    """Sensitivity, and the one that matters most: this hangs off `update_view`, which fires on EVERY capture.
    A note per screenshot would bury the conversation in system text."""
    tid = tasks.create("busca una guitarra")
    tasks.update_view(tid, url="https://www.wallapop.com/search?keywords=guitarra", page_title="ok",
                      page_text="Resultados de tu búsqueda")
    assert task_event.drain() == []


def test_the_SAME_wall_is_announced_ONCE():
    """`_announce_wall` only fires when the wall CHANGES, and that guard is what makes this safe: a task parked
    on a challenge page re-captures every few seconds."""
    tid = _wall()
    assert len(task_event.drain()) == 1
    for _ in range(3):
        tasks.update_view(tid, url="https://www.netflix.com/es/login", page_title="t",
                          page_text="Please verify you are human")
    assert task_event.drain() == []


def test_a_question_reaches_the_conversation():
    tid = tasks.create("compra dos entradas para El Rey León")
    tasks.ask(tid, "Voy a pulsar «COMPRAR ENTRADAS». ¿Lo confirmo? (dime sí o no)")
    notes = task_event.drain()
    assert len(notes) == 1, "a question nobody is asked is not a question"
    n = notes[0]
    assert "COMPRAR ENTRADAS" in n, "the question has to travel VERBATIM — the operator answers THIS, not a summary"
    assert "El Rey León" in n, "with several tasks alive, a question that does not name its own is unanswerable"



def test_answering_announces_NOTHING():
    """The answer is the operator's own turn — telling him what he just said is noise."""
    tid = tasks.create("compra dos entradas")
    tasks.ask(tid, "¿Lo confirmo?")
    task_event.drain()
    tasks.answer(tid, "sí")
    assert task_event.drain() == []


def test_neither_announcement_can_break_the_task(monkeypatch):
    """Both live inside the registry, which is on the browser's own path. A task-event door that raises must not
    take a running task with it — same fail-open contract as every other emit here."""
    monkeypatch.setattr(task_event, "told", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    tid = _wall()
    tasks.ask(tid, "¿sigo?")
    assert tasks.get(tid)["status"] == "needs_input"   # the task is intact
    assert tasks.get(tid)["question"] == "¿sigo?"
