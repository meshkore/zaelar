"""The 2026-08-18 incident: a worker started with the repo's developer context already loaded, blew its window in
under five minutes, and its raw provider error was delivered to the operator as if it were the report.

Reproduced here as a USE CASE from the real evidence (voice session `08f54c0c`, flow `T15·bcf7`) plus unit coverage
for each of the five pieces that failed. Every assertion below was verified failing before its fix.

The evidence, for whoever reads this next:
  · first API call: 122,833 input tokens BEFORE the worker did any work (~76k of it `engine/CLAUDE.md`)
  · death at 138,492 with `apiError: max_output_tokens` — NOT "context window", despite what the CLI's synthetic
    message said and what got read out loud to the operator
  · the model that actually ran was `glm-4.7`; the record said `claude-opus-4-8[1m]` and priced it as Opus
  · measured head-to-head afterwards: 167,242 tokens with the repo as cwd vs 25,352 in a scratch dir (-84.8%)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))))

from nucleo.workers import providers, workdir             # noqa: E402
from nucleo.workers.claude_session import _ctx_size       # noqa: E402
from nucleo.workers.session import (                      # noqa: E402
    SessionRecord, context_handoff, operator_safe_summary,
)

# The exact string the operator was told, verbatim from the durable log.
REAL_ERROR = "API Error: The model has reached its context window limit."


# ── 1. the failure is CLASSIFIED, and as its own family ───────────────────────────────────────────────────────
def test_the_real_incident_text_is_recognised_as_a_context_overflow():
    assert providers.is_context_overflow(REAL_ERROR)


def test_the_real_apiError_name_is_recognised_too():
    """The CLI's synthetic message says "context window"; the actual `apiError` was `max_output_tokens`. Matching
    only the friendly wording would miss the machine-readable one, which is the field a backend is likelier to
    surface."""
    assert providers.is_context_overflow("max_output_tokens")


@pytest.mark.parametrize("text", [
    "input length and `max_tokens` exceed context limit",
    "Prompt is too long: 210000 tokens > 200000 maximum",
    "This model's maximum context length is 200000 tokens",
])
def test_other_phrasings_of_the_same_wall(text):
    assert providers.is_context_overflow(text)


def test_a_context_overflow_is_NOT_a_provider_health_verdict():
    """The whole reason this is a separate family: putting it in `exhausted` would cool down a healthy tier and
    migrate the fault to the next one, which would blow up identically."""
    assert providers.classify_failure(REAL_ERROR) == ""


@pytest.mark.parametrize("quota", [
    "API Error: 429 [1310] Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-08-04",
    "429 Usage limit reached for 5 hour, too many tokens",
])
def test_a_quota_error_that_mentions_tokens_is_still_quota_not_overflow(quota):
    """Confusing the two would send us compacting when the right move is to relay providers."""
    assert not providers.is_context_overflow(quota)
    assert providers.classify_failure(quota) == "exhausted"


def test_an_ordinary_task_failure_is_neither():
    assert not providers.is_context_overflow("No pude encontrar la página")
    assert providers.classify_failure("No pude encontrar la página") == ""


# ── 2. the number that predicts death ─────────────────────────────────────────────────────────────────────────
def test_ctx_size_sums_the_three_counters_of_one_request():
    """The real usage line from the last message before death: `input_tokens` said 956 while the context was
    138,492. Watching only the fresh input is what made the ceiling invisible."""
    usage = {"input_tokens": 956, "cache_read_input_tokens": 137536, "cache_creation_input_tokens": 0,
             "output_tokens": 95}
    assert _ctx_size(usage) == 138492


def test_ctx_size_ignores_output_and_survives_junk():
    assert _ctx_size({"output_tokens": 9999}) == 0
    assert _ctx_size({"input_tokens": None, "cache_read_input_tokens": "x"}) == 0
    assert _ctx_size({}) == 0


# ── 3. a raw provider error is NEVER the report ───────────────────────────────────────────────────────────────
def test_the_operator_never_receives_the_raw_error_they_actually_received():
    out = operator_safe_summary(REAL_ERROR)
    assert out and out != REAL_ERROR
    assert "API Error" not in out
    assert "context window" not in out.lower()


def test_a_quota_error_is_also_translated():
    out = operator_safe_summary("API Error: 429 [1310] Weekly/Monthly Limit Exhausted")
    assert "API Error" not in out and "1310" not in out


def test_an_unclassified_api_error_is_still_not_delivered_verbatim():
    """The point of this gate: it must also catch the NEXT unforeseen provider message, not just the two we know."""
    out = operator_safe_summary("API Error: something nobody has seen before (777)")
    assert "API Error" not in out and "777" not in out


def test_a_real_report_passes_through_untouched():
    """A translation gate that eats real results would be worse than the bug it fixes."""
    real = "He encontrado 3 guitarras zurdas 3/4 con envío a Soria antes del 25."
    assert operator_safe_summary(real) == real


def test_empty_stays_empty_so_nothing_is_delivered():
    assert operator_safe_summary("") == ""
    assert operator_safe_summary("   ") == ""


# ── 4. compact and continue: the handoff carries progress, never the error ────────────────────────────────────
def _dead_record() -> SessionRecord:
    """The record as it stood when the real worker died."""
    rec = SessionRecord(task_id="1", goal="Busca una guitarra zurda infantil que llegue a Soria antes del 25")
    rec.plan = ["Buscar guitarras zurdas infantiles en tiendas online",
                "Verificar disponibilidad y plazos de entrega a Soria",
                "Comparar opciones con precio", "Presentar los resultados"]
    rec.done = 2
    rec.note = "I can see the shipping page. Let me search other Spanish stores"
    rec.steps = [{"action": "navigate", "target": "thomann.es/helpdesk_shipping.html"},
                 {"action": "navigate", "target": "amazon.es/s?k=guitarra+zurda"}]
    rec.considered = 7
    rec.kept = 2
    rec.result_summary = REAL_ERROR
    rec.ok = False
    rec.context_full = {"text": REAL_ERROR, "tokens": 138492}
    return rec


def test_the_handoff_carries_the_goal_and_what_was_already_done():
    brief = context_handoff(_dead_record())
    assert "guitarra zurda" in brief
    assert "2 de 4" in brief                      # progress through the plan
    assert "thomann.es" in brief and "amazon.es" in brief
    assert "7 candidatos" in brief


def test_the_handoff_NEVER_pastes_the_dead_workers_error_as_a_finding():
    """`result_summary` on this path holds the provider's error. Carrying it over would tell the fresh worker that
    its predecessor's error message was a research finding."""
    brief = context_handoff(_dead_record())
    assert "API Error" not in brief
    assert "context window" not in brief.lower()


