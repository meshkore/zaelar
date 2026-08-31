"""One vault gate, two mouths — F1 step 1 of the 2026-08-23 architecture audit.

The decision (is this a security-config command? is there a spoken secret? does the turn end here?) lived TWICE:
`providers/vault_intercept.py` for voice, and its own copy inside `probe.py::run_turn` under three mirror
markers. They had already drifted — the probe's copy answered with the parenthetical “(encrypted secret)” where
voice said a real localized sentence, and V2-141 had to be repaired in both places separately, its own comment
noting the copies made each other's bugs invisible.

What these cases pin is the split that makes the extraction worth anything: the DECISION is shared and the
DELIVERY is not. A test that only checked `vault_gate` in isolation would pass just as happily with either
channel still carrying its private copy.
"""
import asyncio
import inspect

from nucleo.turn import vault_gate


class _Detected:
    """Models the real `memory.secrets.Detected` — including `span`, which `redact()` slices with."""

    def __init__(self, text: str, value: str = "hunter2"):
        self.label, self.value = "contraseña de Netflix", value
        self.slot, self.sensitivity = "secret:netflix:password", "high"
        i = text.index(value)
        self.span = (i, i + len(value))


def _run(coro):
    return asyncio.run(coro)


# ── the decision ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_plain_turn_passes_through_untouched():
    v = _run(vault_gate.inspect("pon música de jazz"))
    assert not v.consumed and v.kind == "" and v.text == "pon música de jazz"


def test_the_kickoff_is_not_the_operator_talking():
    """Voice passes `enabled=not first_turn`: the greeting zaelar opens with must not be scanned for secrets."""
    v = _run(vault_gate.inspect("mi contraseña de Netflix es hunter2", enabled=False))
    assert not v.consumed and v.kind == ""


def test_a_secret_that_IS_the_turn_consumes_it_and_never_returns_the_value(monkeypatch):
    from memory import secrets as msecrets
    from memory import vault
    txt = "mi contraseña de Netflix es hunter2"
    monkeypatch.setattr(msecrets, "detect", lambda t: [_Detected(txt)])
    monkeypatch.setattr(vault, "exists", lambda: True)
    saved = []
    monkeypatch.setattr(vault, "store_secret", lambda l, v, **k: saved.append((l, v)))

    v = _run(vault_gate.inspect(txt))
    assert v.consumed and v.kind == "saved" and v.has_vault
    assert saved == [("contraseña de Netflix", "hunter2")]
    assert "hunter2" not in v.text, "el valor sobrevivió al texto que sigue el turno"
    assert v.line and "hunter2" not in v.line


def test_a_secret_CARRIED_inside_a_request_does_not_swallow_the_turn(monkeypatch):
    """V2-141, and why the gate cannot always consume: nobody recites an IBAN for pleasure. Swallowing
    the turn loses the request AND prevents it from reaching the confirm-gate, which is what would have stopped the payment."""
    from memory import secrets as msecrets
    from memory import vault
    # 15 content words once the value is removed — above the `vault_carrier` threshold
    # (CARRIER_MAX_WORDS = 10). The first version of this case left exactly 10, and the verdict was “the secret
    # WAS the turn”: the case was wrong, not the code.
    txt = "paga la factura 42 del gimnasio con el IBAN hunter2 antes del viernes por la mañana"
    monkeypatch.setattr(msecrets, "detect", lambda t: [_Detected(txt)])
    monkeypatch.setattr(vault, "exists", lambda: True)
    monkeypatch.setattr(vault, "store_secret", lambda l, v, **k: None)

    v = _run(vault_gate.inspect(txt))
    assert not v.consumed and v.kind == "carried"
    assert "hunter2" not in v.text and "factura 42" in v.text


def test_without_a_vault_it_asks_for_one_instead_of_pretending(monkeypatch):
    from memory import secrets as msecrets
    from memory import vault
    txt = "mi contraseña de Netflix es hunter2"
    monkeypatch.setattr(msecrets, "detect", lambda t: [_Detected(txt)])
    monkeypatch.setattr(vault, "exists", lambda: False)
    v = _run(vault_gate.inspect(txt))
    assert v.consumed and v.kind == "need_vault" and not v.has_vault and v.line


def test_a_dry_run_never_writes_the_operators_real_secret(monkeypatch):
    """`store=False` is the probe's `ingest=False`. It is the only point where the two channels truly differ,
    and it concerns the RUN, not the mouth — which is why it is a parameter rather than a channel name."""
    from memory import secrets as msecrets
    from memory import vault
    txt = "mi contraseña de Netflix es hunter2"
    monkeypatch.setattr(msecrets, "detect", lambda t: [_Detected(txt)])
    monkeypatch.setattr(vault, "exists", lambda: True)
    calls = []
    monkeypatch.setattr(vault, "store_secret", lambda l, v, **k: calls.append(l))
    v = _run(vault_gate.inspect(txt, store=False))
    assert calls == [], "una corrida en seco escribió en la bóveda de verdad"
    assert v.consumed, "pero el turno se resuelve igual: el operador recibe respuesta"


