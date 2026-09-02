"""Deterministic FlashBrain canvas guards (V2-034, manual session 2026-07-12).

Bug: the operator ASKING about a widget ("¿por qué has abierto el de proyectos?") caused zaelar to OPEN a
spurious widget (the model emitted [[show]] and/or the fallback triggered). A META question/complaint about a past
action is NEVER a command to show something. Run: .venv/bin/pytest tests/voice/unit/providers/test_nucleo_guards.py
"""
from voice.engine.llm.providers.nucleo import _is_meta_widget_question as meta, _norm_nfkd as norm


def _q(t: str) -> bool:
    return meta(norm(t))


def test_meta_questions_are_not_commands():
    assert _q("¿por qué has abierto el widget de proyectos?") is True
    assert _q("¿por qué se abrió un widget de proyectos sin que lo pida?") is True
    assert _q("no deberías haber abierto nada") is True
    assert _q("¿por qué me mostraste eso?") is True


def test_real_commands_still_pass():
    assert _q("muéstrame la agenda") is False
    assert _q("¿me muestras la agenda?") is False        # polite command phrased as a question
    assert _q("abre el navegador") is False
    assert _q("enséñame el reloj") is False
    assert _q("ponme el tiempo en pantalla") is False


def test_deictic_show_resolves_topic_from_previous_turn(monkeypatch):
    from voice.engine.llm.providers import nucleo, widget_intent

    # El doble se pone donde la función MIRA: `_show_guard_target` resuelve `_identify` en los globals de
    # `widget_intent`, que es donde vive desde la pasada del trinquete. Parchear el reexport de `nucleo` deja
    # la función real intacta y el test mide otra cosa (V2-555, misma lección).
    monkeypatch.setattr(widget_intent, "_identify",
                        lambda text: "meteo-soria" if "tiempo" in text.lower() else None)
    context = [{"role": "user", "content": "¿Qué tiempo hará mañana aquí?"},
               {"role": "assistant", "content": "Mañana estará despejado."}]
    assert nucleo._show_guard_target("Vale, pues muéstramelo.", context) == "meteo-soria"
    assert nucleo._show_guard_target("No muestres nada.", context) is None
