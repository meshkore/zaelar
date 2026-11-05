"""A worker's brief is its playbook and the catalogue's headlines, in the session's language, under a measured
ceiling; a family's full set comes on request through the bridge (V2-851 F3, §5, §6).

Measured before (2026-11-05, the composer with no memory and no conversation): hotel 24.8k chars, document 27.2k,
message 26.0k — every family written out whatever the task. After: hotel ≈16k WITH a research brief, document
10.2k, message 9.0k (es; en within 60 chars). The ceiling is the battery's (C11): a sample over it is a defect.
"""
from __future__ import annotations

import json

import pytest

from nucleo.workers.prompts import build, catalog, context, playbook, surfaces, web
from nucleo.workers.prompts.catalog import PROMPT_CEILING_CHARS

SAMPLES = {
    "hotel": {"es": "Búscame un hotel en Valencia para el próximo fin de semana, de menos de 120 euros la noche",
              "en": "Find me a hotel in Boston for next weekend, under 200 dollars a night"},
    "document": {"es": "Escríbeme un documento con un plan de tres días para visitar Lisboa",
                 "en": "Write me a document with a three-day plan to visit Lisbon"},
    "message": {"es": "Mándale un mensaje a Raquel diciéndole que llego a las ocho",
                "en": "Text Raquel that I'll be there at eight"},
}


@pytest.fixture
def lang(request, monkeypatch):
    from i18n import langs
    code = request.param
    monkeypatch.setattr(langs, "current_code", lambda: code)
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[code])
    for mod in (context, build, web):
        monkeypatch.setattr(mod, "_recent_conversation_block", lambda *a, **k: "")
    return code


def _research_brief():
    from nucleo.workers import brief
    return brief.parse(json.dumps({
        "research": True, "goal": "a hotel next weekend under the budget", "domain": "hotels",
        "hard": ["under budget per night", "next weekend", "in the city"], "soft": ["central", "good reviews"],
        "assumed": ["2 adults"], "breadth": {"min_candidates": 20}, "quality_bar": ["price confirmed"],
        "deliverable": {"widget": "results", "n_final": 3}}), request="x")


def _compose(name: str, req: str) -> tuple[str, str]:
    if name == "hotel":
        pb = playbook.which(request=req)
        return pb, web._web_prompt(req, "", _research_brief(), playbook=pb)
    surface, mandate = ("informe", None) if name == "document" else ("", {"channels": ["telegram"]})
    pb = playbook.which(surface=surface, mandate=mandate, request=req)
    return pb, build._build_prompt(req, "", True, None, playbook=pb) + surfaces.trusted_blocks(surface)


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
@pytest.mark.parametrize("name", list(SAMPLES))
def test_each_sample_brief_is_under_the_ceiling(lang, name):
    pb, prompt = _compose(name, SAMPLES[name][lang])
    assert pb == {"hotel": "errand", "document": "document", "message": "message"}[name]
    assert len(prompt) <= PROMPT_CEILING_CHARS, (name, len(prompt))


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
def test_disarmed_a_brief_with_every_family_written_out_is_over_it(lang, monkeypatch):
    """RED proof: the ceiling bites — the headlines replaced by the families' full sets put the hotel over it."""
    monkeypatch.setattr(catalog, "headlines", lambda skip=(): "\n\n".join(catalog.full(f) for f in catalog.FAMILIES))
    _pb, prompt = _compose("hotel", SAMPLES["hotel"][lang])
    assert len(prompt) > PROMPT_CEILING_CHARS


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
def test_the_brief_is_in_the_sessions_language(lang):
    _pb, prompt = _compose("message", SAMPLES["message"][lang])
    header = catalog.words("header")
    assert prompt.startswith("INTÉRPRETE") or header[:40] in prompt
    assert header[:40] in prompt
    assert ("THE METHOD" in prompt) == (lang == "en") and ("EL MÉTODO" in prompt) == (lang == "es")
    other = "es" if lang == "en" else "en"
    from i18n import langs
    assert str(langs.words("worker_brief.header", code=other))[:40] not in prompt


@pytest.mark.parametrize("lang", ["en"], indirect=True)
def test_the_playbook_states_done_when_and_that_the_worker_never_closes(lang):
    _pb, prompt = _compose("message", SAMPLES["message"]["en"])
    assert "DONE WHEN: " + playbook.done_when("message") in prompt
    assert "--option" in prompt and "END YOUR TURN" in prompt          # one question naming all the candidates
    assert "act verify" in prompt and "the engine does" in prompt       # verify asks; settle closes
    assert "at most 2 times" in prompt                                  # bounded by attempts


@pytest.mark.parametrize("lang", ["en"], indirect=True)
def test_the_headlines_name_every_family_once_and_not_its_full_set(lang):
    _pb, prompt = _compose("message", SAMPLES["message"]["en"])
    for fam in catalog.FAMILIES:
        assert prompt.count(f"  · {fam} — ") == 1, fam
    assert "SITIOS DE CONFIANZA" not in prompt and "PASO 0" not in prompt and "CÓMO CONDUCIR" not in prompt
    assert "SITIOS DE CONFIANZA" in catalog.full("sites") and "CÓMO CONDUCIR" in catalog.full("browser")


