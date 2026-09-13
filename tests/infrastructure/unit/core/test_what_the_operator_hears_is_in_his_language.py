"""V2-676 — every sentence the operator hears lives in the language table, and a blocked search says so.

## The session that produced this file

`af4429e0`, 2026-09-11, 22:00–22:05. The operator deliberately initialised a fresh agent in ENGLISH to check
that the product is as language-agnostic as it claims. Two things broke, and they broke together.

**One — the search.** He asked for the weather in New York. FIVE searches fired with good queries and all five
came back `n: 0`, carrying their reason: `failure.kind = captcha`, Google's anti-bot page and DuckDuckGo's
own. What he heard was:

    «I actually don't have live internet access to fetch real-time information like current weather
     conditions. I can only work with knowledge from my training data, which has a cutoff date.»

Every clause is false about this product. The search module worked, observability recorded the reason
faithfully, and the one reader who had to EXPLAIN the emptiness — the model composing the answer — was handed
`RESULTADOS: (sin resultados)` and nothing else. His reaction measures the cost: «no entiendo cómo después de
dos meses de pruebas el sistema falla y dice que no sabe buscar».

**Two — the language.** When DeepSeek answered `402 Insufficient Balance`, and again when a worker died, he
was told so in SPANISH, mid-English-conversation, because those sentences were string literals at their own
delivery points instead of rows in the table that already holds 72 of them and translates all of them.

## What is measured here

The table was never wrong: English overrides all 72 fields. What was wrong is the sentences that never asked
it. So the guard at the bottom is the durable half — it freezes WHICH delivery points still hold prose, so a
new one is a decision somebody makes on purpose rather than a leak nobody sees until an operator hears it.
"""
from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]


# ── 1 · the table is complete in both shipped languages ─────────────────────────────────────────────────
def test_english_translates_every_line_the_operator_can_hear():
    """A field the English spec forgets falls back to the dataclass DEFAULT, which is Spanish — and it does so
    SILENTLY, which is the shape of failure this whole batch is about."""
    from i18n import langs as L
    es, en = L.LANGUAGES["es"], L.LANGUAGES["en"]
    same = [f.name for f in dataclasses.fields(L.LangSpec)
            if isinstance(getattr(es, f.name), (str, tuple)) and getattr(es, f.name)
            and getattr(es, f.name) == getattr(en, f.name)]
    assert not same, f"English serves the Spanish default for: {same}"


def test_the_table_lives_in_a_low_layer_and_the_old_path_is_the_SAME_module():
    """The move (V2-676) had to keep ~35 existing importers and every monkeypatch working. A star-import shim
    would have made a SECOND module object with its own globals — patching one would leave the other untouched
    and the test would go green measuring nothing («mover código byte por byte cambia sus globals»)."""
    import voice.engine.core.langs as old

    from i18n import langs as new
    assert old is new, "the shim must ALIAS the module, not re-export its names into a new one"


# ── 2 · the sentences he actually heard, now in his language ────────────────────────────────────────────
def _in(code: str, fn):
    import os
    prev = os.environ.get("ZAELAR_LANGUAGE")
    os.environ["ZAELAR_LANGUAGE"] = code
    try:
        return fn()
    finally:
        if prev is None:
            os.environ.pop("ZAELAR_LANGUAGE", None)
        else:
            os.environ["ZAELAR_LANGUAGE"] = prev


def test_a_dead_worker_reports_in_the_operators_language():
    """THE sentence he reported: «esta tarea no ha podido realizarse por un fallo del proveedor… me la ha
    dicho en castellano pero yo acabo de inicializar el agente en inglés»."""
    from nucleo.workers import handoff
    raw = "API Error: the provider exploded"
    en, es = _in("en", lambda: handoff.operator_safe_summary(raw)), _in("es", lambda: handoff.operator_safe_summary(raw))
    assert en != es and "provider failure" in en.lower()
    assert "fallo del proveedor" in es.lower()
    assert "api error" not in en.lower(), "the raw provider text must never survive the gate"


def test_the_model_health_lines_follow_the_operators_language():
    from voice import llm_health
    en = _in("en", lambda: llm_health.messages("429 rate limit exceeded"))
    es = _in("es", lambda: llm_health.messages("429 rate limit exceeded"))
    assert en != es
    assert "credit" in en[0].lower() and "saldo" in es[0].lower()


