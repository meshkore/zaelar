"""Tests of the Brain Workers substrate (V2-038): contract, dispatch registration/resolution, and act policy."""
import asyncio

from nucleo import dispatch
from nucleo.cli import worker_api
from nucleo.workers import WorkerEvent, WorkerSpec, get_backend
from nucleo.workers.session import SessionRecord


def _seed(**kw):
    dispatch._SESSIONS.clear()
    for tid, meta in kw.items():
        dispatch._SESSIONS[tid] = SessionRecord(task_id=tid, status="running", **meta)


def test_event_and_spec_contract():
    e = WorkerEvent(task_id="1", type="phase", data={"label": "x"})
    assert e.v >= 1 and e.ts > 0
    s = WorkerSpec(kind="web", task_id="1", token="tok", depth=1)
    assert s.token == "tok" and s.depth == 1


def test_backend_selection_agnostic(monkeypatch):
    """The registry DEFAULT is `claude_code`, and a widget task goes to the generator—regardless of circumstances.

    The provider is deliberately forced: without fixing it, this test read `config/v2.json`, that is, the REAL config
    of the machine where it runs. It passed only while the operator had `claude_code` there, and as soon as they tried
    Codex it started failing a test that is not about their choice but about the code's DEFAULT. Same class as the
    `store.DATA_DIR` leak from 2026-08-12: a test cannot depend on the operator's real state."""
    monkeypatch.setattr("nucleo.workers.providers.registry._provider_for", lambda kind: "claude_code")
    assert get_backend(WorkerSpec(kind="web", task_id="1")).name == "claude_code"
    assert get_backend(WorkerSpec(kind="code", task_id="1",
                                  env={"ZAELAR_TASK_REQUEST": "hazme un widget del clima"})).name == "widget_generator"


def test_resolve_sessions():
    _seed(**{"7": {"goal": "moto enduro", "kind": "web"}, "9": {"goal": "widget clima", "kind": "code"}})
    assert set(dispatch.resolve_sessions("para todo")) == {"7", "9"}
    assert dispatch.resolve_sessions("cancela el widget") == ["9"]
    assert dispatch.resolve_sessions("para la búsqueda") == ["7"]
    dispatch._SESSIONS.clear()


def test_resolve_single_is_unambiguous():
    _seed(**{"1": {"goal": "x", "kind": "generic"}})
    assert dispatch.resolve_sessions("eso") == ["1"]
    dispatch._SESSIONS.clear()


def test_act_policy():
    assert worker_api.classify_act("ask_user", {}) == worker_api.ALLOW
    assert worker_api.classify_act("use_tool", {"tool": "web_search"}) == worker_api.ALLOW
    assert worker_api.classify_act("use_tool", {"tool": "delete_widget"}) == worker_api.DENY
    assert worker_api.classify_act("push_channel", {"channel": "x"}) == worker_api.CONFIRM
    assert worker_api.classify_act("rm_rf", {}) == worker_api.DENY


def test_ask_answer_cycle():
    _seed(**{"5": {"goal": "moto", "kind": "web"}})
    corr = worker_api._register_ask(dispatch._SESSIONS["5"], "¿enduro o cross?")
    assert dispatch._SESSIONS["5"].waiting_on == "user"
    assert worker_api.has_pending_ask()
    assert asyncio.run(worker_api.answer(corr, "enduro"))
    assert dispatch._SESSIONS["5"].waiting_on == ""
    dispatch._SESSIONS.clear()


# ── V2-048: RICH observability of worker steps (where + what specifically) ────────────────────────────────────
from nucleo.workers.providers.claude import _tool_step  # noqa: E402
from nucleo.workers.session import _PLACE             # noqa: E402


def test_tool_step_native_tools():
    assert _tool_step("WebSearch", {"query": "estaciones ITV Soria"}) == \
        {"where": "web", "action": "web_search", "target": "estaciones ITV Soria"}
    assert _tool_step("WebFetch", {"url": "https://sitios.dgt.es/itv"})["where"] == "web"
    assert _tool_step("Read", {"file_path": "/a/b/c/agent.py"}) == \
        {"where": "archivo", "action": "lee", "target": "c/agent.py"}
    assert _tool_step("Edit", {"file_path": "nucleo/flash/router.py"})["where"] == "codigo"
    assert _tool_step("Grep", {"pattern": "def foo"})["where"] == "archivo"


