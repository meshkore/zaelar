"""V2-758 — «Cerebro rápido caído — turno degradado» was OUR bug, nine times, with the provider up.

Measured on the operator's engine, 2026-09-23 22:30–22:38 (sessions `c46c82bc`, `197ead04`): six alerts in the
timeline, every one of them carrying the literal text `flash layer error` and nothing else. The real cause was
in `server.log` and nowhere he could see it:

    nucleo fast brain error (not spoken raw): cannot access local variable '_cvis'
    where it is not associated with a value

`_cvis` is this repo's module alias for `nucleo.flash.canvas_visibility`. A local of the same name inside
`_on_tool_call` (the `connect_cluster` branch, there since V2-086) made the name LOCAL for the whole function,
so every earlier `_cvis.present(...)` — `show_images`, the music guard, the messaging guard — raised
`UnboundLocalError` before that line ever ran. Live since the alias arrived on 2026-09-18 (`91d60052`): five
days in which asking for a photo could not work.

Three consequences, all wrong, none visible:
  · the error handler treated it as the PROVIDER's, opening a cooldown on a healthy tier;
  · the panel painted the model, so the light accused DeepSeek while DeepSeek was answering;
  · the ladder relayed to the more expensive stand-in for a fault no stand-in can cure.

And the operator's own request in the same turn: «para eso tenemos un failover, para que **esa misma request
que ha fallado** se vuelva a enviar al otro modelo», plus «tiene que haber una cajita solo para el flash brain
… y también tiene que haber el modelo failover», plus the memory box «uno en rojo y otro en verde».
"""
from __future__ import annotations

import ast
import pathlib
import re
import symtable

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[3]


# ── A · THE CLASS OF BUG, NOT THE INSTANCE ───────────────────────────────────────────────────────────────────
# The instance is one renamed variable and would need no test. What earns one is the CLASS: a local that
# shadows a module-level import alias kills every earlier use of that module in the same scope, silently, and
# a source-anchored test cannot see it (the line `_cvis.present(...)` was written, present and correct — it
# just could not run). Measured engine-wide when this was written: TWO harmless shadows (both assigned before
# any use) and ZERO live ones, so the floor is zero and stays zero.
_ROOTS = ("nucleo", "voice", "memory", "server", "widgets", "connectors", "config", "i18n")


def _module_alias_shadows(path: pathlib.Path) -> list[tuple[str, str]]:
    """`(scope, name)` for every function whose LOCAL shadows a module-level import alias AND that reads the
    name before assigning it — i.e. every scope where the import is unreachable."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
        top = symtable.symtable(src, str(path), "exec")
    except SyntaxError:
        return []
    aliases = {a.asname or a.name.split(".")[0]
               for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    if not aliases:
        return []
    # symtable answers "is this name LOCAL to this scope", which is the question Python itself asks; nested
    # functions get their own scope, so an alias shadowed in a child does not incriminate the parent.
    local_scopes: list[tuple[str, symtable.SymbolTable, set[str]]] = []

    def walk(t, prefix=""):
        for ch in t.get_children():
            name = f"{prefix}.{ch.get_name()}" if prefix else ch.get_name()
            if ch.get_type() == "function":
                shadowed = {s.get_name() for s in ch.get_symbols()
                            if s.get_name() in aliases and s.is_assigned()
                            and not s.is_parameter() and not s.is_global()}
                if shadowed:
                    local_scopes.append((name, ch, shadowed))
            walk(ch, name)

    walk(top)
    if not local_scopes:
        return []
    # For each incriminated scope, compare the FIRST read against the FIRST write, in its OWN body only.
    by_name: dict[str, ast.AST] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            by_name.setdefault(fn.name, fn)
    bad = []
    for scope_name, _tbl, shadowed in local_scopes:
        fn = by_name.get(scope_name.split(".")[-1])
        if fn is None:
            continue
        for nm in shadowed:
            loads, stores = [], []
            for n in ast.walk(fn):
                if isinstance(n, ast.Name) and n.id == nm:
                    (stores if isinstance(n.ctx, ast.Store) else loads).append(n.lineno)
                elif isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        if (a.asname or a.name.split(".")[0]) == nm:
                            stores.append(n.lineno)
            if stores and any(l < min(stores) for l in loads):
                bad.append((scope_name, nm))
    return bad


def test_no_function_reads_a_module_alias_it_later_shadows():
    """The ratchet. A local that shadows an imported module makes every earlier use of it an
    `UnboundLocalError` — which reaches the operator as «Cerebro rápido caído» and accuses a healthy
    provider."""
    offenders = []
    for root in _ROOTS:
        for py in (ENGINE / root).rglob("*.py"):
            if "__pycache__" in str(py) or f"{pathlib.os.sep}_user{pathlib.os.sep}" in str(py):
                continue
            for scope, nm in _module_alias_shadows(py):
                offenders.append(f"{py.relative_to(ENGINE)}::{scope} reads «{nm}» before shadowing it")
    assert not offenders, (
        "a local shadows an imported module and the module is used BEFORE the assignment — every one of "
        "those uses raises UnboundLocalError at runtime:\n  " + "\n  ".join(offenders))


def test_the_cluster_branch_no_longer_shadows_the_canvas_alias():
    """The instance, named, so a future edit cannot quietly reintroduce it under the old name."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text()
    assert "canvas_visibility as _cvis" in src, "the alias this test is about is gone — re-aim the test"
    assert not re.search(r'^\s+_cvis = \(args\.get\("vis"\)', src, re.M), \
        "`_cvis` is assigned as a local again: `show_images` and the music/messaging guards are dead"
    assert '_cluster_vis = (args.get("vis")' in src, "the cluster visibility local lost its distinct name"