def test_the_handoff_survives_a_record_that_reported_nothing():
    """A worker can die before narrating anything at all — then the goal alone has to be enough."""
    rec = SessionRecord(task_id="1", goal="Busca una guitarra zurda")
    brief = context_handoff(rec)
    assert "Busca una guitarra zurda" in brief
    assert brief.strip()


def test_the_handoff_tells_it_not_to_repeat_and_to_deliver_early():
    brief = context_handoff(_dead_record())
    assert "NO repitas" in brief and "ENTREGA" in brief


# ── 5. the confined workdir — the 85% of the incident ─────────────────────────────────────────────────────────
def test_research_kinds_get_their_own_directory_and_code_kinds_do_not():
    """A research worker has no business reading the engine's source or its developer notes; a `code`/`dev` worker's
    whole job IS the repository."""
    assert not workdir.needs_repo("web")
    assert not workdir.needs_repo("research")
    assert not workdir.needs_repo("generic")
    assert not workdir.needs_repo("memory")
    assert workdir.needs_repo("code")
    assert workdir.needs_repo("dev")


def test_the_workdir_is_outside_the_repo_and_carries_no_CLAUDE_md():
    """The entire fix: no CLAUDE.md anywhere above the worker's cwd."""
    engine_root = workdir._ENGINE_ROOT
    wd = workdir.for_task("test-ctx-budget")
    assert os.path.isdir(wd)
    assert not wd.startswith(engine_root), f"{wd} is inside the repo — the context bomb is back"
    assert not os.path.exists(os.path.join(wd, "CLAUDE.md"))


def test_the_engine_root_is_the_engine_root_and_not_a_subpackage():
    """This was a real bug caught by smoke-testing: the module lives one level deeper than the file whose pattern it
    copied, so two `dirname` calls pointed `PYTHONPATH` at `nucleo/` and `-m nucleo.nav_cli` stopped resolving —
    which would have left the worker with NO bridges at all, the very fault this module exists to prevent."""
    root = workdir._ENGINE_ROOT
    assert os.path.isdir(os.path.join(root, "nucleo")), f"{root} is not the engine root"
    assert os.path.isfile(os.path.join(root, "nucleo", "nav_cli.py"))


