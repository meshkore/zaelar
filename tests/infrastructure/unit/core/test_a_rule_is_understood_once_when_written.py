"""V2-806 F3 — a spoken rule is understood ONCE, when it is written; code validates; no word table decides.

The class: three regex families read his sentence on every write (`consent._flags_for`, `style_policy._flags_for` and
`scope_of`, a removal guard) and a difflib guess removed «the rule that looks most like» what he said. Each knew the
phrasings someone remembered and nothing else, and one sentence landed in up to three stores. Now one structured
call answers `{op, rows, remove, doubt, say}` against the DECLARED vocabulary, code validates every field, and a
removal names an id. The model is replaced here by a scripted answer: what is measured is what the ENGINE does with
an answer — validate, store, scope, expire, remove by id, ask which, fall back — not the model's judgement.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

import rules
from nucleo import consent
from rules import shape

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    consent._reset_for_tests()
    yield
    consent._reset_for_tests()


def _answer(monkeypatch, plan: dict, calls: list | None = None):
    def chat(system, user):
        if calls is not None:
            calls.append(user)
        return "```json\n" + json.dumps(plan, ensure_ascii=False) + "\n```"
    monkeypatch.setattr(shape, "_chat", chat)


def _send(channel: str) -> str:
    return consent.class_policy(f"messaging.send_new@{channel}")


# ── one call, validated, stored where it was meant ───────────────────────────────────────────────────────

def test_one_call_writes_a_scoped_gate_and_the_repeat_back(monkeypatch):
    calls = []
    _answer(monkeypatch, {"op": "add", "say": "Entendido: te pregunto antes de mandar correos.",
                          "rows": [{"scope": "messaging/email/send_new", "kind": "gate", "key": "consent",
                                    "value": "ask", "except": [], "until": None}]}, calls)
    res = shape.write("pregúntame antes de mandar correos")
    assert len(calls) == 1, "ONE model call per rule written"
    assert "messaging/email" in calls[0] and "widget:agenda" in calls[0], "the vocabulary offered is declared data"
    assert [(r["scope"], r["key"], r["value"], r["text"]) for r in res["stored"]] == [
        ("messaging/email/send_new", "consent", "ask", "pregúntame antes de mandar correos")]
    assert _send("email") == "ask" and _send("whatsapp") == "allow", "his rule for email never reaches WhatsApp"
    from nucleo.flash import style_directive
    assert style_directive.repeat_back(res) == "Entendido: te pregunto antes de mandar correos."


def test_an_exception_and_a_style_knob_ride_one_answer(monkeypatch):
    _answer(monkeypatch, {"op": "add", "say": "ok", "rows": [
        {"scope": "messaging/*/send_new", "kind": "gate", "key": "consent", "value": "ask",
         "except": ["messaging/telegram"]},
        {"scope": "global", "kind": "pref", "key": "fillers", "value": "off"}]})
    shape.write("pregúntame antes de mandar mensajes salvo por Telegram, y sin muletillas")
    assert _send("email") == "ask" and _send("telegram") == "allow"
    from nucleo import style_policy
    assert style_policy.filler_mode() == "off", "a knob is a voice row whatever scope the answer gave it"


def test_an_answer_outside_the_declared_vocabulary_is_corrected_or_dropped(monkeypatch):
    _answer(monkeypatch, {"op": "add", "say": "ok", "rows": [
        {"scope": "messaging/fax/send_new", "kind": "gate", "key": "consent", "value": "never"},   # no such channel
        {"scope": "widget:nonexistent", "kind": "gate", "key": "consent", "value": "allow"},     # no such card
        {"scope": "messaging/email/send_new", "kind": "gate", "key": "consent", "value": "maybe"},
        {"scope": "voice", "kind": "pref", "key": "confirm_short_actions", "value": "sure"},
        {"scope": "payment/*/authorize", "kind": "gate", "key": "ask_at", "value": "critical"}]})
    stored = shape.write("una frase cualquiera")["stored"]
    got = {(r["scope"], r["key"], r["value"]) for r in stored}
    assert ("messaging/*/send_new", "consent", "never") in got, "an undeclared channel → the act on any channel"
    assert ("global", "consent", "allow") in got, "an undeclared card → the nearest declared ancestor"
    assert ("global", "ask_at", "critical") in got, "the level knob is global"
    assert not any(r["value"] == "maybe" for r in stored), "a gate value outside allow/ask/never is dropped"
    assert not any(r["key"] == "confirm_short_actions" for r in stored), "a knob value of the wrong type is dropped"


def test_until_is_resolved_by_the_clock(monkeypatch):
    _answer(monkeypatch, {"op": "add", "say": "ok", "rows": [
        {"scope": "messaging/*/send_new", "kind": "gate", "key": "consent", "value": "never", "until": "end_of_day"}]})
    row = shape.write("hoy no mandes nada sin mí")["stored"][0]
    end = time.localtime(row["until"])
    assert (end.tm_hour, end.tm_min) == (23, 59) and _send("email") == "never"
    assert rules.gate(rules.path(cls="messaging.send_new@email"), now=row["until"] + 1) == "allow"


# ── removal and listing are BY ID ────────────────────────────────────────────────────────────────────────

def _two_mail_rules():
    a = rules.add("messaging/email/send_new", "gate", "consent", "ask", text="pregúntame antes de mandar correos")
    b = rules.add("messaging/email", "pref", "note", "firma como R.", text="en los correos firma como R.")
    return a, b


def test_forgetting_a_rule_removes_the_id_the_answer_names(monkeypatch):
    a, b = _two_mail_rules()
    _answer(monkeypatch, {"op": "remove", "remove": [a["id"], "r_not_his"], "doubt": [], "say": "Hecho, olvidada."})
    res = shape.write("olvida la regla de pedirme permiso para los correos")
    assert [r["id"] for r in res["removed"]] == [a["id"]], "only an id of his rows is removable"
    assert rules.get(b["id"]) is not None and _send("email") == "allow"


def test_two_candidates_are_a_question_never_a_guess(monkeypatch):
    a, b = _two_mail_rules()
    _answer(monkeypatch, {"op": "remove", "remove": [], "doubt": [a["id"], b["id"]], "say": "¿Cuál de estas?"})
    res = shape.write("olvida la regla de los correos")
    assert res["removed"] == [] and rules.get(a["id"]) and rules.get(b["id"])
    from nucleo.flash import style_directive
    line = style_directive.repeat_back(res)
    assert "pregúntame antes de mandar correos" in line and "firma como R." in line, line


def test_what_rules_do_i_have_lists_his_rows(monkeypatch):
    _two_mail_rules()
    _answer(monkeypatch, {"op": "list", "say": "Tienes estas reglas"})
    from nucleo.flash import style_directive
    line = style_directive.repeat_back(shape.write("¿qué reglas tengo?"))
    assert line.startswith("Tienes estas reglas: ") and "firma como R." in line


# ── when nothing understands, nothing is guessed ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("answer", [None, "no json here", '{"op": "explode"}'])
def test_without_an_answer_the_sentence_is_kept_as_a_global_note(monkeypatch, answer):
    monkeypatch.setattr(shape, "_chat", lambda system, user: answer)
    res = shape.write("nunca envíes un correo sin preguntarme")
    assert [(r["scope"], r["kind"], r["key"]) for r in res["stored"]] == [("global", "pref", "note")]
    assert _send("email") == "allow", "no gate is written from a guess"


def test_his_name_or_how_to_address_him_is_not_a_rule(monkeypatch):
    _answer(monkeypatch, {"op": "none", "rows": [], "say": ""})
    assert shape.write("trátame de usted")["stored"] == []
    assert rules.all_rows(include_defaults=False) == [], "the treatment stays memory's slot, not a second copy"


# ── the handler: off the turn, once, and the session layer hands over ────────────────────────────────────

def test_the_handler_writes_off_the_turn_says_it_once_and_hands_the_session_back(monkeypatch):
    import asyncio
    from nucleo.flash import style_directive
    from voice import proactive
    said = []

    async def notify(title, text, **kw):
        said.append(text)
        return True
    monkeypatch.setattr(proactive, "notify", notify)
    _answer(monkeypatch, {"op": "add", "say": "Entendido: sin muletillas.",
                          "rows": [{"scope": "voice", "kind": "pref", "key": "fillers", "value": "off"}]})
    events = []

    class Brain:
        _directive = ""
    brain = Brain()
    emit = lambda *a, **k: events.append((a, k))  # noqa: E731
    style_directive.handle("sin muletillas", "sin muletillas, por favor", brain, emit)
    assert brain._directive == "sin muletillas", "obeyed at once, before the rows exist"

    async def _turn_end():      # the post-stream chain settles it: no identity verdict → a rule, written off the turn
        await style_directive.settle(brain, None, emit)
        await asyncio.gather(*list(style_directive._TASKS))
    asyncio.run(_turn_end())
    assert brain._directive == "" and said == ["Entendido: sin muletillas."]
    assert any("user rule guardada" in a[1] and k["extra"]["scope"] == "voice" for a, k in events)


def test_no_word_table_reads_a_rule_any_more():
    for rel, gone in (("nucleo/consent.py", "_flags_for"), ("nucleo/style_policy.py", "_flags_for"),
                      ("nucleo/style_policy.py", "def scope_of"), ("nucleo/flash/router_guards.py", "_RULE_REMOVAL_RE"),
                      ("rules/notes.py", "difflib"), ("connectors/catalog.py", "consent_keys_named")):
        assert gone not in (ENGINE / rel).read_text("utf-8"), f"{rel} still holds {gone}"
    assert not (ENGINE / "nucleo/flash/rule_scope.py").exists()