def test_the_dry_chain_speaks_his_language_and_shows_the_key_instead_of_saying_it():
    """V2-244 renegotiated by the operator: the silenced rung is still NAMED aloud, the config key moves to
    the screen next to the button that acts on it."""
    from nucleo.flash import provider_chain as pc
    line = _in("en", lambda: pc.dry_chain_line(["deepseek-directo"]))
    assert "deepseek-directo" in line and "credit" in line.lower()
    assert "fast.providers" not in line
    assert pc.dry_fault()["config_key"] == "fast.providers"
    assert pc.dry_alert_extra()["blocking"] is True


# ── 3 · a blocked search never denies the internet ──────────────────────────────────────────────────────
_MEASURED = ("I actually don't have live internet access to fetch real-time information like current weather "
             "conditions. I can only work with knowledge from my training data, which has a cutoff date.")
_BLOCKED = {"source": "none", "results": [], "ai": False,
            "failure": {"kind": "captcha", "detail": "google: bloqueado (captcha) · ddg: anti-bot challenge"}}


def test_the_composing_prompt_is_TOLD_why_the_search_came_back_empty():
    """The whole defect in one assertion: the reason existed, and the reader who had to explain it never saw it."""
    from nucleo.flash import search_turn as st
    sys2 = st.compose_system("what's the weather in New York?", "weather in New York", _BLOCKED, "")
    assert "captcha" in sys2.lower() or "ANTI-ROBOT" in sys2
    assert "PROHIBIDO" in sys2, "the forbidden sentence must be named, not merely discouraged"
    assert "acceso a internet" in sys2


def test_a_search_that_WORKED_carries_no_excuse():
    """The reason is added only when there is nothing to show. A prompt that always apologises teaches the
    model to hedge over seven good results."""
    from nucleo.flash import search_turn as st
    ok = {"source": "brave", "results": [{"title": "18°C", "snippet": "sunny"}], "ai": False}
    sys2 = st.compose_system("weather?", "weather NYC", ok, "[1] 18°C — sunny")
    assert "PROHIBIDO" not in sys2 and "captcha" not in sys2.lower()


def test_the_measured_sentence_is_REPLACED_not_merely_logged():
    from nucleo.flash import search_turn as st
    fixed = _in("en", lambda: st.denial_repair(_MEASURED, _BLOCKED))
    assert fixed != _MEASURED
    assert "internet access" not in fixed.lower()
    assert "block" in fixed.lower(), "and it must say what actually happened"


def test_a_true_answer_is_left_alone():
    """«I searched and found nothing» is exactly what we want said — repairing it would be the guard lying."""
    from nucleo.flash import search_turn as st
    for good in ("It's 18 degrees and sunny in New York right now.",
                 "I searched, but nothing useful came back. Want me to dig deeper?",
                 "I don't have the current weather details for New York in front of me right now."):
        assert st.denial_repair(good, _BLOCKED) == good


def test_the_denial_guard_reads_the_answer_alone():
    """Unlike its neighbours in `answer_guards`, this claim is false whenever it is made — over an empty
    search or a full one — so it takes no question."""
    from nucleo.flash import answer_guards as ag
    assert ag.a_reply_denies_the_world("No tengo acceso a internet.")
    assert ag.a_reply_denies_the_world("My knowledge cutoff means I can't help with that.")
    assert not ag.a_reply_denies_the_world("No he podido comprobarlo ahora mismo.")


def test_BOTH_channels_compose_through_the_same_home():
    """WIRING GUARD (V2-555 shape): the voice seam and the probe seam were a parallel implementation since
    V2-135, and the missing half was missing in BOTH. One home is what makes that impossible again."""
    voice = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    for src, who in ((voice, "voice"), (probe, "probe")):
        assert "search_turn" in src, f"{who} must compose through flash/search_turn"
        assert "compose_system(" in src and "denial_repair(" in src, f"{who} misses half the seam"


