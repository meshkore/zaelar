"""FlashBrain conversational stability safeguards (V2-032). Deterministic, model-free → fast in CI.

Covers blocker #1 from the 2026-07-12 report: repetition/negation loops and text degeneration in the
small model. Run: .venv/bin/pytest tests/agent_headless/unit/flash/test_dialog.py
"""
from nucleo.flash import dialog


# ── output anti-degeneration ─────────────────────────────────────────────────────────────────────────────
def test_sanitize_collapses_repeated_phrase():
    assert dialog.sanitize_reply("Déjame comprobar Déjame comprobar") == "Déjame comprobar"


def test_sanitize_collapses_duplicate_sentences():
    assert dialog.sanitize_reply("No tengo acceso. No tengo acceso.") == "No tengo acceso."


def test_sanitize_collapses_word_run():
    assert dialog.sanitize_reply("hola hola hola tío") == "hola tío"


def test_sanitize_leaves_normal_text():
    good = "Claro, te lo miro ahora mismo."
    assert dialog.sanitize_reply(good) == good


def test_looks_degenerate_flags_splice_only():
    assert dialog.looks_degenerate("Déjame comprobar Déjame comprobar") is True
    assert dialog.looks_degenerate("Vale, ¿qué necesitas?") is False


# ── break-loop ──────────────────────────────────────────────────────────────────────────────────────────
def _win(*replies):
    w = []
    for i, r in enumerate(replies):
        w.append({"role": "user", "content": f"u{i}"})
        w.append({"role": "assistant", "content": r})
    return w


def test_loop_detected_on_near_identical_replies():
    w = _win("No encuentro precios ahora", "No encuentro precios ahora mismo")
    assert dialog.repeated_replies(w) >= 2
    assert dialog.loop_nudge(w) != ""
    assert "ROMPE EL BUCLE" in dialog.loop_nudge(w)


def test_no_loop_on_varied_replies():
    w = _win("Hola Alex", "¿Qué tal el efoil?", "Te abro la agenda")
    assert dialog.repeated_replies(w) < 2
    assert dialog.loop_nudge(w) == ""


def test_no_loop_with_single_reply():
    w = _win("Hola, ¿en qué te ayudo?")
    assert dialog.loop_nudge(w) == ""


# ── history pruning ─────────────────────────────────────────────────────────────────────────────────────
def test_prune_collapses_twin_assistant_turns():
    w = _win("No tengo acceso a eso", "No tengo acceso a eso ahora")
    pruned = dialog.prune_window(w)
    assistants = [m for m in pruned if m["role"] == "assistant"]
    assert len(assistants) == 1, "las respuestas gemelas se colapsan a una"


def test_prune_keeps_distinct_turns():
    w = _win("Hola Alex", "Te abro la agenda")
    assert len(dialog.prune_window(w)) == len(w)


def test_similar_short_exact_only():
    # Short responses ("sí"/"no") are NOT merged by Jaccard
    assert dialog.similar("sí", "no") is False
    assert dialog.similar("No encuentro precios de eso", "No encuentro precios de eso ahora") is True