# ── B · WHOSE FAULT IS IT ────────────────────────────────────────────────────────────────────────────────────
class _WithStatus(Exception):
    def __init__(self, msg, status):
        super().__init__(msg)
        self.status_code = status


@pytest.mark.parametrize("exc,mine", [
    (UnboundLocalError("cannot access local variable '_cvis'"), True),
    (AttributeError("'NoneType' object has no attribute 'present'"), True),
    (TypeError("'int' object has no attribute 'strip'"), True),
    (KeyError("widget"), True),
    (RuntimeError("Error code: 402 - Insufficient Balance"), False),
    (_WithStatus("Too Many Requests", 429), False),
    (_WithStatus("bad gateway", 502), False),
    (Exception("connection error"), False),
    (None, False),
])
def test_only_our_own_programming_errors_count_as_an_engine_fault(exc, mine):
    """A provider failure arrives with an HTTP status; a bug of ours is a bare Python error. The status guard
    matters: an SDK may wrap a real 402 in a TypeError, and a 402 must never be excused as «our bug»."""
    from nucleo.flash import provider_failure as pf
    assert pf.is_engine_fault(exc) is mine, f"{type(exc).__name__ if exc else 'None'} misclassified"


def test_a_typeerror_carrying_an_http_status_is_still_the_providers():
    from nucleo.flash import provider_failure as pf
    e = TypeError("upstream said no")
    e.status_code = 503
    assert pf.is_engine_fault(e) is False


def test_the_engine_fault_line_names_the_defect():
    """«flash layer error» answered none of «tengo que saber qué pasa… identificarlo»."""
    from nucleo.flash import provider_failure as pf
    line = pf.engine_fault_line(UnboundLocalError("cannot access local variable '_cvis'"))
    assert "UnboundLocalError" in line and "_cvis" in line, line


def test_a_fault_of_ours_never_reaches_the_ladder():
    """The wiring, in the branch that runs BEFORE anything touches `provider_chain`."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text()
    i = src.index("if errored:")
    j = src.index("_v = {}", i)
    head = src[i:j]
    assert "is_engine_fault(err_exc)" in head, "the turn no longer asks whose fault it is before relaying"
    # NOTHING that touches the ladder may appear before the fault is attributed, and the branch must EXIT:
    # falling through is how a bug of ours opened a cooldown on a healthy tier for five days.
    assert "provider_chain" not in head and "_pfail.handle(" not in head, \
        "the ladder is consulted before the fault is attributed — a bug of ours would open a cooldown again"
    assert re.search(r"if _mine:(?:.|\n)*?\n                send\(", head), \
        "the engine-fault branch no longer speaks the ordinary stumble"
    assert head.rstrip().rstrip().endswith("return") or "\n                return\n" in head, \
        "the engine-fault branch must EXIT, not fall through into the provider path"


def test_the_degraded_alert_carries_the_real_error():
    """It travelled as the literal «flash layer error», so the timeline could not say why the brain fell."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text()
    m = re.search(r'emit\("alert", "Cerebro rápido caído — turno degradado\.",\s*\n\s*text=([^\n]+)', src)
    assert m, "the degraded alert is not where this test expects it"
    assert "err_text" in m.group(1), f"the alert still hides the cause: {m.group(1)}"


