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
    ("¡Abre WhatsApp!", "show_widget"),
    ("abre el whatsapp", "show_widget"),
    ("Abre Telegram", "show_widget"),
    ("abre la agenda", "show_widget"),
    ("abre el calendario", "show_widget"),
    ("abre las alarmas", "show_panel"),
]

MUST_HIT_EN = [
    ("Clear the screen", "close_all"),
    ("clear screen", "close_all"),
    ("close all widgets", "close_all"),
    ("Open WhatsApp", "show_widget"),
    ("open the messages", "show_widget"),
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
        events.append({"kind": kind, "label": label, "extra": dict(extra or {})})

    return events, emit


def test_close_all_goes_through_the_widget_funnel(fresh_map, monkeypatch):
    _lang(monkeypatch, "es")
    events, emit = _collect()
    hit = actionmap.match("limpia la pantalla")
    assert actionmap.execute(hit, emit, phrase="limpia la pantalla") is True
    assert events == [{"kind": "widget", "label": "close", "extra": {"src": "actionmap"}}]


def test_show_widget_resolves_and_emits(fresh_map, monkeypatch):
    _lang(monkeypatch, "es")
    events, emit = _collect()
    hit = actionmap.match("abre el whatsapp")
    assert actionmap.execute(hit, emit, phrase="abre el whatsapp") is True
    ev = events[-1]
    assert (ev["kind"], ev["label"]) == ("widget", "show")
    assert ev["extra"]["id"] == "mensajeria" and ev["extra"]["src"] == "actionmap"


def test_panel_tab_emits_panel_event(fresh_map, monkeypatch):
    _lang(monkeypatch, "en")
    events, emit = _collect()
    hit = actionmap.match("open the crons")
    assert actionmap.execute(hit, emit) is True
    assert events == [{"kind": "panel", "label": "open", "extra": {"tab": "crons", "src": "actionmap"}}]


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
    for phrase in ("abre el whatsapp", "abre la agenda", "abre los procesos", "limpia la pantalla"):
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
