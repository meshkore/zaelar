#
# test_a_known_phrase_skips_the_model.py — V2-539, the Phase-0 litmus encoded.
#
# The action map does ONE thing: an exact lookup of a whole normalized utterance against the active
# language's table of verified commands. These tests pin the four properties the design lives or dies by:
# (1) the seeded hits HIT (a seed pack that silently fails to load is a module born dead — so the hit
# tests go through the REAL import path, not a hand-built index); (2) everything that is not a verbatim
# command MISSES — negations, compounds, questions, novelty: when in doubt, the model; (3) a hit executes
# through the same emit funnel the model uses, with `src: actionmap` provenance; (4) one install, one
# language — the other pack's phrases do not exist at runtime.
#
# Run: .venv/bin/pytest tests/agent_headless/unit/actionmap/test_a_known_phrase_skips_the_model.py
#
import pytest

from memory import db as memdb
from nucleo import actionmap
from nucleo.actionmap import executor, store
from nucleo.actionmap.normalize import normalize

# `Settings.language` FREEZES `env("ZAELAR_LANGUAGE")` at the moment `voice.engine.core.config` is first
# imported — and `store.active_lang()` reaches it lazily (langs → config). If that first import happens
# inside a test that has monkeypatched the env to "es", the frozen default poisons the WHOLE process:
# after the patch is reverted, `langs.current_code()` keeps answering "es" and the suite-isolation guards
# (`test_the_language_is_the_products_own_default…`) go red in whatever file runs later — an
# order-dependent failure pointing at nothing of its own (measured 2026-09-03, V2-571's full sweep).
# Importing it HERE, at collection time with the suite's clean env, freezes the honest default.
import voice.engine.core.config  # noqa: F401  — freeze SETTINGS before any env monkeypatch


@pytest.fixture
def fresh_map(tmp_path, monkeypatch):
    """Isolated DB (the `get_db()` singleton trap: env BEFORE reset) + clean index cache per test."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.delenv("ZAELAR_ACTIONMAP", raising=False)
    memdb.reset_db()
    actionmap.invalidate()
    yield
    actionmap.invalidate()
    memdb.reset_db()


def _lang(monkeypatch, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    actionmap.invalidate()


# ── (1) the seeded hits HIT, through the real import path ────────────────────────────────────────────────

MUST_HIT_ES = [
    ("Limpia la pantalla.", "close_all"),
    ("vacía la pantalla", "close_all"),
    ("Despeja la pantalla", "close_all"),
    ("borra todos los widgets", "close_all"),
    ("¡Abre WhatsApp!", "widget_data"),          # a LENS of mensajeria, not a card of its own (V2-545)
    ("abre el whatsapp", "widget_data"),
    ("Abre Telegram", "widget_data"),
    ("Muéstrame ahora el Telegram", "widget_data"),
    ("enséñame el correo", "widget_data"),
    ("abre la agenda", "show_widget"),
    ("abre el calendario", "show_widget"),
    ("abre las alarmas", "show_panel"),
]

MUST_HIT_EN = [
    ("Clear the screen", "close_all"),
    ("clear screen", "close_all"),
    ("close all widgets", "close_all"),
    ("Open WhatsApp", "widget_data"),
    ("open the messages", "widget_data"),
    ("show me the telegram messages", "widget_data"),
    ("open the agenda", "show_widget"),
    ("open the crons", "show_panel"),
]


@pytest.mark.parametrize("phrase,do", MUST_HIT_ES)
def test_seeded_spanish_commands_hit(fresh_map, monkeypatch, phrase, do):
    _lang(monkeypatch, "es")
    hit = actionmap.match(phrase)
    assert hit is not None, f"{phrase!r} must be a direct hit"
    assert hit["action"]["do"] == do


@pytest.mark.parametrize("phrase,do", MUST_HIT_EN)
def test_seeded_english_commands_hit(fresh_map, monkeypatch, phrase, do):
    _lang(monkeypatch, "en")
    hit = actionmap.match(phrase)
    assert hit is not None, f"{phrase!r} must be a direct hit"
    assert hit["action"]["do"] == do


# ── (2) everything else MISSES: when in doubt, the model ─────────────────────────────────────────────────

MUST_MISS_ES = [
    "no abras el whatsapp",                                        # negation
    "no limpies la pantalla",                                      # negation of a seeded command
    "ponte a buscar un restaurante para hoy y abre el whatsapp",   # the operator's compound example
    "abre el whatsapp y dime si hay mensajes nuevos",              # compound — never partially served
    "abre el panel de mandos",                                     # novel target
    "que widgets tengo abiertos",                                  # question, not a command
    "me gustaria que en algun momento abrieras la agenda",         # indirect phrasing
]


@pytest.mark.parametrize("phrase", MUST_MISS_ES)
def test_non_verbatim_utterances_miss(fresh_map, monkeypatch, phrase):
    _lang(monkeypatch, "es")
    assert actionmap.match(phrase) is None, f"{phrase!r} must fall through to the model"


def test_one_install_one_language(fresh_map, monkeypatch):
    """With Spanish active, the English pack's phrases do not exist (V2-539 §3.2)."""
    _lang(monkeypatch, "es")
    assert actionmap.match("abre el whatsapp") is not None
    assert actionmap.match("clear the screen") is None