# ── C · THE SAME REQUEST GOES TO THE OTHER MODEL ─────────────────────────────────────────────────────────────
def test_the_relay_is_a_different_door_from_the_one_that_failed(monkeypatch):
    """«hay más posibilidades de que se caiga IML que que se caiga el proveedor original» — and a stand-in at
    the SAME endpoint is the decorative ladder `models.default.json` already warns about."""
    from nucleo.flash import fast_client as fc
    from nucleo.flash import provider_chain as pc
    from nucleo.flash.model_spec import ModelSpec

    tiers = [
        {"name": "titular", "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
         "provider": "deepseek", "api_key": "k1"},
        {"name": "relevo", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
         "provider": "openai", "api_key": "k2"},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=None: list(tiers))
    monkeypatch.setattr(pc, "tier_available", lambda t: True)
    monkeypatch.setattr(pc, "spec_for", lambda t: ModelSpec(model=t["model"], base_url=t["base_url"],
                                                            api_key=t["api_key"], provider=t["provider"]))
    here = ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="k1",
                     provider="deepseek")
    got = fc.relay_spec_for(here, pc.ROLE_VOICE)
    assert got is not None and got.model == "gpt-4.1-mini", "no relay was offered for a failing titular"
    assert got.resolved_base_url().rstrip("/") != here.resolved_base_url().rstrip("/"), \
        "the relay points at the SAME host as the titular: one outage takes both"


def test_there_is_no_relay_when_the_ladder_has_only_the_one_that_failed(monkeypatch):
    from nucleo.flash import fast_client as fc
    from nucleo.flash import provider_chain as pc
    from nucleo.flash.model_spec import ModelSpec
    tier = {"name": "titular", "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
            "provider": "deepseek", "api_key": "k1"}
    monkeypatch.setattr(pc, "chain", lambda role=None: [dict(tier)])
    monkeypatch.setattr(pc, "tier_available", lambda t: True)
    monkeypatch.setattr(pc, "spec_for", lambda t: ModelSpec(model=t["model"], base_url=t["base_url"],
                                                            api_key=t["api_key"], provider=t["provider"]))
    here = ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="k1",
                     provider="deepseek")
    assert fc.relay_spec_for(here, pc.ROLE_VOICE) is None, "it offered the tier that just failed as its own relay"


def test_a_tier_without_a_credential_is_not_a_relay(monkeypatch):
    """«sin credencial no es un escalón, es un espejismo» — relaying to it burns the turn for nothing."""
    from nucleo.flash import fast_client as fc
    from nucleo.flash import provider_chain as pc
    from nucleo.flash.model_spec import ModelSpec
    tiers = [
        {"name": "titular", "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
         "provider": "deepseek", "api_key": "k1"},
        {"name": "relevo", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
         "provider": "openai", "api_key": ""},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=None: list(tiers))
    monkeypatch.setattr(pc, "tier_available", lambda t: True)
    monkeypatch.setattr(pc, "spec_for", lambda t: ModelSpec(model=t["model"], base_url=t["base_url"],
                                                            api_key=t["api_key"] or None,
                                                            provider=t["provider"]))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    here = ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="k1",
                     provider="deepseek")
    assert fc.relay_spec_for(here, pc.ROLE_VOICE) is None


def _connect_loop_source() -> str:
    """The STREAMING connect loop only. `complete()` has a retry loop with the same opening comment, and
    anchoring on the first occurrence swallowed half the class — which is how a disarm of this very block came
    back green (the slice still contained an untouched `_extra_body_for` from somewhere else entirely)."""
    src = (ENGINE / "nucleo/flash/fast_client.py").read_text()
    i = src.index("# V2-758 — AND THE FAILOVER LIVES HERE FOR THE SAME REASON.")
    return src[i:src.index("calls: dict[int, dict] = {}", i)]


def test_the_failover_is_attempted_in_the_connect_phase_and_only_once():
    """Where it is matters: the connect phase is the one moment the provider has failed and nothing has been
    emitted, so re-sending costs no half-spoken sentence and no tool call fired twice."""
    body = _connect_loop_source()
    assert "relay_spec_for(spec, role)" in body, "the connect loop no longer asks for a stand-in"
    assert "_relayed = True" in body and "None if _relayed else" in body, \
        "nothing stops a second hop: the ladder could ping-pong inside one turn"


def test_the_relay_rebuilds_the_body_for_its_own_provider():
    """`thinking:disabled` is DeepSeek's and a 400 at OpenAI. Reusing the titular's body would make a healthy
    stand-in look broken — and would read, from outside, as «both rungs are down»."""
    body = _connect_loop_source()
    assert "_extra_body_for(spec)" in body, "the relay reuses the titular's provider-specific body"
    assert 'call_kwargs["model"] = spec.model' in body, "the relay would be called with the titular's model name"