def test_an_unreadable_carrier_verdict_fails_CLOSED(monkeypatch):
    """If it is impossible to know whether the secret WAS the turn, the safe answer is yes: consuming a turn costs
    one repetition; letting the value through costs the invariant for which this module exists."""
    from memory import secrets as msecrets
    from memory import vault
    from nucleo.flash import vault_carrier
    txt = "mi contraseña de Netflix es hunter2"
    monkeypatch.setattr(msecrets, "detect", lambda t: [_Detected(txt)])
    monkeypatch.setattr(vault, "exists", lambda: True)
    monkeypatch.setattr(vault, "store_secret", lambda l, v, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("simulado")
    monkeypatch.setattr(vault_carrier, "secret_is_the_whole_turn", _boom)
    assert _run(vault_gate.inspect(txt)).consumed


# ── and that NO channel keeps its copy ───────────────────────────────────────────────────────────────────────

def test_both_channels_go_through_the_gate_and_neither_keeps_a_copy():
    """The class's guard. Without it, the gate can be perfect while a channel continues deciding on its
    own in silence — exactly the state this extraction found."""
    from nucleo.flash import probe
    from voice.engine.llm.providers import vault_intercept

    for mod, name in ((probe, "probe.run_turn"), (vault_intercept, "vault_intercept")):
        src = inspect.getsource(mod)
        assert "vault_gate" in src, f"{name} ya no pasa por la puerta compartida"
        assert "secret_is_the_whole_turn" not in src, f"{name} recuperó su propia decisión de V2-141"
        assert "_vr.detect" not in src, f"{name} volvió a detectar la config por su cuenta"
        assert "vault_flow" not in src, f"{name} volvió a resolver el reveal por su cuenta"

    # And the edge that truly matters for the reveal: the TEXT channel cannot even mention the value.
    probe_src = inspect.getsource(probe)
    assert ".value" not in probe_src.split("reveal_secret")[1][:600], "probe.py alcanza el valor descifrado"


# ── REVEALING a secret: same outcome, and a boundary that is NOT stylistic ──────────────────────────────────

class _Rev:
    """Stands in for `vault_flow.reveal`, which actually decrypts."""

    def __init__(self, **kw):
        self.kw = {"status": "ok", "label": "Netflix", "memory_id": 7, "value": "hunter2", **kw}

    def __call__(self, label):
        return dict(self.kw)


def test_the_text_channel_CANNOT_carry_the_value(monkeypatch):
    """The invariant separating the two channels, and why `as_probe_payload()` exists instead of
    composing the dict by hand in `probe.py`: that response travels to the harness and use-case logs. With the
    shared phrase, the probe would have to RECEIVE the value in order to discard it afterward — exactly how an
    invariant degrades into a convention."""
    from nucleo.flash import vault_flow
    monkeypatch.setattr(vault_flow, "reveal", _Rev())
    out = _run(vault_gate.reveal("Netflix"))
    payload = out.as_probe_payload()
    assert out.value == "hunter2", "el desenlace sí lo lleva: la voz lo necesita"
    assert "hunter2" not in repr(payload), "el valor se escapó por el canal de texto"
    assert payload["status"] == "ok" and payload["label"] == "Netflix"


def test_the_observability_rows_come_with_the_outcome(monkeypatch):
    """Each channel emits on its own bus, but WHAT is emitted is decided by the outcome — otherwise, a new branch
    gets wired into one and not the other, which is the failure this package exists to close."""
    from nucleo.flash import vault_flow
    for status, expected in (("ok", "reveal"), ("locked", "locked"), ("no_vault", "no_vault")):
        monkeypatch.setattr(vault_flow, "reveal", _Rev(status=status))
        out = _run(vault_gate.reveal("Netflix"))
        assert [e[1] for e in out.events] == [expected], status
    monkeypatch.setattr(vault_flow, "reveal", _Rev(status="not_found", candidates=["Gmail"]))
    assert _run(vault_gate.reveal("Netflix")).events == [], "un no-encontrado no es una fila de seguridad"


def test_the_event_keys_avoid_the_one_that_collides(monkeypatch):
    """`label` would overwrite the event's own label in `observer.emit`. It already cost us one unreadable row once."""
    from nucleo.flash import vault_flow
    monkeypatch.setattr(vault_flow, "reveal", _Rev())
    extra = _run(vault_gate.reveal("Netflix")).events[0][2]
    assert "slabel" in extra and "label" not in extra


def test_a_broken_reveal_never_takes_the_turn_down(monkeypatch):
    from nucleo.flash import vault_flow

    def _boom(_l):
        raise RuntimeError("simulado")
    monkeypatch.setattr(vault_flow, "reveal", _boom)
    out = _run(vault_gate.reveal("Netflix"))
    assert out.status == "error" and out.events == []


def test_the_hard_rule_decides_whether_the_value_is_SPOKEN(monkeypatch):
    """V2-060 F2: comfortable mode says it; “don't tell me the secrets by voice” shows and names it without saying it."""
    from memory import state as mstate
    out = vault_gate.RevealOutcome(status="ok", label="Netflix", value="hunter2")

    monkeypatch.setattr(mstate, "security_flag", lambda k, d=True: True)
    assert "hunter2" in vault_gate.voice_line(out)

    monkeypatch.setattr(mstate, "security_flag", lambda k, d=True: False)
    said = vault_gate.voice_line(out)
    assert "hunter2" not in said and "Netflix" in said