def test_disabled_row_stops_matching(fresh_map, monkeypatch):
    """The user's veto is a row edit and the index honors it — the WhatsApp-retarget scenario's first half."""
    _lang(monkeypatch, "es")
    hit = actionmap.match("abre el whatsapp")
    assert hit is not None
    memdb.get_db().execute("UPDATE action_map SET status='disabled' WHERE id=?", (hit["id"],))
    actionmap.invalidate()
    assert actionmap.match("abre el whatsapp") is None


def test_kill_switch_env_wins(fresh_map, monkeypatch):
    monkeypatch.setenv("ZAELAR_ACTIONMAP", "0")
    assert actionmap.enabled() is False


# ── (3) a hit executes through the SAME funnel, with provenance ─────────────────────────────────────────

def _collect():
    events = []

    def emit(kind, label, text="", role="", extra=None):
        events.append({"kind": kind, "label": label, "text": text, "extra": dict(extra or {})})

    return events, emit


def test_close_all_goes_through_the_widget_funnel(fresh_map, monkeypatch):
    _lang(monkeypatch, "es")
    events, emit = _collect()
    hit = actionmap.match("limpia la pantalla")
    assert actionmap.execute(hit, emit, phrase="limpia la pantalla") is True
    assert [(e["kind"], e["label"]) for e in events] == [("widget", "close")]
    assert events[0]["extra"]["src"] == "actionmap" and "id" not in events[0]["extra"]


def test_show_widget_resolves_and_emits(fresh_map, monkeypatch):
    _lang(monkeypatch, "es")
    events, emit = _collect()
    hit = actionmap.match("abre la agenda")
    assert actionmap.execute(hit, emit, phrase="abre la agenda") is True
    ev = events[-1]
    assert (ev["kind"], ev["label"]) == ("widget", "show")
    assert ev["extra"]["id"] == "agenda" and ev["extra"]["src"] == "actionmap"


def test_panel_tab_emits_panel_event(fresh_map, monkeypatch):
    _lang(monkeypatch, "en")
    events, emit = _collect()
    hit = actionmap.match("open the crons")
    assert actionmap.execute(hit, emit) is True
    assert [(e["kind"], e["label"]) for e in events] == [("panel", "open")]
    assert events[0]["extra"]["tab"] == "crons" and events[0]["extra"]["src"] == "actionmap"


def test_every_canvas_order_carries_the_phrase_that_caused_it(fresh_map, monkeypatch):
    """Operator rule (2026-08-09): the event carries the PHRASE. A close/move/panel without it forces a jump
    to the neighbouring transcript row to answer «what did I say to get this?»."""
    _lang(monkeypatch, "es")
    events, emit = _collect()
    for phrase in ("limpia la pantalla", "cierra la agenda", "abre los procesos"):
        hit = actionmap.match(phrase)
        assert hit is not None and actionmap.execute(hit, emit, phrase=phrase)
    texts = [e.get("text") for e in events]
    assert texts == ["limpia la pantalla", "cierra la agenda", "abre los procesos"]


def test_the_origin_is_stamped_on_every_event(fresh_map, monkeypatch):
    """Both surfaces (engine viewer + Master) read the ORIGIN off the event. Without it a mapped turn was
    painted «FlashBrain» / tagged «LLM» — the timeline claiming a model ran when none did."""
    _lang(monkeypatch, "es")
    events, emit = _collect()
    for phrase in ("abre la agenda", "limpia la pantalla", "abre el chat"):
        hit = actionmap.match(phrase)
        assert actionmap.execute(hit, emit, phrase=phrase)
    assert all(e["extra"].get("origin") == "actionmap" for e in events)
    assert all(e["extra"].get("src") == "actionmap" for e in events)