def test_the_stream_never_relays_once_it_has_spoken():
    """A retry after a yielded chunk duplicates speech. The relay lives ONLY in the connect loop."""
    src = (ENGINE / "nucleo/flash/fast_client.py").read_text()
    after = src[src.index("calls: dict[int, dict] = {}"):]
    assert "relay_spec_for" not in after, \
        "a relay was wired into the streaming half: a mid-stream retry repeats what the operator already heard"


def test_a_relayed_turn_is_not_marked_against_the_titular_twice():
    """`fast_client` already attributed the failure on the way out. Re-marking from the voice handler would
    punish the titular for what the stand-in did — the silent mis-attribution V2-307 paid for."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text()
    i = src.index("_v = {}")
    body = src[i:src.index("# RELAY on a HARD failure", i)]
    assert 'relayed_to' in body, "the handler no longer asks whether the relay already happened"
    assert "if not (llm_metrics or {}).get(\"relayed_to\")" in body, \
        "the handler marks the ladder unconditionally again"


# ── D · THE PANEL SAYS WHO IS ANSWERING ──────────────────────────────────────────────────────────────────────
def _rows(monkeypatch, *, chain, serving, mem_status, mem_err=None, eng_err=None):
    """One `/api/status` render with the ladder and the memory heart stubbed."""
    from nucleo.flash import provider_chain as pc
    from nucleo import mem_processor
    from voice import health_state
    from server import voice_api
    monkeypatch.setattr(pc, "chain", lambda role=None: list(chain))
    monkeypatch.setattr(pc, "pick", lambda role=None: serving)
    monkeypatch.setattr(mem_processor, "status", lambda: dict(mem_status))
    monkeypatch.setattr(health_state, "get",
                        lambda svc: (mem_err if svc == "memory" else eng_err if svc == "engine" else None))
    import asyncio
    import inspect
    import json
    r = voice_api.status()
    if inspect.isawaitable(r):
        r = asyncio.run(r)
    return {it["key"]: it for it in json.loads(bytes(r.body).decode())["items"]}


_CH = [{"name": "titular", "model": "deepseek-flash", "provider": "deepseek",
        "base_url": "https://api.deepseek.com"},
       {"name": "relevo", "model": "gpt-4.1-mini", "provider": "openai",
        "base_url": "https://api.openai.com/v1"}]
_MEM_OK = {"model": "deepseek-flash", "url": "https://api.deepseek.com", "fail_streak": 0, "last_error": "",
           "last_ok_ts": 0.0, "degraded": False, "serving_model": "deepseek-flash",
           "serving_url": "https://api.deepseek.com", "relayed": False}


def test_the_flash_brain_box_names_its_primary_and_its_stand_in_while_healthy(monkeypatch):
    """«tiene que haber una cajita solo para el flash brain que se muestre que estamos llamando al v4 flash
    como principal, y también tiene que haber el modelo failover». Before this, the ladder was invisible until
    the day it had to work."""
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[0], mem_status=_MEM_OK)
    llm = rows["llm"]
    assert "FlashBrain" in llm["label"], f"the box is still called {llm['label']!r}"
    x = llm.get("extra") or {}
    assert x.get("titular", {}).get("model") == "deepseek-flash"
    assert x.get("titular_ok") is True
    assert x.get("standby", {}).get("model") == "gpt-4.1-mini", "the stand-in is not shown while healthy"


def test_a_stand_in_that_is_answering_paints_amber_even_with_the_light_clean(monkeypatch):
    """THE CASE THAT WAS INVISIBLE: once the stand-in answers, `fast_client` clears the model light on the
    first chunk, so the row went GREEN while the engine ran on the substitute. Who is answering is a fact
    about the ladder, not about whether an error is still fresh."""
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[1], mem_status=_MEM_OK)
    llm = rows["llm"]
    assert llm["state"] == "warn", f"a relayed engine reported {llm['state']!r} — amber is the point"
    x = llm["extra"]
    assert x["titular"]["model"] == "deepseek-flash" and x["serving"]["model"] == "gpt-4.1-mini"
    assert "standby" not in x, "it offers a stand-by while a stand-in is already serving"


def test_the_memory_box_shows_the_same_two_lines(monkeypatch):
    """«en la misma cajita donde pone memoria corazón tendríamos que poner el modelo principal y debajo el
    modelo secundario. Uno en rojo y otro en verde»."""
    relayed = dict(_MEM_OK, relayed=True, serving_model="gpt-4.1-mini",
                   serving_url="https://api.openai.com/v1")
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[0], mem_status=relayed)
    mem = rows["memory"]
    assert mem["state"] == "warn", f"a relayed heart reported {mem['state']!r} — «si fallaran los dos, " \
                                   "entonces sí que habría que marcarlo en rojo»"
    x = mem["extra"]
    assert x["titular"]["model"] == "deepseek-flash", x
    assert x["serving"]["model"] == "gpt-4.1-mini", x


def test_the_memory_box_names_its_stand_in_while_healthy(monkeypatch):
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[0], mem_status=_MEM_OK)
    x = rows["memory"].get("extra") or {}
    assert x.get("titular_ok") is True and x.get("standby", {}).get("model"), \
        "the memory ladder is invisible while it works"


def test_a_dead_heart_stays_RED_even_though_a_relay_would_be_amber(monkeypatch):
    """Amber is for a system that WORKS on its substitute. A heart writing by heuristics is not that."""
    dead = dict(_MEM_OK, degraded=True, fail_streak=3, relayed=True, serving_model="gpt-4.1-mini")
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[0], mem_status=dead)
    assert rows["memory"]["state"] == "error", "a heart writing by heuristics was downgraded to a warning"


def test_a_fault_of_ours_gets_its_own_row_and_only_when_there_is_one(monkeypatch):
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[0], mem_status=_MEM_OK)
    assert "engine" not in rows, "a permanently green «engine: fine» row is noise"
    rows = _rows(monkeypatch, chain=_CH, serving=_CH[0], mem_status=_MEM_OK,
                 eng_err={"kind": "bug", "text": "fallo interno del motor · UnboundLocalError: cannot "
                                                 "access local variable '_cvis'"})
    assert rows["engine"]["state"] == "error"
    assert "UnboundLocalError" in rows["engine"]["detail"], "the row does not name the defect"


def test_the_panel_draws_the_ladder_for_BOTH_rows():
    """One renderer, two rows. A second copy is how the two halves of a status row drift apart."""
    js = (ENGINE / "frontend/app/components/StatusPanel.js").read_text()
    assert 'it.key === "llm" || it.key === "memory"' in js, "the memory row lost its ladder renderer"
    assert "status.llm_titular_ok" in js, "the healthy primary has no line"
    assert 'h("div", { class: "st-detail" }, it.detail || "")' in js, \
        "the row's own detail was dropped again — «el recall no cerró en 0.8s» is the fact he needs"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_every_ladder_line_has_its_string(lang):
    import json
    b = json.loads((ENGINE / f"i18n/bundles/{lang}.json").read_text())
    for k in ("status.llm_titular_ok", "status.llm_titular_down", "status.llm_serving", "status.llm_standby"):
        assert b.get(k), f"{lang}: falta «{k}» — the panel would render a raw key"


# ── E · THE MEMORY HEART SAYS WHO WROTE ──────────────────────────────────────────────────────────────────────
def test_the_heart_reports_the_rung_that_actually_served(monkeypatch):
    """It has relayed since 2026-08-19 and nothing outside `process()` could see it: `status()` reported the
    configured titular whoever answered."""
    from nucleo import mem_processor as mp
    monkeypatch.setattr(mp, "_model", lambda: "deepseek-flash")
    monkeypatch.setattr(mp, "_url", lambda: "https://api.deepseek.com")
    monkeypatch.setattr(mp, "_served_rung", ("https://api.openai.com/v1", "gpt-4.1-mini"), raising=False)
    st = mp.status()
    assert st["model"] == "deepseek-flash", "the configured titular must stay readable as itself"
    assert st["serving_model"] == "gpt-4.1-mini" and st["relayed"] is True


def test_with_no_relay_the_heart_reports_itself(monkeypatch):
    from nucleo import mem_processor as mp
    monkeypatch.setattr(mp, "_model", lambda: "deepseek-flash")
    monkeypatch.setattr(mp, "_url", lambda: "https://api.deepseek.com")
    monkeypatch.setattr(mp, "_served_rung", None, raising=False)
    st = mp.status()
    assert st["serving_model"] == "deepseek-flash" and st["relayed"] is False


def test_the_heart_records_who_served_after_a_distillation():
    """The wiring: the global is set where the loop decides, not somewhere a refactor can drop it."""
    src = (ENGINE / "nucleo/mem_processor.py").read_text()
    assert 'globals()["_served_rung"] = _served' in src, "nothing publishes the rung that served"
    i = src.index('globals()["_served_rung"]')
    assert src.index("if not _served:") < i, "the rung is published before the loop knows there was one"


# ── F · EMBEDDINGS: THE FALL IS SAID, THE SPACE IS NOT SWAPPED ───────────────────────────────────────────────
def test_a_failing_embeddings_titular_turns_the_memory_amber(monkeypatch):
    """It fell silently: the writer deferred the vector and the reader went lexical, and the panel said
    «Memoria · CORAZÓN — deepseek-flash» with the semantic half of recall off."""
    from memory import embeddings as em
    from voice import health_state
    seen = {}
    monkeypatch.setattr(health_state, "record", lambda svc, kind, text="": seen.update(
        {"svc": svc, "kind": kind, "text": text}))
    monkeypatch.setattr(em, "_last_live_degraded", None, raising=False)
    em._report_live_outcome(degraded=True)
    assert seen.get("svc") == "memory" and seen.get("kind") == "degraded", seen
    assert "embeddings:" in seen.get("text", ""), seen


def test_the_amber_is_actually_WIRED_to_a_real_embedding_call(monkeypatch, tmp_path):
    """The function working proves nothing — V2-756's lesson is that a disarm has to bite the WIRING. Removing
    the call from `embed_batch` left every direct-call test green, so this one goes through the real entry
    point with the cloud titular refusing to answer, exactly as it did on his machine."""
    from memory import embeddings as em
    from voice import health_state
    seen = {}
    monkeypatch.setattr(health_state, "record", lambda svc, kind, text="": seen.update({"svc": svc, "t": text}))
    monkeypatch.setattr(em, "_backend", "cloud", raising=False)
    monkeypatch.setattr(em, "_forced", True, raising=False)          # no re-probe: this is not a resolution test
    monkeypatch.setattr(em, "_active_dim", 768, raising=False)
    monkeypatch.setattr(em, "_last_live_degraded", None, raising=False)
    monkeypatch.setattr(em, "_cloud_embed", lambda texts, timeout=None: None)
    out = em.embed_batch(["el operador vive en Barcelona"])
    assert len(out) == 1 and len(out[0]) == 768, "the caller must still get a vector — degrade, never raise"
    assert em.last_degraded is True, "the writer would insert a hash vector into the semantic index"
    assert seen.get("svc") == "memory" and "embeddings:" in seen.get("t", ""), \
        f"the fall reached nobody: {seen!r}"


def test_the_amber_is_written_once_not_on_every_single_embedding(monkeypatch):
    """This runs on every insert AND every query: re-recording an unchanged fact keeps refreshing its
    timestamp, so a stale amber could never age out of its TTL."""
    from memory import embeddings as em
    from voice import health_state
    calls = []
    monkeypatch.setattr(health_state, "record", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(em, "_last_live_degraded", None, raising=False)
    for _ in range(5):
        em._report_live_outcome(degraded=True)
    assert len(calls) == 1, f"the amber was rewritten {len(calls)} times"


def test_a_recovered_embedding_never_clears_somebody_elses_light(monkeypatch):
    """ONE LIGHT, FOURTEEN WRITERS. Clearing `memory` because OUR fact recovered wipes the heart's relay or
    REM's outage — the failure mode that made this row unreadable in the first place."""
    from memory import embeddings as em
    from voice import health_state
    cleared = []
    monkeypatch.setattr(health_state, "clear", lambda svc: cleared.append(svc))
    monkeypatch.setattr(health_state, "get",
                        lambda svc: {"kind": "degraded", "text": "destilador: relevo a gpt-4.1-mini"})
    monkeypatch.setattr(em, "_last_live_degraded", True, raising=False)
    em._report_live_outcome(degraded=False)
    assert cleared == [], "it took down the heart's amber while the heart was still on its stand-in"

    monkeypatch.setattr(health_state, "get",
                        lambda svc: {"kind": "degraded", "text": "embeddings: «x» no contestó — …"})
    monkeypatch.setattr(em, "_last_live_degraded", True, raising=False)
    em._report_live_outcome(degraded=False)
    assert cleared == ["memory"], "our own amber stayed up after the provider recovered"


