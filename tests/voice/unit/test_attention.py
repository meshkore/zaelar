#
# test_attention.py — attention gate (V2-015 · T134/T135/T136; content V2-??? 2026-08-16).
#
import asyncio
import importlib

import pytest

from voice import attention


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    attention.set_directed_judge(None)
    yield
    attention.reset()
    attention.set_directed_judge(None)


# ── mode ────────────────────────────────────────────────────────────────────────────────────────────────
def test_mode_default_is_always():
    # Robot OFF by default = always listens and responds; the UI toggle switches to wake-word mode.
    assert attention.mode() == "always"


def test_mode_env_override(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "WakeWord")
    assert attention.mode() == "wakeword"


def test_mode_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "bogus")
    assert attention.mode() == "always"


# ── wake-word ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "zaelar qué hora es", "Oye Zaelar, abre la agenda", "ZAELAR",
    "oye zaelar ayúdame",
])
def test_wakeword_detected(txt):
    assert attention.has_wakeword(txt)


@pytest.mark.parametrize("txt", [
    "qué hora es", "sí sí sí", "abro mi agenda", "pásame la sal por favor",
    "harvey pon música", "oye jarbi ayúdame",  # mishearings of the old name "harbee" — no longer wakewords
])
def test_wakeword_absent(txt):
    assert not attention.has_wakeword(txt)


def test_custom_wakewords(monkeypatch):
    monkeypatch.setenv("ZAELAR_WAKEWORDS", "colmena, abeja")
    assert attention.has_wakeword("oye colmena")
    assert not attention.has_wakeword("zaelar")   # The custom value REPLACES the default.


# ── evaluate: smart ─────────────────────────────────────────────────────────────────────────────────────
def test_smart_wakeword_is_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    v = attention.evaluate("zaelar, cierra la agenda")
    assert v.directed and v.reason == "wakeword"