def test_each_task_gets_a_PRIVATE_directory_so_informe_json_stops_colliding():
    """Sharing the repo root meant every worker wrote the same relative `informe.json` — the guitar worker started
    with the PREVIOUS day's report auto-attached to its prompt."""
    a, b = workdir.for_task("task-alpha"), workdir.for_task("task-beta")
    assert a != b


def test_the_same_task_gets_the_SAME_directory_so_a_resumed_worker_finds_its_work():
    """V2-049 continuity: a resumed worker of the same management must land back where it wrote."""
    assert workdir.for_task("task-stable") == workdir.for_task("task-stable")


def test_a_task_id_with_path_characters_cannot_escape_the_root():
    wd = workdir.for_task("../../etc/passwd")
    assert os.path.dirname(os.path.abspath(wd)) == os.path.abspath(workdir._ROOT)


def test_pythonpath_puts_the_engine_first_and_keeps_what_was_already_there():
    """Assigning instead of prepending would silently drop an existing entry, because `spec.env` REPLACES keys when
    the backend merges it over `os.environ`."""
    env = workdir.env_for_task({"PYTHONPATH": "/already/here"})
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert parts[0] == workdir._ENGINE_ROOT
    assert "/already/here" in parts


def test_the_browser_data_dir_is_declared_as_a_read_dependency():
    """The vision path (V2-049) hands the worker an ABSOLUTE screenshot path outside its cwd.

    Deliberately NOT claiming this is what keeps that path working: verified live against the real CLI with
    production flags that an absolute read outside the cwd is already permitted. This asserts the DEPENDENCY is
    declared, so a future permission tightening surfaces as a failing test instead of a blind worker."""
    dirs = workdir.extra_dirs()
    assert dirs, "no read dirs → the worker cannot open its own screenshots"
    assert all(os.path.isabs(d) for d in dirs)
    assert any("navegador" in d for d in dirs)


# ── 6. the backend translates: real model, ctx size, and the right failure family ─────────────────────────────
def _map_all(objs: list[dict], *, spec_model: str = "claude-opus-4-8[1m]") -> list:
    """Feeds stream-json lines through the REAL `_map` of the real backend (no subprocess) and returns its
    WorkerEvents. Exercising production's own translator is the point: a test that reimplements the mapping can pass
    while production does something else."""
    from nucleo.workers.claude_session import ClaudeCodeSession
    s = ClaudeCodeSession()
    s._task_id = "1"
    s._model = spec_model
    out = []
    for o in objs:
        out.extend(list(s._map(o)))
    return out, s


def _assistant(model: str, usage: dict) -> dict:
    return {"type": "assistant", "message": {"model": model, "usage": usage,
                                             "content": [{"type": "text", "text": "buscando"}]}}


def test_the_backend_reports_the_model_that_actually_ran_not_the_alias_we_asked_for():
    """The record said `claude-opus-4-8[1m]`; the transcript says every assistant message was produced by
    `glm-4.7`. The panel lied about the model and the bill was priced at the alias's rate."""
    evs, s = _map_all([_assistant("glm-4.7", {"input_tokens": 956, "cache_read_input_tokens": 137536})])
    usage = [e for e in evs if e.type == "usage"]
    assert usage and usage[0].data["real_model"] == "glm-4.7"
    assert usage[0].data["model"] == "claude-opus-4-8[1m]", "the requested alias is kept for diagnosing config bugs"
    assert s._real_model == "glm-4.7"


def test_the_synthetic_label_is_never_mistaken_for_a_model():
    """`<synthetic>` is what the CLI stamps on messages IT fabricates — the error notice, for one. Taking it as the
    model would overwrite the real one right at the moment of death, when attribution matters most."""
    _, s = _map_all([
        _assistant("glm-4.7", {"input_tokens": 10}),
        {"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": REAL_ERROR}]}},
    ])
    assert s._real_model == "glm-4.7"


def test_the_backend_publishes_the_current_context_size_on_every_message():
    evs, s = _map_all([_assistant("glm-4.7", {"input_tokens": 956, "cache_read_input_tokens": 137536})])
    assert [e for e in evs if e.type == "usage"][0].data["ctx_tokens"] == 138492
    assert s._ctx_tokens == 138492