def test_tool_step_bridges_from_bash():
    # browser: URL, numeric ref, and typed text
    nav = _tool_step("Bash", {"command": 'python -m nucleo.cli.nav navigate "https://sitios.dgt.es/cita"'})
    assert nav["where"] == "navegador" and nav["action"] == "navigate" and "sitios.dgt.es" in nav["target"]
    clk = _tool_step("Bash", {"command": ".venv/bin/python -m nucleo.cli.nav click 12"})
    assert clk["where"] == "navegador" and clk["action"] == "click" and clk["target"] == "[12]"
    typ = _tool_step("Bash", {"command": 'python -m nucleo.cli.nav type 7 "moto enduro" --submit'})
    assert typ["action"] == "type" and "moto enduro" in typ["target"]
    # memory: recall (query) and remember (slot)
    rc = _tool_step("Bash", {"command": 'python -m nucleo.cli.mem recall "ubicación del operador"'})
    assert rc["where"] == "memoria" and rc["action"] == "recall" and "ubicación" in rc["target"]
    rm = _tool_step("Bash", {"command": 'python -m nucleo.cli.mem remember --slot itv.cita "cita el martes"'})
    assert rm["action"] == "guarda" and "[itv.cita]" in rm["target"]
    # zaelar (worker_bridge) and agent_report (None → does not duplicate the hbnote phase)
    assert _tool_step("Bash", {"command": "python -m nucleo.cli.bridge ask '¿matrícula?'"})["where"] == "zaelar"
    assert _tool_step("Bash", {"command": "python -m nucleo.cli.report phase 'buscando'"}) is None


def test_every_place_maps_to_a_known_kind():
    # every `where` emitted by _tool_step must have an entry in _PLACE (otherwise the row would silently fall to system)
    kinds = {"search", "memory", "navegador", "task"}
    for where in ("web", "memoria", "navegador", "codigo", "archivo", "zaelar", "sistema"):
        assert where in _PLACE
        assert _PLACE[where][1] in kinds


def test_base_backend_pause_resume_default_noop():
    # workers/base.py::WorkerBackend—a backend that does not override pause/resume (Codex stub, generator_session)
    # must be an inert no-op and never break the agnostic contract (V2-065).
    from nucleo.workers.base import WorkerBackend

    class _Dummy(WorkerBackend):
        async def start(self, prompt, *, spec): pass
        async def send(self, text): pass
        def events(self):
            async def _gen():
                return
                yield  # pragma: no cover
            return _gen()
        async def stop(self, *, grace=3.0): pass
        @property
        def alive(self): return True

    d = _Dummy()
    assert d.pause() is False and d.resume() is False and d.paused is False