def test_the_embeddings_row_still_declares_NO_stand_in():
    """THE ONE SERVICE WHERE A FAILOVER WOULD BE THE BUG. An embedding model defines the vector space every
    stored pill lives in, so a stand-in MODEL answers in coordinates nothing can be compared against. The
    operator asked for an embeddings failover in the same breath as the FlashBrain one; this test is the
    answer, and it fails loudly the day someone «fixes» the table."""
    import json
    tbl = json.loads((ENGINE / "config/models.default.json").read_text())
    row = tbl["services"]["embeddings"]
    assert row.get("failover") is None, \
        ("a stand-in was added to `embeddings`: unless it serves the EXACT same model, every vector it "
         "returns lands in a different space and recall degrades silently — re-embed first (memory/reembed.py)")
    assert "warning" in row and "FAILOVER" in row["warning"].upper(), \
        "the row lost the sentence that explains why it has no stand-in"


# ── G · THE FAILOVER ACTUALLY RUNS (behaviour, not a source anchor) ──────────────────────────────────────────
class _Delta:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _Choice:
    def __init__(self, content):
        self.delta = _Delta(content)
        self.finish_reason = None


class _Chunk:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = None


class _FakeStream:
    def __init__(self, pieces):
        self._pieces = list(pieces)

    def __aiter__(self):
        async def gen():
            for p in self._pieces:
                yield _Chunk(p)
        return gen()