def test_a_blown_context_emits_context_full_and_NEVER_provider_down():
    """The distinction the whole fix rests on: nobody goes on cooldown for this. Relaying would migrate the fault to
    a tier that would blow up identically, and would take a working provider out of rotation on the way."""
    evs, _ = _map_all([
        _assistant("glm-4.7", {"input_tokens": 956, "cache_read_input_tokens": 137536}),
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": REAL_ERROR,
         "usage": {"input_tokens": 138175, "output_tokens": 2590}, "total_cost_usd": 2.2696},
    ])
    kinds = [e.type for e in evs]
    assert "context_full" in kinds
    assert "provider_down" not in kinds
    cf = [e for e in evs if e.type == "context_full"][0]
    assert cf.data["tokens"] == 138492


def test_a_real_quota_failure_still_emits_provider_down(monkeypatch):
    """The 2026-08-10 path must keep working — this fix adds a lane, it does not divert the existing one."""
    from nucleo.workers import providers as _prov
    monkeypatch.setattr(_prov, "note_failure", lambda text, tier: {"name": "moonshot"}, raising=False)
    evs, _ = _map_all([{"type": "result", "subtype": "error_during_execution", "is_error": True,
                        "result": "API Error: 429 [1310] Weekly/Monthly Limit Exhausted"}])
    kinds = [e.type for e in evs]
    assert "provider_down" in kinds
    assert "context_full" not in kinds


def test_the_result_carries_the_real_model_too():
    evs, _ = _map_all([
        _assistant("glm-4.7", {"input_tokens": 10}),
        {"type": "result", "subtype": "success", "result": "listo", "usage": {"input_tokens": 5}},
    ])
    res = [e for e in evs if e.type == "result"][0]
    assert res.data["real_model"] == "glm-4.7"


# ── 7. the session acts on it: ask for delivery, then compact and continue ─────────────────────────────────────
class _FakeBackend:
    """Minimal backend: replays a scripted event stream and RECORDS what was injected into it, which is the thing
    under test — the wrap-up turn goes over the same stdin channel `send_to_worker` uses."""
    name = "fake"

    def __init__(self, events):
        self._events = list(events)
        self.sent: list[str] = []

    async def start(self, prompt, *, spec):
        self._prompt = prompt

    async def events(self):
        for e in self._events:
            yield e

    async def send(self, text):
        self.sent.append(text)

    async def stop(self, *, grace=3.0):
        pass

    @property
    def alive(self):
        return True

    def native_session_id(self):
        return ""


def _ev(task_id, etype, **data):
    from nucleo.workers.base import WorkerEvent
    return WorkerEvent(task_id=task_id, type=etype, data=data)


def _run_session(monkeypatch, events, *, goal="Busca una guitarra zurda", escalate=None):
    """Drives a real `WorkerSession` over the fake backend with delivery/memory/escalation stubbed out, and returns
    (record, backend, escalations, delivered)."""
    import asyncio as _aio
    from nucleo.workers.session import SessionRecord, WorkerSession
    from nucleo.workers.base import WorkerSpec

    escalations: list[tuple] = []
    delivered: list[str] = []

    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None, raising=False)
    # `escalate` lets a caller make the retake FAIL. It has to be a parameter and not a second `setattr` by the
    # test, because this helper patches the same name — whichever ran last would silently win, which is exactly how
    # the first version of this file reported a pass while never exercising the failure branch at all.
    def _default_escalate(req, context=None):
        escalations.append((req, context or {}))
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain",
                        escalate or _default_escalate, raising=False)

    async def _fake_notify(title, text, **kw):
        delivered.append(text)
    monkeypatch.setattr("voice.proactive.notify", _fake_notify, raising=False)
    monkeypatch.setattr("voice.brain_notes.push", lambda t: None, raising=False)

    async def _fake_remember(p):
        return None
    monkeypatch.setattr("nucleo.memory_agent.remember", _fake_remember, raising=False)
    monkeypatch.setattr("nucleo.energy_meter.report_worker_usage", lambda **kw: None, raising=False)

    rec = SessionRecord(task_id="1", goal=goal)
    b = _FakeBackend(events)
    s = WorkerSession(b, WorkerSpec(task_id="1"), rec)
    _aio.run(s.run("prompt"))
    return rec, b, escalations, delivered