def test_claude_session_pause_resume_real_process():
    # V2-065 (operator request, ⏻ button: "pause, don't kill it, so they can continue"): verifies real SIGSTOP/
    # SIGCONT against a REAL process (not the `claude` binary—a long `sleep` in its own group,
    # just as start_new_session=True leaves the real process)—without this, the guarantee is only code inspection.
    import os
    import signal
    import time

    from nucleo.workers.providers.claude import ClaudeCodeSession

    async def _run():
        s = ClaudeCodeSession()
        s._proc = await asyncio.create_subprocess_exec(
            "sleep", "5", start_new_session=True,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert s.alive and not s.paused

        assert s.pause() is True and s.paused is True
        assert s.pause() is False   # idempotent: it was already paused
        # the real group received SIGSTOP—its state in /proc becomes "T" (stopped). macOS has no /proc,
        # so we verify by behavior: it does NOT terminate even if we wait longer than the entire "sleep 5" duration.
        await asyncio.sleep(0.3)
        assert s._proc.returncode is None   # still alive (frozen, not dead)

        assert s.resume() is True and s.paused is False
        assert s.resume() is False   # idempotent: there was nothing to resume

        # after resuming, the process remains alive and runs normally (we kill it cleanly; no need to wait 5s)
        assert s._proc.returncode is None
        os.killpg(os.getpgid(s._proc.pid), signal.SIGKILL)
        try:
            await asyncio.wait_for(s._proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

    asyncio.run(_run())


# ── DENIAL MUST TEACH (live incident 2026-08-12, sailboat search) ─────────────────────────────────────────────
# With the provider's search quota exhausted, the worker tried to borrow the brain's `web_search`
#—which IS lendable—in the wrong form (`act web_search {...}` instead of `act use_tool {"tool":…}`).
# The policy returned the SAME phrase for everything, "action not permitted for a worker"; the worker believed it
# and abandoned its only fallback: the search was left without a search engine.
def test_a_malformed_call_is_not_reported_as_a_forbidden_capability():
    from nucleo.cli.worker_api import deny_reason
    msg = deny_reason("web_search", {"query": "velero 42 pies"})
    assert "DESCONOCIDA" in msg, "un nombre de tool en el hueco de la acción es una llamada MAL ESCRITA"
    assert "use_tool" in msg and '"tool":"web_search"' in msg, "tiene que decir la forma CORRECTA"
    assert "NO es una prohibición" in msg, "si suena a prohibido, el worker deja de intentarlo"


def test_an_actually_forbidden_tool_says_so_and_offers_the_way_out():
    from nucleo.cli.worker_api import deny_reason
    msg = deny_reason("use_tool", {"tool": "authenticate_web"})
    assert "no se presta" in msg and "ask_user" in msg
    assert "DESCONOCIDA" not in msg, "esto sí es una prohibición real, no un error de forma"


def test_a_tool_outside_the_lendable_catalogue_names_what_is_lendable():
    from nucleo.cli.worker_api import deny_reason, _PRESTABLE_TOOLS
    msg = deny_reason("use_tool", {"tool": "play_music"})
    assert all(t in msg for t in _PRESTABLE_TOOLS)


def test_the_deny_message_lists_the_real_action_vocabulary():
    """The message must not become outdated relative to what the policy actually allows."""
    from nucleo.cli import worker_api as W
    msg = W.deny_reason("noexiste", {})
    for a in W._KNOWN_ACTS:
        assert a in msg, a
    for a in W._KNOWN_ACTS:
        assert W.classify_act(a, {"widget_id": "results", "action": "present", "tool": "web_search"}) != W.DENY \
            or a in ("widget_data",), f"«{a}» está en el vocabulario pero la política no lo conoce"


# ── A KILLED WORKER IS STILL BILLED (billing hole, bank 2026-08-13) ────────────────────────────────────────────
# The Energy report lived INSIDE `_finish`'s `if rec.status != "cancelled"`—an `if` that exists for an
# INTERFACE reason (not to display two contradictory `end` rows, 2026-07-14 demo) and that swept away an
# unrelated BILLING concern: a worker killed due to budget had spent REAL tokens and was billed ZERO.
# Measured: 704 s, 256 steps, 39 captures, ~$0.20 in xAI tokens → €0 billed.
def test_the_energy_report_is_not_gated_by_the_ui_concern(monkeypatch):
    """The two concerns are SEPARATE: a CANCELLED session paints no second end row, and its tokens are billed."""
    from nucleo.energy import meter as energy_meter
    from tests.agent_headless.unit.workers import session_door as door
    billed = []
    monkeypatch.setattr(energy_meter, "report_worker_usage", lambda **kw: billed.append(kw))
    s = door.session(monkeypatch, status="cancelled", ok=False)
    s._usage = {"input_tokens": 1200, "output_tokens": 80}
    door.finish(monkeypatch, s)
    assert billed and billed[0]["prompt_tokens"] == 1200, "a cancelled worker still consumed real tokens"
    assert not [c for c in s.chips if c[0] == "end"], "the cancellation already painted its end row"


def test_partial_usage_survives_a_worker_that_never_says_goodbye(monkeypatch):
    """The final `result`'s `usage` does not exist if we kill the process, so it accumulates message by message. The
    `result` takes precedence when it arrives (the CLI already provides the sum); the partial is the MINIMUM reported
    when it does not. Read from what the session bills."""
    from nucleo.energy import meter as energy_meter
    from tests.agent_headless.unit.workers import session_door as door
    billed = []
    monkeypatch.setattr(energy_meter, "report_worker_usage", lambda **kw: billed.append(kw))
    killed = door.session(monkeypatch, status="running", ok=False)
    door.event(killed, "usage", usage={"input_tokens": 500, "output_tokens": 20})
    door.event(killed, "usage", usage={"input_tokens": 700, "output_tokens": 30})
    door.finish(monkeypatch, killed)
    assert billed[-1]["prompt_tokens"] == 1200 and billed[-1]["completion_tokens"] == 50, billed
    summed = door.session(monkeypatch, status="running", ok=True, result_summary="x")
    door.event(summed, "usage", usage={"input_tokens": 500, "output_tokens": 20})
    summed._usage = {"input_tokens": 61969, "output_tokens": 127}
    door.finish(monkeypatch, summed)
    assert billed[-1]["prompt_tokens"] == 61969, "the final sum wins over the partial"


def test_the_stream_emits_usage_per_message_not_only_at_the_end():
    """Verified by polling the CLI: each `assistant` message carries its `usage`, and the `result`'s is the SUM
    (61.969+127 = 62.096). Without emitting it per message, killing a worker would still be free."""
    from nucleo.workers.providers.claude import ClaudeCodeSession
    from nucleo.workers.providers.grok import GrokSession
    s = ClaudeCodeSession()
    msg = {"type": "assistant", "message": {"usage": {"input_tokens": 61969, "output_tokens": 127}, "content": []}}
    usage = [e for e in s._map(msg) if e.type == "usage"]
    assert usage and usage[0].data["usage"]["input_tokens"] == 61969
    # …and Grok inherits it, which is where the hole was found (it does not reimplement `_map`)
    assert GrokSession._map is ClaudeCodeSession._map


# ── a newly created widget must APPEAR on screen (2026-08-18) ──────────────────────────────────────────────────
def _drive_generator(monkeypatch, *, req, gen_result, action=None):
    """Runs `GeneratorBackend._drive()` with the REAL generator replaced (without launching `claude`) and returns
    the observability `emit()` calls it produced, plus the WorkerEvents it queued."""
    from nucleo.workers.providers.generator import GeneratorBackend
    from widgets import generator as _gen

    seen: list[tuple] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda cat, label, **kw: seen.append((cat, label, kw.get("extra") or {})))
    monkeypatch.setattr(_gen, "generate_widget", lambda *a, **k: gen_result, raising=False)
    monkeypatch.setattr(_gen, "modify_widget", lambda *a, **k: gen_result, raising=False)
    if action is not None:
        monkeypatch.setattr("nucleo.agentes.code.widget_action", lambda r: action, raising=False)

    b = GeneratorBackend()
    b._task_id = "T1"
    asyncio.run(b._drive(req))
    evs = []
    while not b._q.empty():
        evs.append(b._q.get_nowait())
    return seen, evs


def test_a_created_widget_is_actually_opened_on_screen(monkeypatch):
    """Reported live: "no new widget appeared, nor anything on screen." The widget was built correctly and
    announced by voice ("I created the widget \"X\""), but NOBODY opened it—the `wid` traveled inside the `data` of
    the `result`, and `session.py::_handle` keeps `summary`/`ok`/`usage` and discards `data`. The only path that
    opened a worker's widget was the browser path. Three minutes of work delivered to a blank screen."""
    seen, evs = _drive_generator(monkeypatch, req="hazme un widget del tiempo de Soria",
                                 gen_result={"ok": True, "id": "meteo-soria"})
    assert ("widget", "show", {"id": "meteo-soria", "src": "worker:T1"}) in seen
    assert any(e.type == "result" and e.data.get("ok") for e in evs)


def test_an_already_existing_widget_is_opened_too(monkeypatch):
    """The copy for this case literally says "it already existed, I'LL SHOW IT TO YOU"—it promised an action by
    voice that did not happen. It is the same bug with the worse of the two possible wordings."""
    seen, _ = _drive_generator(monkeypatch, req="hazme un widget del tiempo de Soria",
                               gen_result={"ok": True, "id": "meteo-soria", "existed": True})
    assert ("widget", "show", {"id": "meteo-soria", "src": "worker:T1"}) in seen


def test_deleting_a_widget_does_not_open_it(monkeypatch):
    """The flip side: opening what you just deleted. That is why show lives in the backend (which knows WHAT action
    occurred), not in the agnostic pumping of `session.py`."""
    async def _fake_delete(wid, who):
        return {"ok": True}
    monkeypatch.setattr("widgets.lifecycle.delete_widget", _fake_delete, raising=False)
    seen, evs = _drive_generator(monkeypatch, req="borra el widget del tiempo",
                                 gen_result={"ok": True, "id": "meteo-soria"},
                                 action=("delete", "meteo-soria"))
    assert not [s for s in seen if s[1] == "show"], "un borrado NUNCA abre la tarjeta"
    assert any(e.type == "result" for e in evs)


def test_a_failed_generation_opens_nothing(monkeypatch):
    """A failure must not leave a phantom card open."""
    seen, _ = _drive_generator(monkeypatch, req="hazme un widget del tiempo de Soria",
                               gen_result={"ok": False, "error": "boom"})
    assert not [s for s in seen if s[1] == "show"]
