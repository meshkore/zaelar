"""A board note is a note ABOUT something, and that something is the brain that did the work.

Each row already sealed which JUDGE scored it (`status.record`'s `judge`), based on a measurement from
2026-08-20: the judge's chain falls back to another provider when the primary runs out of quota, and a case
that «dropped from 3 to 2» may have changed only its measuring rule. One floor lower, the same thing happens
and matters more: the judge is the instrument; the brain IS the product.

Measured on 2026-08-27: a batch of US cases ran with z.ai without a 5-hour quota, so their Brain Workers
were served by the RELAY tier (`deepseek-v4-flash`) instead of the primary that the cloud contracts
(`glm-5.3`). Five rows scored 1–2 would have remained beside rows measured with the primary, identical in
appearance and about a different product. I caught it by reading the log manually; neither the board nor
the ledger stored it anywhere.

The tests pin down the REAL SHAPE of the flow, which is where this makes no noise when it breaks:
  · `observer.emit` does `ev.update(extra)`, so the model arrives FLATTENED and the payload is a JSON STRING.
  · `worker_start` is reused by the voice engine's BOOT («motor de voz arriba»), which has no worker behind it
    and calls its model `llm_model`.
  · a relay row does NOT have `kind == "perf"`: the chain's `extra={"kind": "exhausted"}` overwrites the
    event's kind when it is stored.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import status as S
from tests.use_cases.e2e.agent import verify as V


def _worker_row(model: str, backend: str = "claude_code") -> dict:
    """A `worker_start` exactly as returned by `/api/observability/events`, not as emitted in-process."""
    return {"kind": "worker_start", "cat": "worker",
            "payload": json.dumps({"kind": "worker_start", "label": f"worker · {backend}",
                                   "cat": "worker", "id": "1", "model": model, "layer": "web"})}


def _boot_row() -> dict:
    """The voice engine boot: SAME kind, no worker behind it, and its model is called `llm_model`."""
    return {"kind": "worker_start", "cat": "worker",
            "payload": json.dumps({"kind": "worker_start", "label": "motor de voz arriba", "role": "system",
                                   "cat": "worker", "profile": "remote", "llm_model": "(default)"})}


def _relay_row(frm: str = "z.ai", to: str = "deepseek", why: str = "exhausted") -> dict:
    """A REAL relay: the stored `kind` is the reason, not `perf` — because of `emit`'s `ev.update(extra)`."""
    return {"kind": why, "cat": "system",
            "payload": json.dumps({"kind": why, "cat": "system", "role": "cluster_brain",
                                   "label": f"\U0001f50c cerebro de cluster: «{frm}» sin crédito",
                                   "provider": frm, "next": to})}


def test_reads_the_model_from_the_shape_the_api_returns():
    got = V.brains_that_ran([_worker_row("glm-5.3"), _worker_row("glm-5.3")])
    assert got["n_by_worker"] == {"claude_code/glm-5.3": 2}
    assert got["mixed"] is False


def test_the_voice_engine_booting_is_not_a_brain_worker():
    """Without this line, every round is sealed with a brain that did not run."""
    assert V.brains_that_ran([_boot_row()])["n_by_worker"] == {}
    got = V.brains_that_ran([_boot_row(), _worker_row("glm-5.3")])
    assert got["n_by_worker"] == {"claude_code/glm-5.3": 1}
    assert got["mixed"] is False, "el arranque no puede hacer que una ronda parezca mixta"


def test_a_chain_that_moved_mid_round_is_loud():
    """Half the round is one product and the other half another: no single stamp would be honest."""
    got = V.brains_that_ran([_worker_row("glm-5.3"), _worker_row("deepseek-v4-flash"),
                             _worker_row("deepseek-v4-flash")])
    assert got["mixed"] is True
    assert S._brain_stamp({"brains": got}) == "deepseek-v4-flash+glm-5.3", "el más usado primero"


def test_the_relay_is_read_by_its_label_not_by_its_kind():
    """Filtering by `kind == 'perf'` finds ZERO relays in a round full of them."""
    relays = V.brains_that_ran([_relay_row()])["relays"]
    assert relays == [{"role": "cluster_brain", "from": "z.ai", "to": "deepseek", "why": "exhausted"}]


def test_the_two_other_event_shapes_read_the_same():
    """Nested under `extra` and read directly from sqlite: the same fact does not depend on how it entered."""
    nested = [{"kind": "worker_start", "payload": {"extra": {"model": "glm-5.3", "label": "worker · cc"}}}]
    flat = [json.loads(_worker_row("glm-5.3")["payload"])]
    assert V.brains_that_ran(nested)["n_by_worker"] == {"cc/glm-5.3": 1}
    assert V.brains_that_ran(flat)["n_by_worker"] == {"claude_code/glm-5.3": 1}


def test_a_round_with_no_worker_is_not_an_unstamped_round():
    """`—` is a MEASURED absence (a conversational case); `?` is a row from before this existed.
    Confusing them would make every old row read as if nobody had worked on it."""
    assert S._brain_stamp({"brains": {"n_by_worker": {}}}) == ""
    assert S._brain_cell({"brain": ""}) == "—"
    assert S._brain_cell({"overall": 4}) == "?"
    assert S._brain_cell({"brain": "glm-5.3"}) == "`glm-5.3`"


def test_the_stamp_travels_from_the_mechanism_report_to_the_ledger_row(tmp_path, monkeypatch):
    """The entire chain: events → mechanism report → ledger row → board column."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    mech = {"brains": V.brains_that_ran([_worker_row("glm-5.3")]), "families_observed": ["worker"]}
    S.record([{"scenario": "x__us", "tier": 2, "run": {"mechanism_report": mech, "transcript": []},
               "verdict": {"overall": 4, "scores": {"mecanismo": 4}, "veredicto": "bien"}}], sandboxed=True)
    row = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["scenarios"]["x__us"]
    assert row["brain"] == "glm-5.3"
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "| brain |" in board and "`glm-5.3`" in board
