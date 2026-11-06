"""One vocabulary of events (V2-857 phase 1, architecture audit 2026-11-05).

Five tables said «what leaves and what it may do»: the event topics, the consent classes, the mandate's `may`, the
manifest's `effects` and the consequence doors. Now an event type is declared ONCE (`nucleo/events/vocabulary`) and
the others are read off it: the topics a rule may subscribe to, the scopes a rule may name, the grants a mandate
holds, the level a leaving class asks at, the effect a manifest action carries by its class. Every class the code
names is declared there — a name outside the table is nobody's event.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from nucleo.events import vocabulary as voc

ENGINE = Path(__file__).resolve().parents[4]


def _classes_named_in_code() -> set[str]:
    """Every literal class the engine hands the consent door: `decide_act("x")`, `act_key("x", …)`,
    `class_policy("x")`, plus genesis' classes, the manifests' `consent_class`, the connectors' and the click gate's."""
    out: set[str] = set()
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    for rel in files:
        if rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("decide_act", "act_key", "class_policy") \
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out.add(node.args[0].value)
    out |= set((json.loads((ENGINE / "nucleo/genesis.json").read_text())["consent"]["classes"]).keys())
    for p in (ENGINE / "widgets").glob("*/manifest.json"):
        for spec in (json.loads(p.read_text()).get("actions") or {}).values():
            if isinstance(spec, dict) and spec.get("consent_class"):
                out.add(str(spec["consent_class"]))
    for p in (ENGINE / "connectors/catalog").glob("*.json"):
        if (cls := json.loads(p.read_text()).get("consent_class")):
            out.add(str(cls))
    from widgets.navegador import click_gate
    out |= set(click_gate.CONSENT_OF.values())
    from nucleo.acts import errand
    out |= {f"errand.{c}" for c, _w in errand._CLASSES if c != "none"}
    return {c for c in out if "." in c}


def test_every_class_the_code_names_is_a_declared_event_type():
    named = _classes_named_in_code()
    assert len(named) >= 10, named
    undeclared = sorted(c for c in named if not voc.declared(c))
    assert not undeclared, f"a class with no event type is nobody's event — declare it in nucleo/events/vocabulary: {undeclared}"
    assert all(voc.of(c).direction == voc.OUT for c in named)


def test_the_topics_a_rule_subscribes_to_are_the_types_that_arrive():
    from nucleo import events
    from rules import subscriptions
    assert subscriptions.TOPICS == voc.topics()
    assert {t for t, _w in subscriptions.TOPICS} == set(voc.names(voc.IN))
    for name in (events.CONNECTOR_MSG, events.MAIL_IN, events.CRON_DUE):
        assert voc.of(name).direction == voc.IN
    assert voc.of(events.WORKER_DONE).direction == voc.TASK and events.WORKER_ASK not in dict(subscriptions.TOPICS)


def test_the_grants_are_one_tuple_and_every_leaving_type_names_one_of_them():
    from nucleo.errands import mandate
    assert mandate.MAY is voc.GRANTS
    names = {g.name for g in voc.GRANTS}
    for t in voc.TYPES:
        if t.direction == voc.OUT and t.grant:
            assert t.grant in names, t
    assert mandate.acts(["reply", "agenda", "dance", "reply"]) == ["message", "schedule"]


@pytest.mark.parametrize("cls, expect", [("payment.authorize", "ask_consent"), ("errand.moves_money", "ask_consent"),
                                         ("errand.mesh_serve", "run")])
def test_a_leaving_class_asks_at_its_declared_level_when_the_caller_measured_none(monkeypatch, cls, expect):
    from nucleo import consent
    consent._reset_for_tests()
    assert consent.decide_act(cls, licensed=True)["verdict"] == expect
    # disarmed: with no declared level the door reads every class as `sensitive`, and an errand that moves money —
    # a class with no genesis row, only its level — would start without asking
    monkeypatch.setattr(voc, "level_of", lambda name, default="sensitive": default)
    assert consent.decide_act("errand.moves_money", licensed=True)["verdict"] == "run"


def test_an_action_of_a_leaving_class_leaves_without_repeating_the_effect(monkeypatch):
    from widgets import effects
    man = {"actions": {"send": {"consent_class": "messaging.send_new"}, "move": {"consent_class": "web.commit"},
                       "look": {"view": True}}}
    monkeypatch.setattr(effects, "_manifest", lambda wid: man if wid == "fake" else {})
    assert effects.leaves("fake", "send") and effects.carries("fake", "send", effects.EXTERNAL_SEND)
    assert not effects.leaves("fake", "move") and not effects.leaves("fake", "look")
    # disarmed: a class the vocabulary does not know implies nothing — the manifest's own words are all there is
    man["actions"]["send"]["consent_class"] = "nothing.declared"
    assert not effects.leaves("fake", "send")


def test_every_leaving_class_is_a_scope_his_rule_may_name(monkeypatch):
    from rules import vocabulary as rv
    for cls in voc.names(voc.OUT):
        family, _dot, act = cls.partition(".")
        assert rv.declared(f"{family}/*/{act}"), cls
    assert rv.nearest("errand/mesh/mesh_serve") == "errand/*/mesh_serve"
    assert "an errand's request goes to an agent" in rv.scopes()["errand/*/mesh_serve"]
    # disarmed: classes read only from genesis and the manifests — the class with no default falls to global
    monkeypatch.setattr(voc, "names", lambda direction="": [])
    assert rv.nearest("errand/mesh/mesh_serve") == "global"


def test_the_click_gate_reads_its_level_off_the_type(monkeypatch):
    from nucleo import consent
    from widgets.navegador import click_gate
    seen = []
    monkeypatch.setattr(consent, "decide_act", lambda cls, **kw: seen.append((cls, kw.get("level"))) or {"verdict": "run"})
    click_gate.consent_verdict({"name": "", "inForm": True, "isSubmit": True, "payment": True, "method": "post"})
    assert seen == [("payment.authorize", None)]
    assert voc.level_of("payment.authorize") == "critical"