def test_nearing_the_ceiling_the_worker_is_asked_to_deliver_what_it_has(monkeypatch):
    """The preventive half. The number was already flowing past `session.py` and we only used it to bill the
    post-mortem; the session is ALIVE at that point, so we can just talk to it."""
    monkeypatch.setattr("nucleo.workers.session._CTX_BUDGET", 100000, raising=False)
    _, b, _, _ = _run_session(monkeypatch, [
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=50000),
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=120000),
        _ev("1", "result", summary="algo", ok=True, usage={"input_tokens": 10}),
        _ev("1", "done"),
    ])
    assert b.sent, "nobody asked the worker to wrap up before it hit the wall"
    assert "sin contexto" in b.sent[0] and "entrega" in b.sent[0].lower()


def test_the_wrap_up_is_asked_ONCE_not_on_every_message_past_the_budget(monkeypatch):
    """Repeating it would spend the little room that is left saying the same thing."""
    monkeypatch.setattr("nucleo.workers.session._CTX_BUDGET", 100000, raising=False)
    _, b, _, _ = _run_session(monkeypatch, [
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=120000),
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=130000),
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=135000),
        _ev("1", "done"),
    ])
    assert len(b.sent) == 1


def test_a_worker_well_under_the_budget_is_left_alone(monkeypatch):
    monkeypatch.setattr("nucleo.workers.session._CTX_BUDGET", 100000, raising=False)
    _, b, _, _ = _run_session(monkeypatch, [
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=30000),
        _ev("1", "result", summary="listo", ok=True, usage={"input_tokens": 10}),
        _ev("1", "done"),
    ])
    assert not b.sent


def test_a_blown_context_is_retaken_with_what_was_learned_and_delivers_no_error(monkeypatch):
    """The reactive half, and the operator's own requirement: compact and continue, never block the person with a
    provider error where their answer should be."""
    rec, _, escalations, delivered = _run_session(monkeypatch, [
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=138492),
        _ev("1", "context_full", text=REAL_ERROR, tokens=138492),
        _ev("1", "result", summary=REAL_ERROR, ok=False, usage={"input_tokens": 138175, "output_tokens": 2590}),
        _ev("1", "done"),
    ])
    assert rec.context_retried is True
    assert escalations, "the task was dropped instead of being retaken"
    req, ctx = escalations[0]
    assert "RETOMA" in req and "guitarra zurda" in req
    assert "API Error" not in req
    assert ctx.get("src") == "context_handoff"
    assert not delivered, "nothing is spoken: the fresh worker delivers, without noise in between"


def test_the_retake_happens_ONCE_so_it_cannot_loop(monkeypatch):
    """A retake that can retake itself is a way to burn a provider's quota in a loop."""
    rec, _, escalations, _ = _run_session(monkeypatch, [
        _ev("1", "context_full", text=REAL_ERROR, tokens=138492),
        _ev("1", "context_full", text=REAL_ERROR, tokens=139000),
        _ev("1", "result", summary=REAL_ERROR, ok=False, usage={}),
        _ev("1", "done"),
    ])
    assert len(escalations) == 1 and rec.context_retried is True


def test_if_the_retake_itself_fails_the_operator_is_TOLD_in_plain_language(monkeypatch):
    """Silence is the one outcome that is not allowed. And what gets said is prose, not the CLI's error."""
    def _boom(req, context=None):
        raise RuntimeError("bus down")
    _, _, _, delivered = _run_session(monkeypatch, escalate=_boom, events=[
        _ev("1", "context_full", text=REAL_ERROR, tokens=138492),
        _ev("1", "result", summary=REAL_ERROR, ok=False, usage={}),
        _ev("1", "done"),
    ])
    assert delivered, "the task died in total silence"
    assert "API Error" not in delivered[0]
    assert "contexto" in delivered[0]


def test_a_normal_successful_task_is_delivered_exactly_as_before(monkeypatch):
    """The counterweight: none of this may change the happy path."""
    rec, b, escalations, delivered = _run_session(monkeypatch, [
        _ev("1", "usage", usage={"input_tokens": 10}, ctx_tokens=20000),
        _ev("1", "result", summary="He encontrado 3 guitarras zurdas.", ok=True, usage={"input_tokens": 10}),
        _ev("1", "done"),
    ])
    assert rec.ok and rec.status == "done"
    assert delivered == ["He encontrado 3 guitarras zurdas."]
    assert not escalations and not b.sent