def _fake_client(fail_urls: dict, seen: list):
    """A stand-in for the OpenAI client: raises for the endpoints in `fail_urls`, streams otherwise."""
    class _Completions:
        def __init__(self, url):
            self._url = url

        async def create(self, **kw):
            seen.append((self._url, kw.get("model"), tuple(sorted((kw.get("extra_body") or {}).keys()))))
            if self._url in fail_urls:
                err = RuntimeError(fail_urls[self._url])
                err.status_code = 402
                raise err
            return _FakeStream(["hola ", "Ricart"])

    class _Chat:
        def __init__(self, url):
            self.completions = _Completions(url)

    class _Client:
        def __init__(self, url):
            self.chat = _Chat(url)

    return _Client


def _wire(monkeypatch, *, failing: dict, seen: list):
    from nucleo.flash import fast_client as fc
    from nucleo.flash import provider_chain as pc
    from nucleo.flash.model_spec import ModelSpec
    tiers = [
        {"name": "titular", "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
         "provider": "deepseek", "api_key": "k1"},
        {"name": "relevo", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
         "provider": "openai", "api_key": "k2"},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=None: [dict(t) for t in tiers])
    monkeypatch.setattr(pc, "tier_available", lambda t: True)
    monkeypatch.setattr(pc, "spec_for", lambda t: ModelSpec(model=t["model"], base_url=t["base_url"],
                                                            api_key=t["api_key"], provider=t["provider"]))
    monkeypatch.setattr(fc, "_CONNECT_RETRIES", 0, raising=False)
    mk = _fake_client(failing, seen)
    monkeypatch.setattr(fc.FastClient, "_client_for",
                        lambda self, spec: mk(spec.resolved_base_url().rstrip("/")))
    return ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="k1",
                     provider="deepseek")