# ── 4 · an update re-translates, and a blocking fault reaches the screen ────────────────────────────────
def test_the_boot_tops_up_the_language_after_an_update():
    """`i18n.init.prepare()` has claimed since V2-089 that «the boot sequence and the language-switch path»
    both call it. Only the second one ever did — so a French self-hoster who updated kept every NEW key in
    English for good, which is exactly the mixed-language product the operator reported."""
    boot = (ENGINE / "server/__init__.py").read_text(encoding="utf-8")
    assert "_i18n_init.prepare(" in boot, "nothing tops the language up at boot"
    assert "active_code()" in boot


def test_the_fault_that_blocks_the_screen_carries_FACTS_and_not_prose():
    """A dry model chain is the one moment the translator —a model— is what we do not have, so the engine
    sends facts and the frontend renders them from its own bundle."""
    from nucleo.flash import provider_chain as pc
    f = pc.dry_fault()
    assert set(f) >= {"code", "model", "provider", "suppressed", "config_key"}
    assert all(not isinstance(v, str) or len(v) < 60 for v in f.values()), "no sentences in the payload"


def test_the_blocking_fault_is_wired_from_the_engine_to_a_translated_screen():
    fe = ENGINE / "frontend/app"
    sse = (fe / "services/sse.js").read_text(encoding="utf-8")
    assert "d.blocking" in sse and "showFault(" in sse
    assert "hb:blocking-fault" in sse, "the voice stop is announced (sse cannot import session: cycle)"
    assert "hb:blocking-fault" in (ENGINE / "frontend/app/main.js").read_text(encoding="utf-8")
    modal = (fe / "components/FaultModal.js").read_text(encoding="utf-8")
    assert "setConfigOpen(true)" in modal, "the operator asked for a button that opens the settings"
    # Every word on that screen must be a key, never a literal the engine sent.
    import json
    keys = json.loads((ENGINE / "i18n/bundles/en.json").read_text(encoding="utf-8"))
    for k in ("fault.no_model.title", "fault.no_model.body", "fault.no_model.open_config",
              "fault.no_model.suppressed", "fault.no_model.fix"):
        assert k in keys, f"{k} missing from the manifest — a generated language would never get it"
        assert f'"{k}"' in modal or k in modal


# ── 4b · the four sentences of 2026-09-12 (V2-682) ─────────────────────────────────────────────────────
# All four were heard VERBATIM, in Spanish, in an English session — and none of them was a `notify`/`say`
# call, which is why the ratchet below had to grow two shapes as well.

def test_the_irreversible_gate_asks_in_his_language():
    """«¿Vacío la agenda entera? Es permanente.» → «Vale, no toco nada.», 20:07. A gate that stops the
    product doing something has to explain itself in his language or it reads as a fault."""
    from nucleo import danger
    en = _in("en", lambda: danger.confirm_question("delete every appointment"))
    es = _in("es", lambda: danger.confirm_question("borra todas las citas"))
    assert "irreversible" in en.lower() and "your OK" in en
    assert "irreversible" in es.lower() and "tu OK" in es
    assert en != es


def test_the_spend_gate_asks_in_his_language():
    """20:45:05, fired by the STT rendering «pause» as «pay» — so he got a money warning, in Spanish, over a
    request to pause the music."""
    from nucleo import danger
    en = _in("en", lambda: danger.confirm_question("pay the booking with my card"))
    es = _in("es", lambda: danger.confirm_question("paga la reserva con mi tarjeta"))
    assert "moves money" in en.lower() and "charge" in en.lower()
    assert "mueve dinero" in es.lower()


def test_the_confirmation_ack_comes_from_the_table():
    """«Vale, no toco nada.» was a literal at the voice mouth."""
    from i18n import langs as L
    assert L.LANGUAGES["en"].confirm_cancelled != L.LANGUAGES["es"].confirm_cancelled
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "confirm_cancelled" in src and "Vale, no toco nada" not in src


def test_the_first_turn_is_spoken_in_his_language():
    """The kickoff is the one injected turn that impersonates the OPERATOR, so a Spanish one primes a Spanish
    reply on turn one. It was a literal in the provider."""
    from i18n import langs as L
    assert L.LANGUAGES["en"].kickoff_prompt.startswith("This is the first turn")
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "kickoff_prompt" in src and "Es el primer turno" not in src


