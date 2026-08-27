#
# test_attention.py — gate de atención (V2-015 · T134/T135/T136; contenido V2-??? 2026-08-16).
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


# ── modo ────────────────────────────────────────────────────────────────────────────────────────────────
def test_mode_default_is_always():
    # robot OFF por defecto = escucha y responde siempre; el toggle de la UI pasa a wake-word.
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
    assert not attention.has_wakeword("zaelar")   # el custom REEMPLAZA el default


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
    v = attention.evaluate("y mañana qué tengo", now=now + 10)   # dentro de 30s
    assert v.directed and v.reason == "active_window"


def test_smart_window_expires(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = attention.evaluate("y mañana qué tengo", now=now + 45)   # fuera de 30s
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
    assert not attention.evaluate("sin llamarle", now=now + 5).directed   # ventana NO cuenta
    assert attention.evaluate("zaelar ayuda", now=now + 5).directed


def test_always_mode_everything_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    assert attention.evaluate("cualquier cosa ambiente").directed


# ── evaluate_content: modo `always` JUZGA el contenido (2026-08-16) ────────────────────────────────────────
# Real, sesión en vivo: ruido de fondo ("Mira donde tú quieras, pero dame el ya...") corrió un turno COMPLETO
# —incluido un web_search real de 3,3s— antes de descartarse como superado. `evaluate()` (arriba) sigue dando
# TODO por dirigido en `always`; `evaluate_content()` es la que de verdad discrimina, y es la única que usa el
# turno real de voz (nucleo.py). El juez es inyectable (`set_directed_judge`) para no pegarle a la red en tests.
def _run(coro):
    return asyncio.run(coro)


def test_evaluate_content_ignores_smart_wakeword_modes_same_as_evaluate(monkeypatch):
    """Fuera de `always` no hace falta preguntarle a ningún modelo — el heurístico de siempre basta."""
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
    """El caso real que motivó esto: ruido de fondo, el juez dice AMBIENTE, y el turno NUNCA llega a costar
    nada (nucleo.py corta aquí, antes del prompt/tools/búsqueda)."""
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
    """None = no se pudo parsear la respuesta (JSON roto, modelo raro) — mismo fail-open que una excepción."""
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


# ── PRONOMBRE ENCLÍTICO (fallo REAL en vivo, 2026-08-12 13:01:51) ────────────────────────────────────────
# El operador dijo «Ciérralo todo y páralo todo». `\bcierra\b` no casa con «cierralo» (no hay frontera de palabra
# después de 'cierra'), así que el detector devolvió None, la orden acabó en el MODELO —que ese turno se atascó— y
# no se cerró nada. Este camino existe precisamente para que cerrar y parar NO dependan del LLM.
# Es morfología, no una lista de frases: el imperativo español pega hasta dos pronombres al verbo.
def test_close_all_with_the_pronoun_stuck_to_the_verb():
    assert attention.hard_interrupt("Ciérralo todo y páralo todo.") == "close"   # la frase EXACTA del incidente
    assert attention.hard_interrupt("ciérralo todo") == "close"
    assert attention.hard_interrupt("ciérramelo todo") == "close"                # dos pronombres
    assert attention.hard_interrupt("quítalos todos") == "close"
    assert attention.hard_interrupt("límpialo todo") == "close"


def test_stop_with_the_pronoun_stuck_to_the_verb():
    """El pronombre pegado desambigua la PREPOSICIÓN, así que un stop con clítico no necesita el tope de
    palabras de la regla blanda — eso sigue siendo cierto y es lo que este caso protege.

    Lo que V2-393 corrigió es la otra mitad: «inequívoco como VERBO» no es «inequívoco sobre QUÉ». El
    reflexivo/dativo habla de zaelar y sigue siendo un stop duro; el acusativo de tercera («párala»,
    «detenlo») lleva OBJETO DIRECTO — va sobre una cosa — y un barge-in no tiene objeto. Medido en
    `watch-a-video-not-listen-to-it`: «Ahora páralo, porfa» sobre un vídeo cargado se comió el turno entero.
    El detalle vive en `tests/voice/unit/test_paralo_lleva_objeto.py` (nodo 3.14).
    """
    assert attention.hard_interrupt("páralo todo ahora mismo y espera") == "stop"   # «todo» → global
    assert attention.hard_interrupt("párate ahora mismo y espera") == "stop"        # reflexivo → es él
    assert attention.hard_interrupt("párala") is None                               # acusativo → una cosa
    assert attention.hard_interrupt("detenlo") is None


def test_the_enclitic_forms_do_not_swallow_normal_speech():
    """La frontera sigue exigiendo un pronombre REAL pegado: ni 'cierralotodo' inventado ni palabras que empiecen
    igual disparan un cierre, y un turno largo con 'para' de preposición sigue siendo conversación."""
    assert attention.hard_interrupt("dame una receta rica para la cena de mañana") is None
    assert attention.hard_interrupt("cierra la puerta de casa cuando salgas") is None   # sin 'todo/widgets'
    assert attention.hard_interrupt("quita la pantalla completa") is None               # modo de UN widget


def test_hard_interrupt_soft_para_short():
    assert attention.hard_interrupt("para por favor") == "stop"


def test_hard_interrupt_soft_para_long_is_not_stop():
    # "para" como preposición en un turno largo NO debe disparar un STOP.
    assert attention.hard_interrupt("dame una receta rica para la cena de mañana") is None


def test_hard_interrupt_none_for_normal_turn():
    assert attention.hard_interrupt("qué tiempo hace hoy") is None
    assert attention.hard_interrupt("cierra la agenda") is None   # cierre de UN widget ≠ hard (no 'todo/widgets')


# ── clamp_input (T135) ──────────────────────────────────────────────────────────────────────────────────
def test_clamp_short_passthrough():
    txt, clipped = attention.clamp_input("hola", 100)
    assert txt == "hola" and not clipped


def test_clamp_preserves_command_at_start():
    cmd = "cierra los widgets por favor. "
    long = cmd + ("bla bla bla ambiente " * 200)   # >> max
    txt, clipped = attention.clamp_input(long, 400)
    assert clipped
    assert "cierra los widgets" in txt            # el comando NO se pierde aunque esté al principio
    assert len(txt) <= 400 + 8


def test_clamp_truncates_when_no_command():
    long = "ruido ambiente " * 500
    txt, clipped = attention.clamp_input(long, 300)
    assert clipped and len(txt) == 300
