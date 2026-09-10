"""V2-658 — a `widget_data` cut by the TOKEN CAP is not a void (measured twice, consecutive sessions
2026-09-10: the operator asked for the Declaration of Independence, the model opened an EMPTY `documento`,
promised twice, finally pasted the full text inline into one widget_data — `finish_reason: length`, action
discarded — and the turn fell to «Perdona, ¿me lo repites?» over an errand it had in hand).

Content that exceeds a voice turn is a WORKER's delivery (V2-644's doc surface): the rescue escalates the
turn's request, naming what the model was trying to write, in BOTH channels."""
import os

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _src(rel: str) -> str:
    return open(os.path.join(ENG, rel), encoding="utf-8").read()


def test_the_helper_names_only_a_token_capped_widget_write():
    from nucleo.flash.fast_client import oversized_widget_write
    hit = {"dropped_tool_calls": [{"name": "widget_data", "reason": "cortada por el tope de tokens",
                                   "args_head": '{"id":"documento","action":"show","payload":{"title":"Decl'}]}
    head = oversized_widget_write(hit)
    assert head and "documento" in head
    # the OTHER two drop classes are different faults with different fixes (V2-566) — never escalated here
    assert oversized_widget_write({"dropped_tool_calls": [
        {"name": "widget_data", "reason": "el stream se cortó a mitad de la acción (interrupción del turno o corte de red)"}]}) is None
    assert oversized_widget_write({"dropped_tool_calls": [
        {"name": "widget_data", "reason": "argumentos ilegibles"}]}) is None
    # a different tool cut by the cap is not a widget delivery
    assert oversized_widget_write({"dropped_tool_calls": [
        {"name": "escalate_to_slowbrain", "reason": "cortada por el tope de tokens"}]}) is None
    assert oversized_widget_write({}) is None and oversized_widget_write(None) is None


def test_the_drop_record_carries_the_head_of_what_was_being_written():
    """Without `args_head` the rescue can only escalate the operator's bare turn text — which at the
    measured incident was «Venga, estoy esperando.», an errand no worker can act on."""
    from nucleo.flash.fast_client import _drop_tool_call
    metrics = {"finish_reason": "length"}
    _drop_tool_call(metrics, "widget_data", '{"id":"documento","action":"show","payload":{"title":"X","body":"' + "a" * 500)
    d = metrics["dropped_tool_calls"][0]
    assert d["reason"] == "cortada por el tope de tokens"
    assert d["args_head"].startswith('{"id":"documento"') and len(d["args_head"]) <= 240


def test_the_voice_channel_wires_the_rescue():
    prov = _src("voice/engine/llm/providers/nucleo.py")
    assert "oversized_widget_write as _oversized" in prov
    assert 'escalate_req["surface"][_ow_req] = "documento"' in prov, \
        "the rescue must carry the DOC surface (V2-644) — a results sheet is the wrong delivery for a text"
    i = prov.index("oversized_widget_write as _oversized")
    j = prov.index('if escalate_req["v"] is not None and not spoken_text:')
    assert i < j, "the rescue must run BEFORE the mute-escalation holding line, so the turn speaks it"


def test_the_probe_mirrors_the_rescue_as_a_synthesized_escalation():
    probe = _src("nucleo/flash/probe.py")
    assert "oversized_widget_write as _oversized_p" in probe
    i = probe.index("oversized_widget_write as _oversized_p")
    j = probe.index('names = [t["name"] for t in tool_calls]')
    assert i < j, "the synthesized escalate must exist before the action classification reads the names"


def test_the_documento_manifest_teaches_against_inline_long_texts():
    import json
    m = json.load(open(os.path.join(ENG, "widgets/documento/manifest.json")))
    u = m["usage"]
    assert "NUNCA cabe en una sola llamada" in u and "append" in u
