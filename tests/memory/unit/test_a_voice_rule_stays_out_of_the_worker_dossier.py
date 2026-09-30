"""A spoken rule about how the VOICE speaks stays out of the worker's dossier (2026-09-29).

`state.rules` was a flat list of ≤8 sentences with no scope, and it rode into every prompt that carries the
memory context — the FlashBrain turn (right) and the brain worker's dossier («Reglas del operador: …»), where
«no me confirmes las órdenes» or «sin muletillas» mean nothing to a browser errand and burn its eight slots.
The operator's design: rules are HIERARCHICAL — genesis per domain (already so), and a spoken rule carries the
scope a fixed classifier gives it at the moment it is set; every prompt composer asks only for its own. The
default scope is `general` = everywhere, exactly today's behaviour, so nothing changes unless a rule is
recognised with certainty as a manner of speaking.
"""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import style_policy as sp


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    yield
    memdb.reset_db(); mememb.reset()


def test_the_fixed_classifier_names_the_scope_of_a_spoken_rule():
    for voice in ("no me confirmes las órdenes", "sin muletillas", "sé breve, respuestas de una frase",
                  "confirm my orders", "keep it short, one sentence", "no fillers please", "háblame de usted"):
        assert sp.scope_of(voice) == "voice", voice
    for general in ("nunca compres en Wish", "llámame siempre capitán", "las reuniones siempre de 30 minutos",
                    "avísame de los correos de Quinn", "always check my calendar before booking"):
        assert sp.scope_of(general) == "general", general


def test_a_voice_rule_reaches_the_voice_and_not_the_worker():
    memapi.add_user_rule("no me confirmes las órdenes", scope="voice")
    memapi.add_user_rule("nunca compres en Wish")                       # default scope: everywhere, as before
    assert memapi.rules_for("voice") == ["no me confirmes las órdenes", "nunca compres en Wish"]
    assert memapi.rules_for("worker") == ["nunca compres en Wish"]
    block, _, _ = memapi.compose_state(mission_fallback="m")
    assert "no me confirmes" in block and "Wish" in block, "the FlashBrain still sees both"


def test_retiring_a_rule_drops_its_scope_and_the_list_stays_a_list_of_strings():
    memapi.add_user_rule("sin muletillas", scope="voice")
    _, gone = memapi.remove_user_rule("olvida lo de las muletillas")
    assert gone == "sin muletillas"
    assert memapi.rules_for("worker") == [] and memapi.rules_for("voice") == []
    assert memapi.state().get("rule_scopes") == {}
    memapi.add_user_rule("Trátame de usted", scope="voice")
    assert all(isinstance(r, str) for r in memapi.state()["rules"]), "the store keeps its shape for old readers"


def test_the_directive_handler_and_the_dossier_are_wired():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    sd = (root / "nucleo/flash/style_directive.py").read_text("utf-8")
    assert sd.count("scope=_rscope.scope_of(") == 2, "both channels (voice and probe) store the rule with its scope"
    dossier = (root / "nucleo/memory_agent/dossier.py").read_text("utf-8")
    assert 'rules_for("worker"' in dossier, "the worker's dossier asks for its own rules"


def test_a_rule_that_names_one_card_gets_that_widget_as_its_scope():
    from nucleo.flash import rule_scope
    assert rule_scope.scope_of("en la agenda, las reuniones siempre de 30 minutos") == "widget:agenda"
    assert rule_scope.scope_of("in the calendar, meetings are always 30 minutes") == "widget:agenda"
    assert rule_scope.scope_of("no me confirmes las órdenes") == "voice", "a manner of speaking wins"
    assert rule_scope.scope_of("nunca compres en Wish") == "general"
    assert rule_scope.scope_of("close the calendar and the messages") == "general", "two cards is nobody's rule"


def test_a_widget_rule_rides_in_its_row_not_in_the_generic_line():
    """Composed at the point of the flow it belongs to: the widget's own row of the resources block, every turn
    (an order about the agenda comes before the agenda is open). The worker keeps it: losing it there would cost
    more than carrying it."""
    from widgets import brief
    memapi.add_user_rule("en la agenda, las reuniones siempre de 30 minutos", scope="widget:agenda")
    memapi.add_user_rule("nunca compres en Wish")
    assert memapi.rules_for("widget:agenda") == ["en la agenda, las reuniones siempre de 30 minutos"]
    assert memapi.rules_for("voice") == ["nunca compres en Wish"], "the generic line carries the general ones"
    assert memapi.rules_for("worker") == ["en la agenda, las reuniones siempre de 30 minutos", "nunca compres en Wish"]
    block, _, _ = memapi.compose_state(mission_fallback="m")
    assert "Wish" in block and "30 minutos" not in block
    res = brief.for_prompt([], [], query="")
    assert "[agenda] regla del operador: en la agenda, las reuniones siempre de 30 minutos" in res