def test_unresolved_target_falls_through(fresh_map, monkeypatch):
    """execute() returning False is a ROUTING decision: the caller continues to the model."""
    events, emit = _collect()
    entry = {"id": 0, "action": {"do": "show_widget", "widget": "a-widget-that-does-not-exist"}}
    assert actionmap.execute(entry, emit) is False
    assert events == []


def test_a_chain_of_commands_is_n_lookups_zero_models(fresh_map, monkeypatch):
    """The operator's usage model: short commands separated by silences — each one a direct action."""
    _lang(monkeypatch, "es")
    events, emit = _collect()
    for phrase in ("abre el calendario", "abre la agenda", "abre los procesos", "limpia la pantalla"):
        hit = actionmap.match(phrase)
        assert hit is not None and actionmap.execute(hit, emit, phrase=phrase) is True
    assert [(e["kind"], e["label"]) for e in events] == [
        ("widget", "show"), ("widget", "show"), ("panel", "open"), ("widget", "close")]


# ── (4) the allowlist is CLOSED and the seed import is loud ─────────────────────────────────────────────

@pytest.mark.parametrize("action,why_hint", [
    ({"do": "delete_widget", "widget": "agenda"}, "unknown do"),
    ({"do": "task", "brief": "book me a table"}, "unknown do"),      # workflows: future scope (§7)
    ({"do": "show_widget"}, "missing widget"),
    ({"do": "show_panel", "tab": "secrets"}, "unknown tab"),
    ({"do": "move", "widget": "agenda", "where": "offscreen"}, "bad where"),
    ("close_all", "not an object"),
])
def test_the_allowlist_refuses_what_it_must(action, why_hint):
    assert executor.validate(action) != ""


def test_every_shipped_seed_entry_validates():
    import json
    for pack in sorted(store.SEEDS_DIR.glob("*.json")):
        entries = json.loads(pack.read_text(encoding="utf-8"))["entries"]
        assert entries, f"{pack.name}: empty pack"
        seen = set()
        for e in entries:
            phrase = normalize(e["phrase"])
            assert phrase and phrase not in seen, f"{pack.name}: dup/empty {e['phrase']!r}"
            seen.add(phrase)
            assert executor.validate(e["action"]) == "", f"{pack.name}: {e['phrase']!r}"


def test_a_bad_seed_is_refused_loudly_not_swallowed(fresh_map, monkeypatch, tmp_path):
    """The born-dead lesson: a refused seed raises an ALERT event and the good rows still load."""
    import json
    pack_dir = tmp_path / "seeds"
    pack_dir.mkdir()
    (pack_dir / "es.json").write_text(json.dumps({"entries": [
        {"phrase": "abre la agenda", "action": {"do": "show_widget", "widget": "agenda"}},
        {"phrase": "borra la agenda", "action": {"do": "delete_widget", "widget": "agenda"}},
    ]}), encoding="utf-8")
    monkeypatch.setattr(store, "SEEDS_DIR", pack_dir)
    alerts = []
    monkeypatch.setattr(store, "_emit", lambda kind, label, **kw: alerts.append((kind, label)))
    _lang(monkeypatch, "es")
    assert actionmap.match("abre la agenda") is not None
    assert actionmap.match("borra la agenda") is None
    assert any(k == "alert" for k, _ in alerts), "a refused seed must ALERT"


# ── the WATCH half: what the map is MISSING (V2-539 quality signal) ─────────────────────────────────────

def _decision(**kw):
    base = {"escalated": False, "searched": False, "widget_acted": False, "worker_acted": False,
            "data_done": False, "confirm_opened": False, "clarify": False, "shown_ids": [], "reply": ""}
    base.update(kw)
    return base


def test_a_pure_single_action_model_turn_is_a_candidate():
    from nucleo.actionmap.watch import _candidate_reason
    assert _candidate_reason(_decision(widget_acted=True, shown_ids=["mensajeria"])) == "canvas:show:mensajeria"
    assert _candidate_reason(_decision(widget_acted=True)) == "canvas:close"


