"""V2-219 — the worker died in OUR OWN CLI's arity, twice, in cases with nothing to do with each other.

Measured 2026-08-20 by the use-case harness:

  `hotel-under-15-days`   Exit code 2 usage: worker_bridge [-h] {ask,wait,act,say} … the following arguments
                          are required
  `hotel-under-15-days`   Exit code 2 nav_cli scroll: error: argument dy: invalid int value: 'down'
  (the Bilbao round)      the same `scroll down`, three more times

Consequence in the same round: `n_search_events: 0`. Not one search in the whole run — the worker died in its
own arguments before reaching the web, and the turn went on saying it was working.

Two different faults with one shape. `scroll down` is the CLI being wrong: every other tool a worker has ever
driven takes a direction there, its own manual says `scroll 800` so it KNOWS the syntax and does not use it,
and it wrote the natural thing four times across two unrelated cases. `worker_bridge act` with no payload is
the worker being wrong, and there the fix is not to accept it but to say how it is written — the same contract
as node 4.20: what the bridge knows, it says, and a failure also says how to get out of it.

That second half matters most HERE of all the bridges: `worker_bridge` is how a worker ASKS for a search, so
dying in its arguments leaves it blind for the rest of the task.
"""
import subprocess
import sys

import pytest

from nucleo import nav_cli, worker_bridge


# ── the CLI was wrong: a direction is a legitimate way to write it ────────────────────────────────────────────
@pytest.mark.parametrize("word,sign", [("down", 1), ("abajo", 1), ("up", -1), ("arriba", -1)])
def test_the_measured_word_is_accepted(word, sign):
    px = nav_cli._scroll_amount(word)
    assert px * sign > 0, f"«{word}» debería moverse en ese sentido"
    assert abs(px) == nav_cli._SCROLL_STEP


def test_a_number_still_means_exactly_that_number():
    """Sensitivity: accepting the word must not turn the pixel argument into an approximation. A worker that
    measured a distance on the capture and asks for 240 gets 240."""
    assert nav_cli._scroll_amount("240") == 240
    assert nav_cli._scroll_amount("-1500") == -1500


def test_nonsense_still_fails_AND_says_both_ways_to_write_it():
    """Widening the input must not become «accept anything»: an unreadable value is still an error. What
    changes is that the error carries the two forms instead of `invalid int value`."""
    import argparse
    with pytest.raises(argparse.ArgumentTypeError) as e:
        nav_cli._scroll_amount("perro")
    msg = str(e.value)
    assert "scroll 800" in msg and "scroll down" in msg


def test_the_whole_command_runs_end_to_end():
    """`_scroll_amount` being right is not the same as it being WIRED: the parser has to use it as the type.
    Run the real CLI — with no server it fails on the connection, never on the argument."""
    out = subprocess.run([sys.executable, "-m", "nucleo.nav_cli", "scroll", "down"],
                         capture_output=True, text=True, timeout=60)
    assert "invalid int value" not in (out.stdout + out.stderr)


# ── the worker was wrong: the failure says how it is written ─────────────────────────────────────────────────
def test_act_names_the_search_call_verbatim():
    """The commonest use and the one that was lost: the hint carries a line the worker can copy, not a
    description of a line."""
    h = worker_bridge._hint_for("worker_bridge act")
    assert "use_tool" in h and '"tool":"web_search"' in h


@pytest.mark.parametrize("sub", ["ask", "say", "wait"])
def test_every_subcommand_has_its_own_way_out(sub):
    h = worker_bridge._hint_for(f"worker_bridge {sub}")
    assert h.strip(), sub
    assert sub in h


def test_an_unknown_prog_still_says_something_useful():
    """Fail-open on the hint itself: a subcommand added tomorrow gets the general rule instead of silence."""
    h = worker_bridge._hint_for("worker_bridge algo-nuevo")
    assert "ask" in h and "act" in h


def test_the_bridge_prints_the_hint_when_the_argument_is_missing():
    """The measured failure, end to end. Asserted on the real process because the whole point is what reaches
    the worker's stderr — a hint that exists and is not printed is V2-186 again."""
    out = subprocess.run([sys.executable, "-m", "nucleo.worker_bridge", "act"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 2
    err = out.stderr
    assert "the following arguments are required" in err      # the complaint is KEPT
    assert "use_tool" in err                                   # …and now it says what to do
    assert "usage:" in err                                     # …and the form is still there


def test_the_hint_lands_BETWEEN_the_complaint_and_the_usage():
    """A worker reads top-down: the way out has to arrive before the wall of syntax it is already staring at."""
    out = subprocess.run([sys.executable, "-m", "nucleo.worker_bridge", "act"],
                         capture_output=True, text=True, timeout=60)
    err = out.stderr
    assert err.index("required") < err.index("use_tool") < err.index("usage:")
