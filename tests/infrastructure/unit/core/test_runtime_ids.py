"""The process-identity owner behaves like one (F5, 2026-08-23). Companion to the class ratchet in
`test_architecture_ratchet.py::test_process_identity_has_ONE_owner` — that one stops counters being born
elsewhere; this one pins what the owner actually promises."""
import threading

from nucleo import runtime_ids


def test_the_boot_stamp_is_stable_within_the_process():
    assert runtime_ids.boot_id() == runtime_ids.boot_id()
    assert len(runtime_ids.boot_id()) == 6


def test_sequences_are_monotonic_and_independent():
    runtime_ids.reset_seq("t.a"); runtime_ids.reset_seq("t.b")
    assert [runtime_ids.next_seq("t.a") for _ in range(3)] == [1, 2, 3]
    assert runtime_ids.next_seq("t.b") == 1, "counters must not share state across names"


def test_concurrent_callers_never_share_a_value():
    """The counter exists to mint IDENTITY, so a duplicate under contention is the whole failure."""
    runtime_ids.reset_seq("t.c")
    got, n = [], 200
    def take():
        for _ in range(n):
            got.append(runtime_ids.next_seq("t.c"))
    ts = [threading.Thread(target=take) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(set(got)) == 4 * n, "duplicated sequence values under concurrency"


def test_escalate_ids_come_from_the_owner_and_reset_still_works():
    """`escalate.reset()` is a TEST hook and keeps its contract: after it, ids restart at 1. Production never
    rewinds — which is why anything durable keyed on these ids composes `boot_id()` in (dispatch.sheet_id_for)."""
    from nucleo.flash import escalate
    escalate.reset()
    t1 = escalate.escalate_to_slowbrain("busca una cosa concreta")
    assert t1 == 1
    escalate.reset()
    assert escalate.escalate_to_slowbrain("busca otra cosa distinta") == 1


def test_the_sheet_id_composes_the_boot_stamp():
    from nucleo import dispatch
    assert dispatch.sheet_id_for("7") == f"{runtime_ids.boot_id()}-7"
