#
# A deliberate RESET opens a NEW WORK SESSION (operator request, 2026-08-10).
#
# “It is as if we stopped the agent and started it again while keeping the same rules we already had, but
# observability has to be reset to zero because it is a new session starting blank, with a new id.”
#
# What was failing: the reset emptied the log (`clear_log`) but did NOT rotate the id — nobody called
# `identity.begin_session(force=True)`. So subsequent events remained attached to the old session: the durable
# record mixed the work from before and after a reset into the same session, and the observability column
# started “empty” but with the identity of something that no longer existed.
#
# NOTE what must NOT change: `begin_session` deliberately reuses the open session, so that a reconnection
# caused by a network hiccup is not counted as a new session (splitting it in two would falsify “how long it lasted
# and what it did”). Rotation is ONLY for the deliberate reset, which is why it needs `force=True`.
#
import bus as busmod
import pytest

from observability import identity
from voice import observer, trace


#: The REAL closer, captured at import. Two tests in this file monkeypatch `identity.end_session` to raise on
#: purpose (that is their subject: a reset must survive a failing close), and the autouse fixture below cleans up
#: with the same function — so whether the fixture exploded came down to pytest's teardown ORDER between it and
#: the `monkeypatch` fixture, which a change anywhere in the conftest chain can flip. It flipped on 2026-08-23 and
#: turned a passing test into a suite-wide red with `RuntimeError: simulado` raised from teardown. A fixture's job
#: is to clean up; it must not be defeatable by what the test under it patches.
_END_SESSION = identity.end_session


@pytest.fixture(autouse=True)
def _clean():
    busmod.reset()
    _END_SESSION("test")
    observer.clear_log()
    yield
    busmod.reset()
    _END_SESSION("test")
    observer.clear_log()


def test_reset_mints_a_new_session_id():
    before = identity.session_id()
    assert before, "debería haber una sesión abierta (se abre sola en el primer uso)"
    info = observer.rotate_session("reset")
    assert info.get("session_id"), "la rotación tiene que devolver la sesión nueva"
    assert info["session_id"] != before, "el id TIENE que cambiar: es lo que hace que el borrón signifique algo"
    assert identity.session_id() == info["session_id"], "y ser la sesión en curso a partir de ahora"


def test_the_public_shape_is_session_id_not_the_internal_id():
    """The caller of this (the reset response, the RESET event read by the frontend) speaks `session_id`.
    `begin_session` returns the internal key `id` — returning it as-is left the field empty in the event."""
    info = observer.rotate_session("reset")
    assert "session_id" in info and "id" not in info


def test_observability_starts_from_zero():
    observer.emit("test", "viejo", text="un evento de la sesión anterior")
    observer.emit("test", "viejo2", text="otro")
    assert len(observer._events) >= 2
    observer.rotate_session("reset")
    # Only what the new session ITSELF emitted when it was created (its session/start) may remain, never anything from before.
    assert not any((e.get("label") or "").startswith("viejo") for e in observer._events), \
        "un evento de la sesión anterior sobreviviendo al reset es exactamente lo que se venía a arreglar"
    assert observer._seq["n"] <= 1, "el contador de secuencia empieza de nuevo"


def test_the_event_ring_carries_the_new_session_id_afterwards():
    """The detail that motivated all this: emptying is not enough; anything emitted AFTERWARD must carry the new id."""
    info = observer.rotate_session("reset")
    ev = observer.emit("test", "nuevo", text="primer evento de la sesión nueva")
    assert ev.get("sid") == info["session_id"]


def test_dedup_state_cannot_swallow_the_first_event_of_the_new_session():
    """`_dedup` collapses bursts by (kind,label). With stale entries, the first event of a new session could
    collapse against one from the previous session and NOT appear — the session would start too blank."""
    observer.emit("test", "repetido", text="uno")
    observer.rotate_session("reset")
    assert observer._dedup == {}


def test_traces_are_numbered_from_one_again():
    """A session that starts blank cannot open at “T34”: that tells the operator they are looking at the
    continuation of something."""
    trace.begin("una frase de la sesión vieja")
    trace.begin("otra")
    observer.rotate_session("reset")
    tid = trace.begin("primera frase de la sesión nueva")
    assert tid.startswith("T1·"), f"debería reiniciar la numeración, y dio {tid}"


def test_the_per_session_file_follows_the_new_session():
    """The per-session file path is memoized. Without invalidating it, events from the new session would be written
    to the file belonging to the one that has just closed."""
    old = observer.session_info()["file"]
    info = observer.rotate_session("reset")
    new = observer.session_info()["file"]
    assert new != old
    assert info["session_id"] in new


def test_a_plain_reconnect_is_still_not_a_new_session():
    """Counterpoint: without `force`, `begin_session` reuses the open session. If this broke, every network hiccup
    would split the session in two and distort the entire duration analysis."""
    sid = identity.session_id()
    again = identity.begin_session(source="frontend")
    assert again["id"] == sid


def test_the_log_is_cleared_even_if_closing_the_old_session_fails(monkeypatch):
    """A half-completed reset is bad; a reset that crashes is worse: the operator is left unable to reset. If closing
    the old session fails, proceed: clear the log and open the new one anyway."""
    def boom(*a, **k):
        raise RuntimeError("simulado")

    observer.emit("test", "algo", text="x")
    monkeypatch.setattr(identity, "end_session", boom)
    info = observer.rotate_session("reset")
    assert all((e.get("label") or "") != "algo" for e in observer._events), "el log se limpia igual"
    assert info.get("session_id"), "y la sesión nueva se abre igual"


def test_rotation_returns_empty_instead_of_raising_if_the_new_session_cannot_open(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulado")

    observer.emit("test", "algo", text="x")
    monkeypatch.setattr(identity, "begin_session", boom)
    info = observer.rotate_session("reset")
    assert info == {}                        # there is no new session to announce…
    assert all((e.get("label") or "") != "algo" for e in observer._events)   # …but the reset WAS performed
