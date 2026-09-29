"""full41 E3 (demo pass 2026-09-29): «send the invoice to andrew, tell him we're already trying inworld and he should
book it» over the open receipt → «I can't send it myself — sending mail isn't something I can do on my end», no
call, the verdict reading `mensajeria:forward`. The promise pass asks «did you promise an act?»; a refusal did not,
so it rightly called nothing, and the mail never went. A refusal of an action the card DECLARES, for an order the
verdict names, gets one more question with that action named."""
import asyncio
import pathlib

import pytest

from nucleo.flash import act_repair

ENGINE = pathlib.Path(__file__).resolve().parents[3]
_REFUSAL = "I can't send it myself — sending mail isn't something I can do on my end."
_FORWARD = {"widget_id": "mensajeria", "action": "forward",
            "payload": {"contact": "Andrew", "text": "We're already trying Inworld — please book it."}}


class _Model:
    """First call = the promise pass (refuses again, calls nothing); later calls = the scripted answer."""
    def __init__(self, later):
        self.later, self.seen = later, []

    async def complete(self, messages, **kw):
        self.seen.append(messages)
        if len(self.seen) > 1:
            for name, args in self.later:
                kw["on_tool_call"](name, args)


@pytest.fixture
def model(monkeypatch):
    import nucleo.flash.fast_client as fc
    holder = {}

    def use(later):
        holder["m"] = _Model(later)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


def _run(verdict="forward"):
    return asyncio.run(act_repair.call_for_promise_or_order("send the invoice to andrew", _REFUSAL, "mensajeria",
                                                            verdict))


def test_a_refusal_of_the_verdicts_declared_act_gets_its_call(model):
    m = model([("widget_data", _FORWARD)])
    assert _run() == _FORWARD
    system = m.seen[1][0]["content"]
    assert "`forward`" in system and "sending mail isn't something I can do" in system


def test_without_a_verdict_a_refusal_stays_a_refusal(model):
    m = model([("widget_data", _FORWARD)])
    assert _run(verdict="") is None
    assert len(m.seen) == 1, "no second question without an order the verdict names"


def test_the_model_can_still_decline(model):
    model([])
    assert _run() is None


def test_both_channels_use_it():
    for rel in ("voice/engine/llm/providers/nucleo.py", "nucleo/flash/probe.py"):
        src = (ENGINE / rel).read_text("utf-8")
        assert "call_for_promise_or_order(" in src, rel
        assert "_act_repair.call_for_promise(operator_text, spoken, _ar_wid" not in src, rel


def test_an_escalation_to_an_open_card_gets_the_verdicts_call_too():
    """full44 E3: the model ESCALATED «forward the Inworld invoice to Andrew» with the receipt open and the verdict
    reading `mensajeria:forward`. The open-card pass asked «did you promise?» of the escalation text, got nothing,
    and a browser worker took the errand — its card sat on screen for the rest of the demo, and the mail went out
    minutes later. Both channels now ask the verdict's call there too."""
    voice = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    i = voice.index("V2-770 — the rung fills ONE key")
    assert "call_for_promise_or_order(operator_text, str(escalate_req" in voice[i:i + 1200]
    probe = (ENGINE / "nucleo/flash/probe.py").read_text("utf-8")
    assert "_ar_esc.call_for_promise_or_order(operator_text, spoken or text, _owner, _owner_act" in probe