def test_the_request_that_failed_is_re_sent_to_the_other_model(monkeypatch):
    """His sentence, run: «para eso tenemos un failover, para que ESA MISMA REQUEST que ha fallado se vuelva a
    enviar al otro modelo». Before this the turn was simply lost and he had to repeat himself."""
    import asyncio
    from nucleo.flash import fast_client as fc
    seen: list = []
    spec = _wire(monkeypatch, failing={"https://api.deepseek.com": "Insufficient Balance"}, seen=seen)
    monkeypatch.setattr(fc, "_extra_body_for", lambda sp: ({"thinking": {"type": "disabled"}}
                                                           if "deepseek" in (sp.model or "") else {}))

    async def go():
        m: dict = {}
        out = []
        async for piece in fc.FastClient().stream([{"role": "user", "content": "hola"}], spec=spec, metrics=m):
            out.append(piece)
        return "".join(out), m

    text, m = asyncio.run(go())
    assert text == "hola Ricart", f"the relayed turn produced {text!r} — the request was not saved"
    assert [s[0] for s in seen] == ["https://api.deepseek.com", "https://api.openai.com/v1"], seen
    assert m.get("relayed_from") == "deepseek-flash" and m.get("relayed_to") == "gpt-4.1-mini", m


def test_the_relayed_call_carries_the_new_providers_body_not_the_titulars(monkeypatch):
    """`thinking:disabled` is DeepSeek's and a 400 at OpenAI — a stand-in called with the titular's body
    fails for a reason that has nothing to do with why the titular failed."""
    import asyncio
    from nucleo.flash import fast_client as fc
    seen: list = []
    spec = _wire(monkeypatch, failing={"https://api.deepseek.com": "Insufficient Balance"}, seen=seen)
    monkeypatch.setattr(fc, "_extra_body_for", lambda sp: ({"thinking": {"type": "disabled"}}
                                                           if "deepseek" in (sp.model or "") else {}))

    async def go():
        async for _ in fc.FastClient().stream([{"role": "user", "content": "hola"}], spec=spec, metrics={}):
            pass

    asyncio.run(go())
    first, second = seen[0], seen[1]
    assert first[1] == "deepseek-flash" and "thinking" in first[2], first
    assert second[1] == "gpt-4.1-mini", second
    assert "thinking" not in second[2], f"the stand-in was called with DeepSeek's body: {second}"