def test_smart_no_wakeword_no_window_is_ambient(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    v = attention.evaluate("sí claro, lo que tú digas")
    assert not v.directed and v.reason == "ambient"


def test_smart_active_window_is_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = attention.evaluate("y mañana qué tengo", now=now + 10)   # within 30s
    assert v.directed and v.reason == "active_window"


def test_smart_window_expires(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = attention.evaluate("y mañana qué tengo", now=now + 45)   # beyond 30s
    assert not v.directed and v.reason == "ambient"


def test_window_configurable(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    monkeypatch.setenv("ZAELAR_ATTENTION_WINDOW", "60")
    now = 1000.0
    attention.note_directed(now=now)
    assert attention.evaluate("sigo hablando", now=now + 50).directed


# ── evaluate: wakeword / always / ptt ───────────────────────────────────────────────────────────────────
def test_wakeword_mode_ignores_window(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "wakeword")
    now = 1000.0
    attention.note_directed(now=now)
    assert not attention.evaluate("sin llamarle", now=now + 5).directed   # The window does NOT count.
    assert attention.evaluate("zaelar ayuda", now=now + 5).directed


def test_always_mode_everything_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    assert attention.evaluate("cualquier cosa ambiente").directed


# ── evaluate_content: `always` mode JUDGES content (2026-08-16) ─────────────────────────────────────────
# Real live session: background noise ("Mira donde tú quieras, pero dame el ya...") ran a COMPLETE turn
# —including a real 3.3s web_search— before being discarded as ambient. `evaluate()` (above) still treats
# EVERYTHING as directed in `always`; `evaluate_content()` is what actually discriminates, and it is the only
# one used by the real voice turn (nucleo.py). The judge is injectable (`set_directed_judge`) so tests do not
# hit the network.
def _run(coro):
    return asyncio.run(coro)


def test_evaluate_content_ignores_smart_wakeword_modes_same_as_evaluate(monkeypatch):
    """Outside `always`, there is no need to ask any model—the existing heuristic is sufficient."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = _run(attention.evaluate_content("y mañana qué tengo", now=now + 10))
    assert v.directed and v.reason == "active_window"


def test_evaluate_content_wakeword_is_a_free_shortcut_no_judge_called():
    async def _judge(text, context):
        raise AssertionError("wake-word ya es prueba suficiente, no hace falta gastar un round-trip")
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("zaelar, qué hora es"))
    assert v.directed and v.reason == "wakeword"


def test_evaluate_content_directed_when_the_judge_says_so():
    async def _judge(text, context):
        assert text == "cuánto vale un balón de fútbol"
        return True
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("cuánto vale un balón de fútbol"))
    assert v.directed and v.reason == "always"


def test_evaluate_content_ambient_when_the_judge_says_so():
    """The real case that motivated this: background noise, the judge says AMBIENT, and the turn NEVER incurs
    any cost (nucleo.py cuts off here, before the prompt/tools/search)."""
    async def _judge(text, context):
        return False
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("Mira donde tú quieras, pero dame el ya"))
    assert not v.directed and v.reason == "llm_ambient"


def test_evaluate_content_passes_context_through_to_the_judge():
    seen = {}

    async def _judge(text, context):
        seen["context"] = context
        return True
    attention.set_directed_judge(_judge)
    _run(attention.evaluate_content("de la más alta gama", context="precio del balón del mundial"))
    assert seen["context"] == "precio del balón del mundial"


def test_evaluate_content_fails_open_when_the_judge_raises():
    async def _judge(text, context):
        raise RuntimeError("modelo caído")
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("cualquier frase"))
    assert v.directed, "un juez roto nunca puede dejar mudo al agente"


def test_evaluate_content_fails_open_when_the_judge_returns_none():
    """None = the response could not be parsed (broken JSON, odd model)—same fail-open behavior as an exception."""
    async def _judge(text, context):
        return None
    attention.set_directed_judge(_judge)
    assert _run(attention.evaluate_content("cualquier frase")).directed


def test_evaluate_content_empty_text_is_ambient_without_calling_the_judge():
    async def _judge(text, context):
        raise AssertionError("un texto vacío no necesita juez")
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("   "))
    assert not v.directed


@pytest.mark.parametrize("raw,expected", [
    ('{"directed": true}', True),
    ('{"directed": false}', False),
    ('```json\n{"directed": true}\n```', True),
    ('here you go: {"directed": false} thanks', False),
    ("not json at all", None),
    ("", None),
    (None, None),
    ('{"directed": "yes"}', None),   # no es un bool real — fail-open, no se adivina
])
def test_parse_directed(raw, expected):
    assert attention._parse_directed(raw) is expected


def test_ptt_mode(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "ptt")
    assert not attention.evaluate("hola").directed
    attention.set_ptt(True)
    assert attention.evaluate("hola").directed
    attention.set_ptt(False)
    assert not attention.evaluate("hola").directed


# ── hard interrupt (T136) ───────────────────────────────────────────────────────────────────────────────
def test_hard_interrupt_close_all():
    assert attention.hard_interrupt("cierra los widgets") == "close"
    assert attention.hard_interrupt("cierra todo") == "close"
    assert attention.hard_interrupt("close everything") == "close"


@pytest.mark.parametrize("txt", ["silencio", "cállate", "basta ya", "stop", "para ya", "shhh"])
def test_hard_interrupt_stop_hard(txt):
    assert attention.hard_interrupt(txt) == "stop"


# ── ENCLITIC PRONOUN (REAL live failure, 2026-08-12 13:01:51) ────────────────────────────────────────────
# The operator said «Ciérralo todo y páralo todo». `\bcierra\b` does not match «cierralo» (there is no word
# boundary after 'cierra'), so the detector returned None, the command reached the MODEL—which got stuck on
# that turn—and nothing was closed. This path exists precisely so closing and stopping do NOT depend on the LLM.
# This is morphology, not a phrase list: the Spanish imperative attaches up to two pronouns to the verb.
def test_close_all_with_the_pronoun_stuck_to_the_verb():
    assert attention.hard_interrupt("Ciérralo todo y páralo todo.") == "close"   # the EXACT phrase from the incident
    assert attention.hard_interrupt("ciérralo todo") == "close"
    assert attention.hard_interrupt("ciérramelo todo") == "close"                # two pronouns
    assert attention.hard_interrupt("quítalos todos") == "close"
    assert attention.hard_interrupt("límpialo todo") == "close"


def test_stop_with_the_pronoun_stuck_to_the_verb():
    """An attached pronoun disambiguates the PREPOSITION, so a stop with a clitic does not need the soft
    rule's word limit—that remains true and is what this case protects.

    What V2-393 fixed is the other half: «unambiguous as a VERB» is not «unambiguous about WHAT». The
    reflexive/dative refers to zaelar and remains a hard stop; the third-person accusative («párala»,
    «detenlo») carries a DIRECT OBJECT—it applies to a thing—and a barge-in has no object. In
    `watch-a-video-not-listen-to-it`: «Ahora páralo, porfa» over a loaded video consumed the entire turn.
    The detail lives in `tests/voice/unit/test_paralo_lleva_objeto.py` (node 3.14).
    """
    assert attention.hard_interrupt("páralo todo ahora mismo y espera") == "stop"   # «todo» → global
    assert attention.hard_interrupt("párate ahora mismo y espera") == "stop"        # reflexivo → es él
    assert attention.hard_interrupt("párala") is None                               # acusativo → una cosa
    assert attention.hard_interrupt("detenlo") is None


def test_the_enclitic_forms_do_not_swallow_normal_speech():
    """The boundary still requires a REAL attached pronoun: neither invented 'cierralotodo' nor words that start
    the same way trigger a close, and a long turn with prepositional 'para' remains conversation."""
    assert attention.hard_interrupt("dame una receta rica para la cena de mañana") is None
    assert attention.hard_interrupt("cierra la puerta de casa cuando salgas") is None   # without 'todo/widgets'
    assert attention.hard_interrupt("quita la pantalla completa") is None               # mode for ONE widget


def test_hard_interrupt_soft_para_short():
    assert attention.hard_interrupt("para por favor") == "stop"


def test_hard_interrupt_soft_para_long_is_not_stop():
    # "para" as a preposition in a long turn must NOT trigger a STOP.
    assert attention.hard_interrupt("dame una receta rica para la cena de mañana") is None


def test_hard_interrupt_none_for_normal_turn():
    assert attention.hard_interrupt("qué tiempo hace hoy") is None
    assert attention.hard_interrupt("cierra la agenda") is None   # closing ONE widget ≠ hard (no 'todo/widgets')


# ── clamp_input (T135) ──────────────────────────────────────────────────────────────────────────────────
def test_clamp_short_passthrough():
    txt, clipped = attention.clamp_input("hola", 100)
    assert txt == "hola" and not clipped


def test_clamp_preserves_command_at_start():
    cmd = "cierra los widgets por favor. "
    long = cmd + ("bla bla bla ambiente " * 200)   # >> max
    txt, clipped = attention.clamp_input(long, 400)
    assert clipped
    assert "cierra los widgets" in txt            # the command is NOT lost even though it is at the beginning
    assert len(txt) <= 400 + 8


def test_clamp_truncates_when_no_command():
    long = "ruido ambiente " * 500
    txt, clipped = attention.clamp_input(long, 300)
    assert clipped and len(txt) == 300
