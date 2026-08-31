"""V2-214 — the alert existed and its CONTENT was broken.

Measured on `remember-and-remind-deadline` (2026-08-20 15:49), and the judge named it precisely: «el `prompt` del
cron lleva la frase cruda del usuario, así que el recordatorio hará que el agente vuelva a programar en vez de
avisar — el aviso existe pero su contenido está roto».

`_reminder_prompt` composes the safe form («AVISA al operador, es el recordatorio que te pidió: …») and its own
docstring explains why: the cron's reader is the AGENT at a later moment, so leaving the operator's own words in
asks it to FILE something, which is the loop this whole area exists to close. Only the BACKSTOP went through it.
When the model emits the `cron.create` tag itself, its `prompt` is whatever it wrote — and what it wrote was «el
jueves tengo que renovar el seguro del coche».

So the answer to «regression, or never covered?» is: never covered. Same defect, the other door.

NARROW on purpose: only a FIRST-PERSON obligation is rewritten. A cron the operator set up deliberately («cada
lunes dame el resumen») is already an instruction to the agent, and wrapping it would break a feature to fix a
defect.
"""
import pytest

from nucleo.flash import router_guards as g


def test_the_measured_prompt_becomes_an_instruction_to_NOTIFY():
    out = g.safe_reminder_prompt("el jueves tengo que renovar el seguro del coche")
    assert out.startswith("AVISA al operador")
    assert "renovar el seguro del coche" in out


def test_english_first_person_too():
    assert g.safe_reminder_prompt("I have to renew the car insurance on Thursday").startswith("AVISA")


@pytest.mark.parametrize("already", [
    "AVISA al operador, es el recordatorio que te pidió: renovar el seguro",
    "Avísame de la renovación del seguro del coche",
    "Recuérdame la renovación",
    "remind me about the insurance",
])
def test_something_already_addressed_to_the_agent_is_LEFT_ALONE(already):
    """Wrapping twice reads as a quotation of a quotation, and the point of this is what the agent READS."""
    assert g.safe_reminder_prompt(already) == already


@pytest.mark.parametrize("deliberate", [
    "dame el resumen semanal de la agenda",
    "revisa el correo y dime si hay algo urgente",
    "haz una copia de seguridad de los widgets",
])
def test_a_cron_the_OPERATOR_set_up_is_untouched(deliberate):
    """Sensitivity, and the reason the rule is narrow: these are already instructions to the agent. Wrapping them
    would break a working feature in order to fix a defect."""
    assert g.safe_reminder_prompt(deliberate) == deliberate


def test_empty_stays_empty():
    assert g.safe_reminder_prompt("") == ""
    assert g.safe_reminder_prompt("   ") == ""


def test_BOTH_channels_go_through_it():
    """The backstop already composed the safe form and the model's own tag did not — that asymmetry IS the bug, so
    the guard has to hold on both doors into the scheduler. Asserted on the source because the alternative is a
    live model call."""
    import inspect

    from nucleo.flash import probe
    from voice.engine.llm.providers import nucleo as vp
    for mod in (probe, vp):
        src = inspect.getsource(mod)
        assert "safe_reminder_prompt(" in src, mod.__name__
