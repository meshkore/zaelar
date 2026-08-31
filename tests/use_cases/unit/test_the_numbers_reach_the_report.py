"""The numbers that decide WHOSE fault a defect is have to be in the file the fixing agent opens.

Until 2026-08-21 every one of them was pulled out by hand with a throwaway script and pasted into a
cluster message. That works while somebody is sitting there doing it, and does not survive a handover:
the .md report — the thing another agent actually reads — carried none of them.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent.report import _mechanism_numbers as M


def test_a_quiet_healthy_round_says_nothing():
    """No line without something to say: a report padded with zeroes stops being read."""
    assert M({}) == []
    assert M({"worker_health": {"spawned": 0}, "search_returns": {"queries": 0}}) == []


def test_a_relay_is_named_as_NOT_a_death():
    out = " ".join(M({"worker_health": {"spawned": 3, "ok": 1, "errored": 0, "relayed": 1,
                                        "still_running": 1}}))
    assert "NO es una muerte" in out
    assert "seguía(n) trabajando" in out


def test_the_shared_session_carries_its_own_contrast():
    out = " ".join(M({"worker_deaths": {"shared_sessions": {"c5ad1d9e": ["3", "4"]},
                                        "dead_resuming": 2, "resuming": 2,
                                        "dead_fresh": 0, "fresh": 3, "lifetimes_ms": {}}}))
    assert "COMPARTIDA" in out
    assert "2 de 2" in out and "0 de 3" in out, "the split IS the finding; a count of corpses is not"


def test_a_search_that_answered_and_never_arrived_is_flagged():
    out = " ".join(M({"search_returns": {"queries": 23, "returns": 22, "notes_from_search": 0}}))
    assert "NINGUNA se le empujó al cerebro" in out


def test_and_is_NOT_flagged_when_it_did_arrive():
    out = " ".join(M({"search_returns": {"queries": 5, "returns": 5, "notes_from_search": 5}}))
    assert "NINGUNA" not in out


def test_an_unsettled_round_warns_that_missing_may_mean_not_yet():
    out = " ".join(M({"quiescence": {"settled": False, "waited_s": 60.2, "pending_workers": 1}}))
    assert "todavía no" in out


def test_a_settled_round_says_nothing_about_it():
    assert M({"quiescence": {"settled": True, "waited_s": 6.0, "pending_workers": 0}}) == []


# ── V2-362: the delivery CLOCK, in the report ───────────────────────────────────────────────────────────
#
# `sheet_timing` has been calculated since V2-300 and was refined in V2-355… yet it was not printed anywhere. The judge
# receives it in the JSON, but whoever reads the report—a human or the agent who is going to fix the case—could not see
# the number. A measurement without a reader is a decision without a caller: it exists and changes nothing. This was
# discovered when trying to extract the latency from fourteen rounds and finding the column empty in all fourteen.
#
# And it is THE number in the operator's complaint (“a search is done in one minute, two or three at most”): how long
# the assignment takes to put its first row in front. With “efficiency 2” in eleven of those fourteen rounds, that
# datum is the only thing that says where to aim.

def test_el_reloj_sale_con_su_numero_y_con_QUE_reloj_es():
    """The LOOSE clock (the worker's first write, which may be its plan) and the STRICT one (the intake, which contains
    genuine candidates) do not measure the same thing—confusing them is what produced the invented 130.8 s of
    “retention” that V2-355 cut. A number without its provenance is one nobody audits."""
    out = " ".join(M({"sheet_timing": {"sheet_ms": 1000.0, "sheet_named_ms": 71000.0,
                                       "delivery_lag_s": 12.8, "delivery_clock": "intake"}}))
    assert "primera fila de candidatos: 70.0s" in out
    assert "reloj: intake" in out
    assert "12.8s después de que existieran" in out


def test_una_hoja_que_se_abrio_y_nunca_recibio_nada_lo_DICE():
    """“Did not arrive” and “not measured” are different things: staying silent here leaves the round unexplained."""
    out = " ".join(M({"sheet_timing": {"sheet_ms": 1000.0}}))
    assert "NUNCA llegó" in out


def test_sin_medida_no_se_inventa_una_linea():
    assert M({}) == []
    assert M({"sheet_timing": {}}) == []


def test_el_retraso_de_CERO_se_imprime_y_no_se_confunde_con_ausente():
    """A `delivery_lag_s` of 0 is an immediate delivery—the best possible news—and a `None` means it was not
    measured. An `if _lag:` would have silently collapsed them together."""
    out = " ".join(M({"sheet_timing": {"sheet_ms": 1000.0, "sheet_named_ms": 5000.0, "delivery_lag_s": 0.0}}))
    assert "0.0s después de que existieran" in out