def test_a_worker_that_dies_says_so_in_his_language():
    """Seven of these were heard that evening. They were five Spanish literals in `workers/session.py` and
    one more in `workers/stall.py`."""
    from i18n import langs as L
    for field in ("worker_context_lost", "worker_relay_failed", "worker_no_relay",
                  "worker_gave_up_context", "worker_gave_up_provider", "worker_command_denied",
                  "worker_stalled"):
        en, es = getattr(L.LANGUAGES["en"], field), getattr(L.LANGUAGES["es"], field)
        assert en and es and en != es, field
    src = (ENGINE / "nucleo/workers/session.py").read_text(encoding="utf-8")
    assert "_say().worker_" in src, "the endings must read the table"


def test_the_stalled_ending_is_formatted_from_the_table():
    from i18n import langs as L
    line = _in("en", lambda: L.current_language().worker_stalled.format(minutes=7))
    assert "7 min" in line and "stopped answering" in line


def test_the_introduction_never_asks_a_question_the_language_does_not_have():
    """«"tú" or "usted", which do you prefer?» — asked THREE times in one English conversation on
    2026-09-12 (20:08, 20:24, 20:36). English has no T–V distinction, so there is no answer to give; the
    goal was a Spanish literal in the phase's own goal list."""
    from nucleo.context_packs import introduction as intro
    known = intro._known
    intro._known = lambda: {}                          # nothing learned yet: every goal is still open
    try:
        es = _in("es", intro.block)
        en = _in("en", intro.block)
    finally:
        intro._known = known
    from i18n import langs as L
    q = L.LANGUAGES["es"].treatment_question
    assert q and q in es, "Spanish keeps the question — the distinction is real there"
    # The pack's PROSE is Spanish for every language on purpose (it is a model-facing prompt, like the rest
    # of the system prompt), so the assertion is about the GOAL, not about the block's vocabulary.
    assert q not in en and "(tú/usted)" not in en
    assert "su nombre" in en, "the goals that DO exist in every language are untouched"


def test_a_language_with_no_spec_of_its_own_is_not_asked_either():
    """A generated language has no `LangSpec`, so it inherits the product default — and the safe default is
    not asking about a distinction we cannot confirm exists."""
    from i18n import langs as L
    assert L.LANGUAGES["en"].treatment_question == ""
    assert L.spec("ja").treatment_question == L.LANGUAGES[L.current_code()].treatment_question


# ── 5 · THE RATCHET: prose at a delivery point only shrinks ─────────────────────────────────────────────
# The operator's standing instruction: «intenta unificar todos los textos, labels, todo el contenido que
# tiene que traducirse, que esté en un solo lugar». Two places qualify and both travel to any language:
# `i18n/langs.py` (what he HEARS) and `i18n/bundles/` (what he READS). Everything below is a delivery point
# that still holds its own prose. The list is a MEASUREMENT, edited DOWNWARD when one is retired — never
# upward. A new entry means: put the sentence in the table.
_PROSE_AT_DELIVERY = {
    # OAuth callback pages — served into a popup browser window mid-connection, outside any bundle the app
    # has loaded. Named, not fixed: they need their own pass (the page has no i18n runtime at all).
    "connectors/files/server_api.py",
    "connectors/video/server_api.py",
    "server/spotify_api.py",
}

_SPANISH = re.compile(r"\b(el|la|los|las|un|una|de|que|no|se|te|le|lo|por|para|con|está|estoy|he|"
                      r"hay|puedo|tengo|esa|ese|esto|eso|mi|tu|su|pero|ya)\b", re.I)
_ACCENT = re.compile(r"[áéíóúñ¿¡]", re.I)
# The calls that hand a sentence to the OPERATOR. `emit` is observability and `milestone` is the task log —
# both are ours to read, not his, and both stay Spanish on purpose.
_DELIVERS = {"notify", "send_operator", "say"}
# V2-682 — THE RATCHET MEASURED ONE SHAPE AND THE LEAKS CAME THROUGH THREE OTHERS.
#
# Measured in his English session of 2026-09-12, all four in Spanish and none of them a `notify`/`say` call:
#   · «¿Vacío la agenda entera? Es permanente.» — a RETURN value (`widgets` confirm_q, and `danger.py`'s own)
#   · «Vale, no toco nada.» — a literal handed to `speech.sanitize(...)`, the voice mouth's own funnel
#   · «Esto mueve dinero («…») y no hago ningún cargo sin tu OK» — a RETURN value from `danger.py`
#   · the worker endings — an ASSIGNMENT to `rec.result_summary`, which is read aloud when a task dies
#
# So the measurement grows two shapes: what is written into a field whose content is SPOKEN, and what is
# handed to the sanitizer. Kept narrow on purpose — `send`/`speak` were measured and rejected as the anchor
# (in `session.py` and `second_pass.py` they carry text for the MODEL, not for him, and a ratchet with false
# positives is a ratchet that gets an allowlist instead of a fix).
_SPOKEN_FIELDS = {"result_summary", "spoken", "spoken_text", "_ack_early"}
_SANITIZERS = {"sanitize"}


