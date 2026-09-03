"""One widget order produces ONE mutation, and the boring ones never wait for a model (V2-567).

The measured session behind this (2026-09-03 19:01-19:03, operator's engine): «Cierra los mensajes» hit the
action map in **0.08 ms** — exact, silent, no model. «Cierra los contactos», five seconds later, had no entry,
fell to the model, took **3.4 s** (a trimmed-family retry included) and the model answered a CLOSE order by
calling `show_widget(mensajeria)`; contactos only closed because the close backstop rescued it. One order, two
mutations, and the operator asking why three open cards cannot be handled «linearly and precisely».

Three fixes, three guards here:
1. the seed table covers OPEN and CLOSE for EVERY card — measured before: close existed for 2 of 14 widgets;
2. a close order is never answered with a show (`show_contradicts_the_order`, applied in BOTH channels);
3. the fast close DECLINES when live work sits behind the widget — killing an errand is richer than hiding a
   card, so that turn belongs to the model.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo.actionmap import executor
from nucleo.actionmap.normalize import normalize
from nucleo.actionmap.store import SEEDS_DIR, _pack_entries
from nucleo.flash import router

ENGINE = Path(__file__).resolve().parents[3]


def _expanded(lang: str) -> dict[str, dict]:
    pack = json.loads((SEEDS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for e in _pack_entries(pack):
        out[normalize(e["phrase"])] = e["action"]
    return out


# ── 1 · the table covers every card, both directions ─────────────────────────────────────────────────────

def _catalog_ids() -> list[str]:
    return sorted(d.name for d in (ENGINE / "widgets").iterdir()
                  if d.is_dir() and not d.name.startswith("_") and (d / "manifest.json").exists())


def test_every_widget_card_has_a_deterministic_open_and_close():
    """The ratchet. Before V2-567 the close half covered 2 of 14 widgets, which is exactly how «cierra los
    contactos» ended up waiting 3.4 s for a model that then opened something else. A widget that ships
    without its open/close seed phrases re-opens that hole silently — so the catalog is walked, not trusted.
    An open counts as `show_widget` OR a view data-op (mensajeria's lenses bring the card up, executor rule)."""
    for lang in ("es", "en"):
        table = _expanded(lang).values()
        opened = {a.get("widget") for a in table if a.get("do") == "show_widget"}
        opened |= {a.get("widget") for a in table
                   if a.get("do") == "widget_data" and str(a.get("action", "")).startswith("show_")}
        closed = {a.get("widget") for a in table if a.get("do") == "close_widget"}
        missing_open = [w for w in _catalog_ids() if w not in opened]
        missing_close = [w for w in _catalog_ids() if w not in closed]
        assert not missing_open, f"[{lang}] widgets with NO deterministic open phrase: {missing_open}"
        assert not missing_close, f"[{lang}] widgets with NO deterministic close phrase: {missing_close}"


def test_the_sentences_from_the_session_now_hit_the_table():
    """The literal failures, replayed against the expanded pack (normalization included)."""
    t = _expanded("es")
    assert t[normalize("cierra los contactos")] == {"do": "close_widget", "widget": "contactos"}
    assert t[normalize("Muéstrame mis restaurantes favoritos.")] == {"do": "show_widget", "widget": "contactos"}
    assert t[normalize("Enséñame mis restaurantes favoritos.")] == {"do": "show_widget", "widget": "contactos"}
    assert t[normalize("muéstrame mi lista de restaurantes favoritos")] == {"do": "show_widget",
                                                                            "widget": "contactos"}
    # …and the one that already worked keeps working (same action, still one opinion per phrase).
    assert t[normalize("cierra los mensajes")] == {"do": "close_widget", "widget": "mensajeria"}


def test_one_phrase_one_opinion():
    """A phrase that expands from two places with two different actions is a coin toss at import order.
    The pack must hold ONE opinion per normalized phrase, per language."""
    for lang in ("es", "en"):
        pack = json.loads((SEEDS_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        seen: dict[str, str] = {}
        for e in _pack_entries(pack):
            ph = normalize(e["phrase"])
            a = json.dumps(e["action"], sort_keys=True)
            assert seen.get(ph, a) == a, f"[{lang}] {ph!r} maps to two different actions"
            seen[ph] = a


# ── 2 · a close order is never answered with a show ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Cierra los contactos.",              # the literal turn: the model answered it with show_widget(mensajeria)
    "cierra el reloj",
    "quita el temporizador",
    "podrías cerrar el reloj",
    "no abras nada, cierra los contactos",   # a NEGATED open licenses nothing
])
def test_a_close_order_licenses_no_show(text):
    assert router.show_contradicts_the_order(text)


@pytest.mark.parametrize("text", [
    "cierra los mensajes y enséñame la agenda",   # compound: the open verb licenses the show
    "cierra la agenda y pon el reloj",
    "muéstrame mis restaurantes favoritos",       # not a close at all
    "no cierres nada, enséñame la agenda",        # negated close → not a close order
])
def test_but_a_licensed_or_absent_close_keeps_its_show(text):
    assert not router.show_contradicts_the_order(text)


def test_both_channels_apply_the_guard():
    """V2-539's lesson, again: voice and probe are parallel implementations of the same decision, and a rule
    applied in one silently stops existing in the other — the probe carried this very rule IN PROSE while the
    voice channel executed the spurious show. Both must call the shared guard."""
    voice = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "show_contradicts_the_order" in voice, "the voice channel dropped the guard"
    assert "show_contradicts_the_order" in probe, "the probe channel dropped the guard"


# ── 3 · the fast close declines over live work ───────────────────────────────────────────────────────────

def _run(action, emits):
    return executor.execute(action, lambda kind, label, **kw: emits.append((kind, label, kw)))


def test_the_fast_close_declines_while_live_work_sits_behind_the_widget(monkeypatch):
    """Closing the browser card cancels its tab; closing the results card orphans the errand delivering into
    it. That is richer than «hide a card», so the fast lane declines (False = fall through to the model,
    which can warn or ask) and — crucially — declines WHOLE: no emit may have fired."""
    from widgets.navegador import tasks as nt
    monkeypatch.setattr(nt, "active_ids", lambda: ["t1"])
    emits: list = []
    assert _run({"do": "close_widget", "widget": "navegador"}, emits) is False
    assert emits == [], "the fast lane declined AFTER mutating — a half-executed fallthrough"

    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    assert _run({"do": "close_widget", "widget": "results"}, emits) is False
    assert emits == []


def test_and_closes_normally_when_nothing_is_running(monkeypatch):
    """The sensitivity check — without it, «declines over live work» and «never closes» measure the same."""
    from widgets.navegador import tasks as nt
    from nucleo import dispatch
    monkeypatch.setattr(nt, "active_ids", lambda: [])
    monkeypatch.setattr(dispatch, "has_active", lambda: False)
    for wid in ("navegador", "clock"):
        emits: list = []
        assert _run({"do": "close_widget", "widget": wid}, emits) is True
        assert [(k, l) for k, l, _ in emits] == [("widget", "close")]


def test_liveness_unreadable_means_the_model_decides(monkeypatch):
    """Fail-CLOSED: if the liveness cannot be read, the deterministic close declines rather than gambling —
    the wrong default here is a 0.08 ms kill of a five-minute errand."""
    from widgets.navegador import tasks as nt
    monkeypatch.setattr(nt, "active_ids", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    emits: list = []
    assert _run({"do": "close_widget", "widget": "navegador"}, emits) is False
    assert emits == []