def test_when_both_rungs_fail_the_turn_raises_once_not_forever(monkeypatch):
    """One hop. Without `_relayed` the ladder could ping-pong inside a single turn."""
    import asyncio
    from nucleo.flash import fast_client as fc
    seen: list = []
    spec = _wire(monkeypatch, failing={"https://api.deepseek.com": "Insufficient Balance",
                                       "https://api.openai.com/v1": "Insufficient Balance"}, seen=seen)
    monkeypatch.setattr(fc, "_extra_body_for", lambda sp: {})

    async def go():
        async for _ in fc.FastClient().stream([{"role": "user", "content": "hola"}], spec=spec, metrics={}):
            pass

    with pytest.raises(Exception):
        asyncio.run(go())
    assert len(seen) == 2, f"the ladder was walked {len(seen)} times — one hop only"


def test_a_stream_that_already_spoke_is_never_re_sent(monkeypatch):
    """A retry after a yielded chunk repeats what the operator already heard, so the relay must NOT be reached
    from the streaming half. The stream connects fine and then dies mid-iteration: `create` must have been
    called exactly ONCE, and the chunk already emitted must have reached the caller."""
    import asyncio
    from nucleo.flash import fast_client as fc
    from nucleo.flash.model_spec import ModelSpec
    from nucleo.flash import provider_chain as pc
    calls: list = []

    class _Exploding:
        def __aiter__(self):
            async def gen():
                yield _Chunk("ya he dicho esto")
                err = RuntimeError("Insufficient Balance")
                err.status_code = 402
                raise err
            return gen()

    class _Completions:
        async def create(self, **kw):
            calls.append(kw.get("model"))
            return _Exploding()

    class _Client:
        chat = type("Ch", (), {"completions": _Completions()})()

    tiers = [
        {"name": "titular", "base_url": "https://api.deepseek.com", "model": "deepseek-flash",
         "provider": "deepseek", "api_key": "k1"},
        {"name": "relevo", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
         "provider": "openai", "api_key": "k2"},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=None: [dict(t) for t in tiers])
    monkeypatch.setattr(pc, "tier_available", lambda t: True)
    monkeypatch.setattr(pc, "spec_for", lambda t: ModelSpec(model=t["model"], base_url=t["base_url"],
                                                            api_key=t["api_key"], provider=t["provider"]))
    monkeypatch.setattr(fc.FastClient, "_client_for", lambda self, sp: _Client())
    monkeypatch.setattr(fc, "_extra_body_for", lambda sp: {})
    spec = ModelSpec(model="deepseek-flash", base_url="https://api.deepseek.com", api_key="k1",
                     provider="deepseek")

    spoken = []

    async def go():
        async for piece in fc.FastClient().stream([{"role": "user", "content": "hola"}], spec=spec, metrics={}):
            spoken.append(piece)

    with pytest.raises(Exception):
        asyncio.run(go())
    assert spoken == ["ya he dicho esto"], spoken
    assert calls == ["deepseek-flash"], \
        f"the request was re-sent after the operator had already heard part of it: {calls}"


def test_with_both_rungs_down_the_box_is_RED_and_promises_nobody(monkeypatch):
    """«si fallaran los dos, entonces sí que habría que marcarlo en rojo». And it must not still say «relevo
    listo» about a tier that is equally down — that is the panel telling him he is covered when he is not."""
    from nucleo.flash import provider_chain as pc
    from voice import health_state
    monkeypatch.setattr(pc, "tier_available", lambda t: False)
    rows = _rows(monkeypatch, chain=_CH, serving=None, mem_status=_MEM_OK,
                 mem_err=None)
    llm = rows["llm"]
    x = llm.get("extra") or {}
    assert x.get("titular_ok") is False, "the titular is drawn as if it were answering"
    assert "standby" not in x, "it still promises a stand-in that is also down"
    assert "serving" not in x, x