def test_which_playbook_reads_facts_never_words():
    assert playbook.which(surface="informe") == "document"
    assert playbook.which(mandate={"channels": ["email"]}) == "message"
    listed = ("Please do these for me this week:\n1. book the dentist for a cleaning on any morning after Tuesday\n"
              "2. call the plumber about the kitchen sink and ask for a quote before Friday\n"
              "3. buy oat milk, eggs, rice and coffee for the weekend from the usual supermarket\n"
              "4. renew the passport and check which documents the appointment needs\n"
              "5. send Anna the photos from the trip and remind her about the dinner on Saturday\n")
    assert playbook.which(request=listed) == "lista"
    assert playbook.which(request="find me a hotel in Boston") == "errand"


@pytest.mark.parametrize("lang", ["es"], indirect=True)
def test_a_list_gets_one_worker_walking_it_item_by_item(lang):
    block = playbook.block("lista", playbook.done_when("lista"))
    assert "UNA A UNA" in block and "UNA sola pregunta" in block
    assert "UNA A UNA" not in playbook.block("errand", playbook.done_when("errand"))


def test_the_row_records_its_playbook(monkeypatch):
    from types import SimpleNamespace
    from memory import tasks_store
    rows = {"u1": {"id": "u1"}}
    monkeypatch.setattr(tasks_store, "task_get", lambda uid: rows.get(uid))
    monkeypatch.setattr(tasks_store, "task_patch", lambda uid, **kw: rows[uid].update(kw))
    playbook.record(SimpleNamespace(uid="u1", task_id="t1"), "document")
    assert rows["u1"]["playbook"] == "document"


def test_the_bridge_serves_a_family_and_lists_them_for_an_unknown_one(capsys):
    from nucleo.cli import bridge
    assert bridge.main(["catalog", "schedule"]) == 0
    out = capsys.readouterr().out
    assert "act schedule" in out and "python -m nucleo." not in out.replace("/python -m nucleo.", "")
    assert bridge.main(["catalog", "nope"]) == 0
    listed = capsys.readouterr().out
    assert all(f in listed for f in catalog.FAMILIES)


def test_the_worker_start_event_carries_the_prompt_size(monkeypatch):
    from types import SimpleNamespace
    from nucleo.workers.session_notes import SessionNotes
    seen = {}
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, **kw: seen.update(kind=kind, **kw))
    me = SimpleNamespace(_rec=SimpleNamespace(task_id="t1", backend="claude", goal="g", kind="generic"),
                         _model="m", _spec=SimpleNamespace(model=""), _b=SimpleNamespace(name="claude"),
                         _prompt_chars=12345)
    SessionNotes._emit_meta_row(me)
    assert seen["kind"] == "worker_start" and seen["extra"]["prompt_chars"] == 12345


def test_a_declared_playbook_wins_over_the_inference():
    """An answered send escalates with `playbook: message` (V2-851 F2e); the inference must not overwrite it.
    Disarm: drop the `declared` branch in `which` and an answered send with no mandate reads as `errand`."""
    from nucleo.workers.prompts import playbook as pb
    assert pb.which(surface="", mandate=None, request="x", declared="message") == pb.MESSAGE
    assert pb.which(surface="", mandate=None, request="x", declared="nonsense") == pb.ERRAND


_ONCE = ("-m nucleo.cli.report plan", "-m nucleo.cli.report phase", "-m nucleo.cli.bridge ask")


@pytest.mark.parametrize("lang", ["es", "en"], indirect=True)
def test_the_web_brief_gives_each_bridge_once_and_the_browser_family_keeps_all(lang):
    """C11 (2026-11-05): the live hotel brief measured 16 538 chars, over the ceiling, and the report, phase and ask
    bridges were in it twice — once in the header and playbook, once again in the browser's driving lines. The brief
    gives each bridge once; the browser family's full set (`catalog browser`) still carries the driving lines whole."""
    _pb, prompt = _compose("hotel", SAMPLES["hotel"][lang])
    assert {b: prompt.count(b) for b in _ONCE} == dict.fromkeys(_ONCE, 1)
    family = catalog.full("browser")
    assert all(b in family for b in _ONCE) and "nucleo.cli.nav visit" in prompt


@pytest.mark.parametrize("lang", ["en"], indirect=True)
def test_disarmed_the_driving_lines_written_out_in_the_brief_say_a_bridge_twice(lang, monkeypatch):
    """RED proof: the brief composed with the full driving lines repeats the bridges."""
    real = web.driving_block
    monkeypatch.setattr(web, "driving_block", lambda py, **k: real(py))
    _pb, prompt = _compose("hotel", SAMPLES["hotel"][lang])
    assert any(prompt.count(b) > 1 for b in _ONCE)