def _spanishy(s: str) -> bool:
    if len(s) < 25:
        return False
    w = _SPANISH.findall(s)
    return len(w) >= 3 and (len(w) >= 4 or bool(_ACCENT.search(s)))


def _flat(node) -> list[str]:
    """Every string this expression can produce, with an f-string JOINED back together.

    ⚠️ V2-682 — this is the hole the first version had, and it is the one that mattered: an f-string is a
    `JoinedStr` whose pieces are each too short to look Spanish («El proveedor dejó de responder (» has two
    stopwords), so the sentences that actually leaked — every one of them interpolated — were invisible to a
    scan that only looked at `ast.Constant`. A disarm that put one back came back GREEN and accused the
    ratchet, which is what a disarm is for."""
    out: list[str] = []
    for c in ast.walk(node):
        if isinstance(c, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}"
                               for v in c.values))
        elif isinstance(c, ast.Constant) and isinstance(c.value, str):
            out.append(c.value)
    return out


def _prose_in(src: str) -> bool:
    """True when this source hands the operator a Spanish sentence at one of the watched delivery shapes."""
    try:
        tree = ast.parse(src)
    except Exception:
        return False
    for n in ast.walk(tree):
        carried = []
        if isinstance(n, ast.Call):
            fn = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if fn in _DELIVERS or fn in _SANITIZERS:
                carried = list(n.args) + [k.value for k in n.keywords]
        elif isinstance(n, ast.Assign):
            names = {getattr(t, "attr", None) or getattr(t, "id", None) for t in n.targets}
            if names & _SPOKEN_FIELDS:
                carried = [n.value]
        for a in carried:
            if any(_spanishy(t) for t in _flat(a)):
                return True
    return False


def _measure() -> set[str]:
    found: set[str] = set()
    for root in ("nucleo", "voice", "widgets", "server", "connectors"):
        for p in sorted((ENGINE / root).rglob("*.py")):
            try:
                src = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if _prose_in(src):
                found.add(str(p.relative_to(ENGINE)))
    return found


# The ratchet must be able to SEE each shape, or «no new prose» only means «no prose of the one shape I read».
def test_the_ratchet_sees_a_sentence_written_into_a_spoken_field():
    assert _prose_in('rec.result_summary = "El proveedor dejó de responder y he abortado la tarea entera."')
    assert _prose_in('rec.result_summary = f"El proveedor dejó de responder ({mins} min) y aborté la tarea."')


def test_the_ratchet_sees_a_sentence_handed_to_the_mouth():
    assert _prose_in('send(speech.sanitize("Vale, no toco nada, esto no lo hago sin tu permiso.", x=1))')


def test_the_ratchet_leaves_our_own_prose_alone():
    """Observability and the task log are OURS to read. A ratchet that reddens on those gets an allowlist
    instead of a fix."""
    assert not _prose_in('emit("brain", "el turno se descarta porque no hay nada que decir todavía")')
    assert not _prose_in('logger.warning("no se pudo relevar el proveedor de los procesos de fondo")')


def test_no_new_prose_is_written_at_a_delivery_point():
    got = _measure()
    new = got - _PROSE_AT_DELIVERY
    assert not new, (
        "a sentence the operator can hear is hardcoded instead of living in `i18n/langs.py` — that is how he "
        "ended up being answered in Spanish in an English session:\n  " + "\n  ".join(sorted(new)))


def test_the_retired_ones_stay_retired():
    """The celebration half: an entry removed from the list above must not come back."""
    got = _measure()
    assert got <= _PROSE_AT_DELIVERY, f"unexpected: {sorted(got - _PROSE_AT_DELIVERY)}"
