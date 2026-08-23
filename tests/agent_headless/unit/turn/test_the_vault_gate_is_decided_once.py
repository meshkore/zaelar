"""One vault gate, two mouths — F1 step 1 of the 2026-08-23 architecture audit.

The decision (is this a security-config command? is there a spoken secret? does the turn end here?) lived TWICE:
`providers/vault_intercept.py` for voice, and its own copy inside `probe.py::run_turn` under three mirror
markers. They had already drifted — the probe's copy answered with the parenthetical «(secreto cifrado)» where
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


# ── la decisión ──────────────────────────────────────────────────────────────────────────────────────────────

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
    """V2-141, y la razón de que la puerta no pueda consumir siempre: nadie recita un IBAN por gusto. Tragarse
    el turno pierde la petición Y le impide llegar al confirm-gate, que es el que habría parado el pago."""
    from memory import secrets as msecrets
    from memory import vault
    # 15 palabras de contenido una vez fuera el valor — por encima del umbral de `vault_carrier`
    # (CARRIER_MAX_WORDS = 10). La primera versión de este caso dejaba justo 10 y el veredicto era «el secreto
    # ERA el turno»: el caso estaba mal, no el código.
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
    """`store=False` es el `ingest=False` del probe. Es el único punto donde los dos canales difieren de verdad,
    y va de la CORRIDA, no de la boca — por eso es un parámetro y no el nombre de un canal."""
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
    """Si no se puede saber si el secreto ERA el turno, la respuesta segura es que sí: consumir un turno cuesta
    una repetición, dejar seguir el valor cuesta el invariante por el que existe este módulo."""
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


# ── y que NINGÚN canal conserve su copia ─────────────────────────────────────────────────────────────────────

def test_both_channels_go_through_the_gate_and_neither_keeps_a_copy():
    """El guarda de la clase. Sin él, la puerta puede estar perfecta mientras un canal sigue decidiendo por su
    cuenta en silencio — que es exactamente el estado que esta extracción encontró."""
    from nucleo.flash import probe
    from voice.engine.llm.providers import vault_intercept

    for mod, name in ((probe, "probe.run_turn"), (vault_intercept, "vault_intercept")):
        src = inspect.getsource(mod)
        assert "vault_gate" in src, f"{name} ya no pasa por la puerta compartida"
        assert "secret_is_the_whole_turn" not in src, f"{name} recuperó su propia decisión de V2-141"
        assert "_vr.detect" not in src, f"{name} volvió a detectar la config por su cuenta"