@pytest.mark.parametrize("decision", [
    _decision(widget_acted=True, escalated=True),                       # it needed a worker
    _decision(widget_acted=True, searched=True),                        # it needed the web
    _decision(widget_acted=True, data_done=True),                       # it changed data, not just the canvas
    _decision(widget_acted=True, confirm_opened=True),                  # it asked before acting
    _decision(widget_acted=True, clarify=True),                         # it asked WHICH one
    _decision(widget_acted=True, shown_ids=["a", "b"]),                 # two targets, not one entry's job
    _decision(widget_acted=True, reply="Claro, te cuento: en la bandeja tienes tres mensajes de ayer y uno de hoy"),
    _decision(reply="pura charla"),                                     # no action at all
    _decision(widget_acted=True, actionmap=14),                         # the map already served it: a HIT
])
def test_turns_that_needed_understanding_are_not_candidates(decision):
    from nucleo.actionmap.watch import _candidate_reason
    assert _candidate_reason(decision) == ""


# ── the PROBE channel writes a different decision shape through the same seam ───────────────────────────

def _probe(**kw):
    base = {"action": "chat", "tool_calls": [], "tags": [], "reply": ""}
    base.update(kw)
    return base


def test_the_probe_channels_own_shape_is_understood():
    """Caught LIVE: «muéstrame la mensajería» resolved to one show_widget and produced NO candidate — the
    reader knew only the voice provider's flags, so the channel the use-case platform drives was invisible."""
    from nucleo.actionmap.watch import _candidate_reason
    assert _candidate_reason(_probe(action="canvas:show:mensajeria",
                                    tool_calls=["show_widget"])) == "canvas:show:mensajeria"
    assert _candidate_reason(_probe(action="canvas:close")) == "canvas:close"


@pytest.mark.parametrize("decision", [
    _probe(action="escalate", tool_calls=["escalate_to_slowbrain"]),
    _probe(action="search", tool_calls=["web_search"]),
    _probe(action="chat", reply="pura charla"),
    _probe(action="canvas:show:mensajeria", tool_calls=["show_widget", "web_search"]),
    _probe(action="canvas:show:mensajeria",
           reply="Claro, te cuento: en la bandeja tienes tres mensajes de ayer y uno de hoy"),
    _probe(action="canvas:show:mensajeria", actionmap=14),      # the map already served it
])
def test_probe_turns_that_did_more_than_open_a_card_are_not_candidates(decision):
    from nucleo.actionmap.watch import _candidate_reason
    assert _candidate_reason(decision) == ""


# ── the observability contract: both surfaces must know the kind (the two-surfaces rule) ────────────────

def test_the_engine_classifies_the_actionmap_kind():
    """An unmapped kind is always-visible by design, but unclassified: it would fall outside the FlashBrain
    family filter, which is where an operator looks for turn routing."""
    from voice.observer import _CAT
    assert _CAT.get("actionmap") == "flash"


# ── wiring guards: BOTH channels call the shared module (the parallel-impl rule) ─────────────────────────

@pytest.mark.parametrize("path", [
    "voice/engine/llm/providers/nucleo.py",
    "nucleo/flash/probe.py",
])
def test_both_channels_are_wired(path):
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    src = (root / path).read_text(encoding="utf-8")
    assert "from nucleo import actionmap" in src, f"{path}: action map not wired"


# ── (5) the lens grid, and a pack that can be UPGRADED (V2-545) ──────────────────────────────────────────

def test_the_lens_grid_covers_the_phrasings_that_failed_live(fresh_map, monkeypatch):
    """The three utterances that got «Aquí lo tienes» over an unmoved card, and the one that worked. All
    four are the same order and now resolve to the same action, before any model runs."""
    _lang(monkeypatch, "es")
    for phrase, platform in (("Ábreme el Telegram.", "telegram"),
                             ("Muéstrame ahora el Telegram.", "telegram"),
                             ("Ábreme el WhatsApp.", "whatsapp"),
                             ("Muéstrame solo los mensajes de WhatsApp.", "whatsapp"),
                             ("Enséñame el correo.", "email"),
                             ("Muéstrame la lista principal.", "all")):
        hit = actionmap.match(phrase)
        assert hit is not None, f"{phrase!r} must be a direct hit"
        assert hit["action"]["action"] == "show_view"
        assert hit["action"]["payload"]["platform"] == platform, phrase


def test_a_lens_order_shows_the_card_too(fresh_map, monkeypatch):
    """«Ábreme el WhatsApp» is one order with two halves. Applying the lens to a card nobody can see would
    be the mirror of the bug this replaces. Needs a running loop: the data half is dispatched on it, and
    without one the whole action falls through to the model rather than half-executing."""
    import asyncio
    _lang(monkeypatch, "es")
    events, emit = _collect()

    async def go():
        hit = actionmap.match("ábreme el whatsapp")
        return actionmap.execute(hit, emit, phrase="ábreme el whatsapp")

    assert asyncio.run(go()) is True
    assert [(e["kind"], e["label"]) for e in events] == [("widget", "show")]
    assert events[0]["extra"]["id"] == "mensajeria"


def test_a_view_op_without_a_loop_falls_through_WHOLE(fresh_map, monkeypatch):
    """Half-executing is worse than not executing: the card must not be shown by an action that then
    reports False and hands the same turn to the model."""
    _lang(monkeypatch, "es")
    events, emit = _collect()
    hit = actionmap.match("ábreme el whatsapp")
    assert actionmap.execute(hit, emit, phrase="ábreme el whatsapp") is False
    assert events == [], "no emit may escape an action that did not execute"


def test_a_better_pack_reaches_an_already_seeded_install(fresh_map, monkeypatch):
    """The upgrade path that did not exist: `ensure_seeded` imported once per INSTALL, so every engine that
    had booted kept the phrases of its first day. Now it imports once per PACK VERSION, adds what is new and
    retargets a shipped phrase whose action changed."""
    import json

    from memory import api as _mapi
    _lang(monkeypatch, "es")
    assert actionmap.match("abre la agenda") is not None            # current pack imported by the fixture
    # The SHIPPED version, read from the pack rather than pinned: this test is about the upgrade PATH, and a
    # pinned literal turned every legitimate pack bump (v3: the V2-567 open/close grids) into a red herring.
    _shipped = int(json.loads((store.SEEDS_DIR / "es.json").read_text(encoding="utf-8"))["version"])
    assert _mapi.action_map_seed_version("es") == _shipped

    old = json.dumps({"do": "show_widget", "widget": "mensajeria"}, ensure_ascii=False)
    assert _mapi.action_map_retarget_seed("es", "abre el whatsapp", old) is True   # pretend it is a v1 row
    _mapi.action_map_set_seed_version("es", 1)
    from memory import db as _db
    row = _db.get_db().query_one("SELECT action FROM action_map WHERE lang='es' AND phrase='abre el whatsapp'")
    assert "show_widget" in row["action"], "the install now looks like one seeded by the older pack"

    store.ensure_seeded("es")                                        # the upgrade
    actionmap.invalidate()
    assert actionmap.match("abre el whatsapp")["action"]["do"] == "widget_data"
    assert _mapi.action_map_seed_version("es") == _shipped


def test_an_upgrade_never_moves_what_the_operator_touched(fresh_map, monkeypatch):
    """A phrase the operator disabled, or one the map LEARNED, is theirs: the veto survives every pack."""
    import json

    from memory import api as _mapi
    from memory import db as _db
    _lang(monkeypatch, "es")
    body = json.dumps({"do": "close_all"}, ensure_ascii=False)
    _db.get_db().execute("UPDATE action_map SET status='disabled' WHERE lang='es' AND phrase='abre el whatsapp'")
    assert _mapi.action_map_retarget_seed("es", "abre el whatsapp", body) is False
    _mapi.action_map_add("es", "una frase mia", body, source="learned")
    assert _mapi.action_map_retarget_seed("es", "una frase mia", json.dumps({"do": "show_widget", "widget": "agenda"})) is False


def test_the_probe_channel_runs_the_action_when_asked_to_execute():
    """The probe reported the mapped action and never ran it — correct while the map only spoke canvas verbs
    (a show is meaningless headless), wrong the day it could drive a widget's DATA: a lens change reported but
    not made is a decision the product does not take. A dry run still only reports."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "nucleo" / "flash" / "probe.py").read_text(encoding="utf-8")
    i = src.index("from nucleo import actionmap as _amap")
    window = src[i:i + 900]
    assert "_amap.execute(" in window, "the probe must RUN the mapped action, not only describe it"
    assert "and execute" in window, "and only when the caller asked for execution — a dry run stays dry"
    assert "_amap_hit = None" in window, \
        "an action that could not run must fall through to the model, like the voice rail's `and execute(...)`"
