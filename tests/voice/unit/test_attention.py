#
# test_attention.py — attention gate (V2-015 · T134/T135/T136; content V2-??? 2026-08-16).
#
import asyncio
import importlib

import pytest

from voice import attention


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    attention.set_directed_judge(None)
    yield
    attention.reset()
    attention.set_directed_judge(None)


# ── mode ────────────────────────────────────────────────────────────────────────────────────────────────
def test_mode_default_is_always():
    # Robot OFF by default = always listens and responds; the UI toggle switches to wake-word mode.
    assert attention.mode() == "always"


def test_mode_env_override(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "WakeWord")
    assert attention.mode() == "wakeword"


def test_mode_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "bogus")
    assert attention.mode() == "always"


# ── wake-word ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "zaelar qué hora es", "Oye Zaelar, abre la agenda", "ZAELAR",
    "oye zaelar ayúdame",
])
def test_wakeword_detected(txt):
    assert attention.has_wakeword(txt)


@pytest.mark.parametrize("txt", [
    "qué hora es", "sí sí sí", "abro mi agenda", "pásame la sal por favor",
    "harvey pon música", "oye jarbi ayúdame",  # mishearings of the old name "harbee" — no longer wakewords
])
def test_wakeword_absent(txt):
    assert not attention.has_wakeword(txt)


def test_custom_wakewords(monkeypatch):
    monkeypatch.setenv("ZAELAR_WAKEWORDS", "colmena, abeja")
    assert attention.has_wakeword("oye colmena")
    assert not attention.has_wakeword("zaelar")   # The custom value REPLACES the default.


# ── evaluate: smart ─────────────────────────────────────────────────────────────────────────────────────
def test_smart_wakeword_is_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    v = attention.evaluate("zaelar, cierra la agenda")
    assert v.directed and v.reason == "wakeword"


def test_smart_no_wakeword_no_window_is_ambient(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    v = attention.evaluate("sí claro, lo que tú digas")
    assert not v.directed and v.reason == "ambient"


def test_smart_active_window_is_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = attention.evaluate("y mañana qué tengo", now=now + 4)   # within the 5s ceiling (2026-09-10)
    assert v.directed and v.reason == "active_window"


def test_smart_window_expires(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = attention.evaluate("y mañana qué tengo", now=now + 45)   # beyond 30s
    assert not v.directed and v.reason == "ambient"


def test_window_configurable_only_SHORTENS_in_smart_mode(monkeypatch):
    """The knob is an escape hatch that can shorten, never lengthen past the 5s ceiling (operator rule
    2026-09-10) — an old stored 60s must not silently defeat it."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    monkeypatch.setenv("ZAELAR_ATTENTION_WINDOW", "60")
    now = 1000.0
    attention.note_directed(now=now)
    assert not attention.evaluate("sigo hablando", now=now + 50).directed   # 60 clamps to 5
    monkeypatch.setenv("ZAELAR_ATTENTION_WINDOW", "3")
    attention.note_directed(now=now)
    assert not attention.evaluate("sigo hablando", now=now + 4).directed    # 3 genuinely shortens


# ── evaluate: wakeword / always / ptt ───────────────────────────────────────────────────────────────────
def test_wakeword_mode_ignores_window(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "wakeword")
    now = 1000.0
    attention.note_directed(now=now)
    assert not attention.evaluate("sin llamarle", now=now + 5).directed   # The window does NOT count.
    assert attention.evaluate("zaelar ayuda", now=now + 5).directed


def test_always_mode_everything_directed(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    assert attention.evaluate("cualquier cosa ambiente").directed


# ── evaluate_content: `always` mode JUDGES content (2026-08-16) ─────────────────────────────────────────
# Real live session: background noise ("Mira donde tú quieras, pero dame el ya...") ran a COMPLETE turn
# —including a real 3.3s web_search— before being discarded as ambient. `evaluate()` (above) still treats
# EVERYTHING as directed in `always`; `evaluate_content()` is what actually discriminates, and it is the only
# one used by the real voice turn (nucleo.py). The judge is injectable (`set_directed_judge`) so tests do not
# hit the network.
def _run(coro):
    return asyncio.run(coro)


def test_evaluate_content_ignores_smart_wakeword_modes_same_as_evaluate(monkeypatch):
    """Outside `always`, there is no need to ask any model—the existing heuristic is sufficient."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    now = 1000.0
    attention.note_directed(now=now)
    v = _run(attention.evaluate_content("y mañana qué tengo", now=now + 4))
    assert v.directed and v.reason == "active_window"


def test_evaluate_content_wakeword_is_a_free_shortcut_no_judge_called():
    async def _judge(text, context):
        raise AssertionError("wake-word ya es prueba suficiente, no hace falta gastar un round-trip")
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("zaelar, qué hora es"))
    assert v.directed and v.reason == "wakeword"


def test_evaluate_content_directed_when_the_judge_says_so():
    async def _judge(text, context):
        assert text == "cuánto vale un balón de fútbol"
        return True
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("cuánto vale un balón de fútbol"))
    assert v.directed and v.reason == "always"


def test_evaluate_content_ambient_when_the_judge_says_so():
    """The real case that motivated this: background noise, the judge says AMBIENT, and the turn NEVER incurs
    any cost (nucleo.py cuts off here, before the prompt/tools/search)."""
    async def _judge(text, context):
        return False
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("Mira donde tú quieras, pero dame el ya"))
    assert not v.directed and v.reason == "llm_ambient"


def test_evaluate_content_passes_context_through_to_the_judge():
    seen = {}

    async def _judge(text, context):
        seen["context"] = context
        return True
    attention.set_directed_judge(_judge)
    _run(attention.evaluate_content("de la más alta gama", context="precio del balón del mundial"))
    assert seen["context"] == "precio del balón del mundial"


def test_evaluate_content_fails_open_when_the_judge_raises():
    async def _judge(text, context):
        raise RuntimeError("modelo caído")
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("cualquier frase"))
    assert v.directed, "un juez roto nunca puede dejar mudo al agente"


def test_evaluate_content_fails_open_when_the_judge_returns_none():
    """None = the response could not be parsed (broken JSON, odd model)—same fail-open behavior as an exception."""
    async def _judge(text, context):
        return None
    attention.set_directed_judge(_judge)
    assert _run(attention.evaluate_content("cualquier frase")).directed


def test_evaluate_content_empty_text_is_ambient_without_calling_the_judge():
    async def _judge(text, context):
        raise AssertionError("un texto vacío no necesita juez")
    attention.set_directed_judge(_judge)
    v = _run(attention.evaluate_content("   "))
    assert not v.directed


@pytest.mark.parametrize("raw,expected", [
    ('{"directed": true}', True),
    ('{"directed": false}', False),
    ('```json\n{"directed": true}\n```', True),
    ('here you go: {"directed": false} thanks', False),
    ("not json at all", None),
    ("", None),
    (None, None),
    ('{"directed": "yes"}', None),   # not a real bool — fail-open; do not guess
])
def test_parse_directed(raw, expected):
    assert attention._parse_directed(raw) is expected


def test_ptt_mode(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "ptt")
    assert not attention.evaluate("hola").directed
    attention.set_ptt(True)
    assert attention.evaluate("hola").directed
    attention.set_ptt(False)
    assert not attention.evaluate("hola").directed


# ── hard interrupt (T136) ───────────────────────────────────────────────────────────────────────────────
def test_hard_interrupt_close_all():
    assert attention.hard_interrupt("cierra los widgets") == "close"
    assert attention.hard_interrupt("cierra todo") == "close"
    assert attention.hard_interrupt("close everything") == "close"


@pytest.mark.parametrize("txt", ["silencio", "cállate", "basta ya", "stop", "para ya", "shhh"])
def test_hard_interrupt_stop_hard(txt):
    assert attention.hard_interrupt(txt) == "stop"


# ── ENCLITIC PRONOUN (REAL live failure, 2026-08-12 13:01:51) ────────────────────────────────────────────
# The operator said «Ciérralo todo y páralo todo». `\bcierra\b` does not match «cierralo» (there is no word
# boundary after 'cierra'), so the detector returned None, the command reached the MODEL—which got stuck on
# that turn—and nothing was closed. This path exists precisely so closing and stopping do NOT depend on the LLM.
# This is morphology, not a phrase list: the Spanish imperative attaches up to two pronouns to the verb.
def test_close_all_with_the_pronoun_stuck_to_the_verb():
    assert attention.hard_interrupt("Ciérralo todo y páralo todo.") == "close"   # the EXACT phrase from the incident
    assert attention.hard_interrupt("ciérralo todo") == "close"
    assert attention.hard_interrupt("ciérramelo todo") == "close"                # two pronouns
    assert attention.hard_interrupt("quítalos todos") == "close"
    assert attention.hard_interrupt("límpialo todo") == "close"


def test_stop_with_the_pronoun_stuck_to_the_verb():
    """An attached pronoun disambiguates the PREPOSITION, so a stop with a clitic does not need the soft
    rule's word limit—that remains true and is what this case protects.

    What V2-393 fixed is the other half: «unambiguous as a VERB» is not «unambiguous about WHAT». The
    reflexive/dative refers to zaelar and remains a hard stop; the third-person accusative («párala»,
    «detenlo») carries a DIRECT OBJECT—it applies to a thing—and a barge-in has no object. In
    `watch-a-video-not-listen-to-it`: «Ahora páralo, porfa» over a loaded video consumed the entire turn.
    The detail lives in `tests/voice/unit/test_paralo_lleva_objeto.py` (node 3.14).
    """
    assert attention.hard_interrupt("páralo todo ahora mismo y espera") == "stop"   # «todo» → global
    assert attention.hard_interrupt("párate ahora mismo y espera") == "stop"        # reflexive → it refers to him
    assert attention.hard_interrupt("párala") is None                               # accusative → a thing
    assert attention.hard_interrupt("detenlo") is None


def test_the_enclitic_forms_do_not_swallow_normal_speech():
    """The boundary still requires a REAL attached pronoun: neither invented 'cierralotodo' nor words that start
    the same way trigger a close, and a long turn with prepositional 'para' remains conversation."""
    assert attention.hard_interrupt("dame una receta rica para la cena de mañana") is None
    assert attention.hard_interrupt("cierra la puerta de casa cuando salgas") is None   # without 'todo/widgets'
    assert attention.hard_interrupt("quita la pantalla completa") is None               # mode for ONE widget


def test_the_stt_rendering_of_pantalla_completa_is_not_a_close_all():
    """V2-600, measured live 2026-09-05 (session 3050e623): the operator said «cierra la pantalla completa»
    and the STT delivered «Cierra la pantalla completamente.» — the fullscreen guard required the exact
    bigram, missed, and «cierra» + «pantalla» closed EVERY widget, re-firing on each glued fragment. The
    adverb form is the same order about the same screen mode. The counterweight below keeps the real
    close-all alive: a wrongly vetoed close-all just reaches the model, a missed veto destroys the canvas."""
    assert attention.hard_interrupt("Cierra la pantalla completamente.") is None
    assert attention.hard_interrupt("quita la pantalla completamente") is None
    assert attention.hard_interrupt("cierra la pantalla") == "close"        # bare screen = everything, still
    assert attention.hard_interrupt("cierra todos los widgets") == "close"  # the guard never eats close-all


def test_mentions_fullscreen_is_the_one_copy_both_backstops_read():
    """The generic close backstops (voice provider + probe mirror) veto on this helper: a turn that mentions
    fullscreen is about a screen STATE — leaving it, or narrating it — never a whole-widget close order for a
    backstop to guess. Measured 2026-09-05: the operator's complaint «te he dicho que cerraras la pantalla
    completa, no que cerraras el widget del vídeo» made the backstop close `youtube` AGAIN, twice."""
    assert attention.mentions_fullscreen("te he dicho que cerraras la pantalla completa, no el widget")
    assert attention.mentions_fullscreen("Cierra la pantalla completamente.")
    assert attention.mentions_fullscreen("exit full screen please")
    assert attention.mentions_fullscreen("quita el fullscreen")
    assert not attention.mentions_fullscreen("cierra el widget de vídeo")
    assert not attention.mentions_fullscreen("limpia la pantalla")   # screen ≠ fullscreen: close-all stays


def test_hard_interrupt_soft_para_short():
    assert attention.hard_interrupt("para por favor") == "stop"


def test_hard_interrupt_soft_para_long_is_not_stop():
    # "para" as a preposition in a long turn must NOT trigger a STOP.
    assert attention.hard_interrupt("dame una receta rica para la cena de mañana") is None


def test_hard_interrupt_none_for_normal_turn():
    assert attention.hard_interrupt("qué tiempo hace hoy") is None
    assert attention.hard_interrupt("cierra la agenda") is None   # closing ONE widget ≠ hard (no 'todo/widgets')


# ── clamp_input (T135) ──────────────────────────────────────────────────────────────────────────────────
def test_clamp_short_passthrough():
    txt, clipped = attention.clamp_input("hola", 100)
    assert txt == "hola" and not clipped


def test_clamp_preserves_command_at_start():
    cmd = "cierra los widgets por favor. "
    long = cmd + ("bla bla bla ambiente " * 200)   # >> max
    txt, clipped = attention.clamp_input(long, 400)
    assert clipped
    assert "cierra los widgets" in txt            # the command is NOT lost even though it is at the beginning
    assert len(txt) <= 400 + 8


def test_clamp_truncates_when_no_command():
    long = "ruido ambiente " * 500
    txt, clipped = attention.clamp_input(long, 300)
    assert clipped and len(txt) == 300


# ── the active window BEATS the judge in `always` mode (2026-09-01, session 701fcc1b) ───────────────────
# Live incident: mid-dialogue, the DeepSeek judge returned {"directed": false} on 8 consecutive operator turns
# («Veo que ya la has abierto», «¿Me estás escuchando?», «Te he dicho que ya la has abierto», «no hay ningún
# mensaje en la lista») — 15/15 on replay — and the agent went deaf until the operator gave up. `always` mode
# maintained the conversation window and never consulted it; now, inside the window, nobody judges.
def test_always_mode_active_window_never_consults_the_judge():
    async def _judge(text, context):
        raise AssertionError("inside the active conversation window no judge is consulted")
    attention.set_directed_judge(_judge)
    now = 1000.0
    attention.note_directed(now=now)
    v = _run(attention.evaluate_content("Te he dicho que ya la has abierto.", now=now + 5))
    assert v.directed and v.reason == "active_window"


def test_always_mode_cold_turn_is_still_judged():
    """Outside the window the judge keeps its original job — the 'session sitting in a meeting' case."""
    seen = {}

    async def _judge(text, context):
        seen["called"] = True
        return False
    attention.set_directed_judge(_judge)
    now = 1000.0
    attention.note_directed(now=now)
    v = _run(attention.evaluate_content("bla bla de fondo", now=now + attention.window_s() + 1))
    assert seen.get("called"), "a COLD turn does go through the judge"
    assert not v.directed and v.reason == "llm_ambient"


def test_session_701fcc1b_the_agent_never_goes_deaf_mid_conversation():
    """Replay of the real incident with the judge answering exactly what it answered live: false, every time.
    The contract under test is the pair gate+caller: a handled directed turn refreshes the window
    (`note_directed`, the call nucleo.py makes at the gate), so one handled turn keeps the whole exchange
    alive and NONE of the 8 turns the operator actually said can be dropped again."""
    async def _judge(text, context):
        return False   # measured live: 8/8, and 15/15 on replay
    attention.set_directed_judge(_judge)
    t0 = 1000.0
    attention.note_directed(now=t0)             # «I have a message.» was handled at 09:12:29
    turns = [
        (15, "Que es la que está trabajando"),
        (17, "Que es la que está trabajando Veo que ya la has abierto."),
        (28, "Lo ha publicado hace unos días, un compañero anteayer,"),
        (33, "Lo ha publicado hace unos días, un compañero anteayer, que habla especialmente, etcétera. ¿Me estás escuchando?"),
        (60, "Te he dicho que ya la has abierto."),
        (83, "Pero no veo ningún mensaje."),
        (102, "Vamos a ver, te he dicho que la mensajería ya la has abierto, hace rato."),
        (106, "Vamos a ver, te he dicho que la mensajería ya la has abierto, hace rato. Te he dicho también que no hay ningún mensaje en la lista."),
    ]
    for dt, phrase in turns:
        v = _run(attention.evaluate_content(phrase, now=t0 + dt))
        assert v.directed, f"REAL turn from the session dropped again: «{phrase[:60]}»"
        attention.note_directed(now=t0 + dt)    # the caller's side of the contract when it handles the turn


def test_both_close_backstops_are_wired_to_the_fullscreen_veto():
    """WIRING guard (V2-600): the veto lives once (`mentions_fullscreen`) and BOTH generic close backstops —
    the voice provider's and the probe mirror's — must consult it, or the next «cierra la pantalla completa»
    complaint closes the widget again in whichever channel lost the line (the V2-252 drift, measured here on
    2026-09-05). Anchored on the backstop's own conditional (`looks_like_close` + `looks_like_create_widget`
    in one statement), never on the whole file; comments are stripped first so a comment naming the helper
    cannot stand in for the call (the V2-573 trap)."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[3]
    files = [root / "voice" / "engine" / "llm" / "providers" / "nucleo.py",
             root / "nucleo" / "flash" / "probe.py"]
    for path in files:
        src = "\n".join(line.split("#", 1)[0] for line in path.read_text().splitlines())
        spans = [m.start() for m in re.finditer(r"looks_like_close\(text\)", src)
                 if "looks_like_create_widget" in src[m.start():m.start() + 400]]
        assert spans, f"the close backstop's conditional was not found in {path.name} — re-anchor this guard"
        for s in spans:
            window = src[s:s + 500]
            assert "mentions_fullscreen" in window, (
                f"{path.name}: the close backstop lost its fullscreen veto — a turn mentioning «pantalla "
                f"completa» would close the whole widget again (measured 2026-09-05, session 3050e623)")


# ── the window measures REAL silence, and only a directed turn can open it (2026-09-09, session 49e13093) ──
# Measured live in wake-word mode: the 30s window re-fed itself off every turn IT admitted, so the operator's
# conversation with a third person kept it alive indefinitely — «A ver, Raquel, ¿a qué hora comemos?» came in
# as `active_window` 13.9s after zaelar's last word, and zaelar answered a family conversation for a minute.

def _smart(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")


def test_the_window_is_per_mode_5s_in_wake_word_30s_in_always(monkeypatch):
    assert attention.window_s() == 30.0     # always: V2-531's no-judge dialogue continuity keeps its 30s
    _smart(monkeypatch)
    # Wake word: hard 5s ceiling (operator, 2026-09-10: «ninguna pausa puede pasar de 5 segundos» — he
    # measured 12s pauses keeping the mic attentive and ruled them out; supersedes 2026-09-09's 12s).
    assert attention.window_s() == 5.0


def test_third_party_talk_after_the_bot_finished_is_ambient(monkeypatch):
    _smart(monkeypatch)
    t = 1000.0
    attention.note_directed(now=t)                      # «No.»
    attention.note_bot_speech(True, now=t + 1)
    attention.note_bot_speech(False, now=t + 6)         # «Perfecto, Ricard. Aquí estoy…» ends
    v = attention.evaluate("A ver, Raquel, ¿a qué hora comemos?", now=t + 20)   # 14s of real silence
    assert not v.directed and v.reason == "ambient"


def test_an_answer_after_a_reply_longer_than_the_window_is_still_directed(monkeypatch):
    # The window is anchored to zaelar's LAST WORD, not the operator's last turn: a 20s reply must not leave
    # the operator's «Vale.» five seconds later marked ambient.
    _smart(monkeypatch)
    t = 1000.0
    attention.note_directed(now=t)
    attention.note_bot_speech(True, now=t + 1)
    attention.note_bot_speech(False, now=t + 21)        # reply outlives the 12s window
    assert attention.evaluate("Vale.", now=t + 26).directed


def test_a_barge_in_while_the_bot_still_talks_is_directed(monkeypatch):
    _smart(monkeypatch)
    t = 1000.0
    attention.note_directed(now=t)
    attention.note_bot_speech(True, now=t + 1)          # still talking at t+15, window would have expired
    assert attention.evaluate("espera, mejor otro", now=t + 15).directed


def test_the_KICKOFF_never_OPENS_a_window(monkeypatch):
    # Zaelar speaking on its OWN INITIATIVE grants no hands-free attention: the documented decision at the
    # gate call site is about the greeting — a session starting mid-meeting must not open with a free window
    # into which ambient speech can walk. RE-SCOPED 2026-09-10 (V2-655): it used to be written as «the bot's
    # own speech NEVER opens a window», which is not what that decision says and is what left the operator
    # unheard for sixteen turns after a delivery the agent owed him. An utterance ARMED by
    # `note_addressed_speech()` does open one — see test_if_it_talks_to_you_it_listens_to_you.py. Unarmed
    # speech, which is what the kickoff is, still only HOLDS a window a directed turn already opened.
    _smart(monkeypatch)
    t = 1000.0
    attention.note_bot_speech(True, now=t)
    attention.note_bot_speech(False, now=t + 5)
    v = attention.evaluate("qué frío hace hoy", now=t + 6)
    assert not v.directed and v.reason == "ambient"


def test_reset_clears_the_bot_hold(monkeypatch):
    _smart(monkeypatch)
    attention.note_directed(now=1000.0)
    attention.note_bot_speech(True, now=1001.0)
    attention.reset()
    assert not attention.evaluate("sigo hablando", now=1002.0).directed


# ── the window is DYNAMIC per reply: 4-15s by what the exchange looks like (2026-09-09) ────────────────────
# Operator directive: after «dime el tiempo» → «Hecho.» four seconds of open mic is plenty; mid-errand or
# right after zaelar ASKS something, fifteen is the natural pause. Deterministic, model-free
# (voice/attention_window.py); the reply that just finished sizes the window it re-anchors.
from voice import attention_window


def test_a_bare_ack_to_a_one_shot_order_earns_the_short_window():
    assert attention_window.hint("Hecho.", dialogue_turns=1, task_live=False) == 5.0


def test_NO_shape_may_exceed_the_5s_ceiling():
    """Operator rule 2026-09-10: «ninguna pausa puede ser tan grande si estamos hablando con el sistema —
    a los 5 segundos se apaga». The scale still distinguishes the shapes underneath, but every rung clamps
    to 5s — including the two that used to earn 15s (a reply that asks, a live errand) and the 12s dialogue
    window he measured live and ruled out."""
    asks = attention_window.hint("¿Quieres que te ponga alguno de la lista?", dialogue_turns=1, task_live=False)
    live = attention_window.hint("Hecho.", dialogue_turns=1, task_live=True)
    dialogue = attention_window.hint("Pues de garajes caseros te recomendaría un par de canales.",
                                     dialogue_turns=4, task_live=False)
    base = attention_window.hint("Te lo apunto para el viernes por la tarde.", dialogue_turns=1, task_live=False)
    assert asks == live == dialogue == base == 5.0
    assert attention_window.MAX_S == 5.0


def test_note_reply_drives_window_s_in_smart_mode_and_the_ceiling_beats_the_override(monkeypatch):
    _smart(monkeypatch)
    monkeypatch.setattr(attention_window, "live_task", lambda: False)
    t = 1000.0
    attention.note_directed(now=t)
    attention.note_reply("Hecho.", now=t + 2)
    assert attention.window_s() == 5.0
    attention.note_reply("¿Te lo pongo?", now=t + 4)
    assert attention.window_s() == 5.0      # even a question caps at the ceiling (2026-09-10)
    # The env override can SHORTEN…
    monkeypatch.setenv("ZAELAR_ATTENTION_WINDOW", "3")
    assert attention.window_s() == 3.0
    # …but never lengthen past the ceiling: the ⚙ knob used to offer 15-120s, and an old stored value must
    # not silently defeat the rule.
    monkeypatch.setenv("ZAELAR_ATTENTION_WINDOW", "20")
    assert attention.window_s() == 5.0


# ── instant wake-word spotting + reclaiming the speech said BEFORE the name (2026-09-09) ───────────────────
# Operator: the orb lit 1-3s after the wake word (STT-final + the whole turn gate in between), and «Ostras,
# para la música, Johnny» lost its order — the fragments before the name were judged ambient and dropped, so
# the model only ever saw «Johnny».

def test_a_wakeword_turn_reclaims_the_ambient_speech_just_before_it(monkeypatch):
    _smart(monkeypatch)
    t = 1000.0
    attention.note_ambient("Ostras, para la música,", now=t)
    assert attention.reclaim_ambient_tail("Johnny.", now=t + 3) == "Ostras, para la música, Johnny."


def test_the_tail_is_consumed_and_never_feeds_two_turns(monkeypatch):
    _smart(monkeypatch)
    t = 1000.0
    attention.note_ambient("para la música,", now=t)
    attention.reclaim_ambient_tail("Johnny.", now=t + 2)
    assert attention.reclaim_ambient_tail("Johnny, ¿me oyes?", now=t + 5) == "Johnny, ¿me oyes?"


def test_old_ambient_speech_is_not_reclaimed(monkeypatch):
    # Nobody ends a half-minute-old sentence with the wake word — stale room chatter must not ride in.
    _smart(monkeypatch)
    attention.note_ambient("esto es charla de hace rato", now=1000.0)
    assert attention.reclaim_ambient_tail("Johnny, hola", now=1020.0) == "Johnny, hola"


def test_wakeword_spotting_emits_once_per_burst(monkeypatch):
    hits = []
    import voice.observer as _obs
    monkeypatch.setattr(_obs, "emit", lambda *a, **k: hits.append(a))
    attention.note_wakeword_spotted(now=1000.0)
    attention.note_wakeword_spotted(now=1001.0)   # interims repeat within the same utterance → deduped
    attention.note_wakeword_spotted(now=1005.0)   # a later burst may light again
    assert len(hits) == 2


def test_the_interim_stream_and_the_gate_are_both_wired():
    import re as _re
    agent_src = _re.sub(r"(?m)#.*$", "", open("voice/engine/pipeline/agent.py", encoding="utf-8").read())
    # V2-655: the gate block moved out of the provider into `attention_turn.judge` (the ratchet asked for an
    # extraction, not a bigger ceiling). The guard follows the CODE — the claim is unchanged.
    gate_src = _re.sub(r"(?m)#.*$", "",
                       open("voice/engine/llm/providers/attention_turn.py", encoding="utf-8").read())
    prov_src = _re.sub(r"(?m)#.*$", "",
                       open("voice/engine/llm/providers/nucleo.py", encoding="utf-8").read())
    assert "note_wakeword_spotted()" in agent_src
    assert "reclaim_ambient_tail(" in gate_src and "note_ambient(" in gate_src
    assert "attention_turn.judge(" in prov_src, "…and the turn still goes through it"


# ── V2-646: a TYPED turn is never ambient ────────────────────────────────────────────────────────────────
# Measured live 2026-09-09 22:30:39: the operator TYPED «puedes ponermela en youtube o de alguna forma?»,
# the model spent its 51 tokens on a `play_video` the canvas-license guard vetoed as context-bleed, the
# `deduped` flag marked the turn handled, and the mute backstop stayed quiet — completion_chars=0 and no
# answer at all to a question he had sat down and written. The V2-633/634 silence exemptions exist for
# AMBIENT speech dragged in from the room; a typed sentence can never be that, and this is the fact the
# provider reads to tell the two apart.

def test_a_typed_turn_is_stamped_and_readable():
    attention.note_typed(now=1000.0)
    assert attention.was_typed(now=1000.5), "the turn being handled right after a typed message IS typed"


def test_the_typed_stamp_expires_so_a_later_spoken_turn_is_not_mislabelled():
    attention.note_typed(now=1000.0)
    assert not attention.was_typed(now=1000.0 + 46.0), \
        "a chat message from minutes ago must never re-classify a spoken turn as typed"


def test_with_nothing_typed_the_answer_is_no():
    attention._state["typed_at"] = 0.0
    assert not attention.was_typed(now=1000.0)


def test_the_text_channel_stamps_it_and_the_provider_reads_it():
    """Parallel-impl guard: the stamp is worthless if the text handler stops writing it, or the provider
    stops reading it — and neither failure is loud. The provider's use is the one that matters: a vetoed
    (`deduped`) action must not count as «handled» on a typed turn, or the backstop goes quiet again."""
    import os
    eng = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    handler = open(os.path.join(eng, "voice/engine/pipeline/agent.py")).read()
    assert "attention.note_typed()" in handler, "the chat/paste handler no longer stamps typed turns"
    prov = open(os.path.join(eng, "voice/engine/llm/providers/nucleo.py")).read()
    assert "was_typed()" in prov, "the provider no longer reads whether the turn was typed"
    assert 'deduped["v"] and not _typed_turn' in prov, \
        "a vetoed action must stop counting as «handled» on a typed turn — that is the whole fix"


# ── a mode flip closes the standing window NOW (operator, 2026-09-10) ─────────────────────────────────────
# He activated the wake-word mode and the orb stayed orange 20+ seconds, riding out a window opened under
# the previous mode: «en el momento en que se activa el modo, en 3 segundos quiero el orbe gris».

def test_a_mode_flip_closes_an_open_window(monkeypatch):
    _smart(monkeypatch)
    t = 1000.0
    attention.note_directed(now=t)
    assert attention.window_open(now=t + 1)
    attention.on_mode_change("smart")
    assert not attention.window_open(now=t + 1)


def test_the_flip_tells_the_clients_so_the_ring_darkens_at_once(monkeypatch):
    import voice.observer as observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **k: seen.append((a, k)))
    attention.on_mode_change("smart")
    assert any(a[:2] == ("ui", "orb:attention") for a, _ in seen)


def test_settings_update_is_the_seam_and_only_a_REAL_change_wipes_the_window(monkeypatch, tmp_path):
    """Every mode writer (⚙ panel, the 🤖 button, the voice directive) goes through config.settings.update.
    A bulk save re-sending the SAME mode must not wipe a live conversation window."""
    from config import settings as cfg
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")    # register the key so teardown restores it (V2-571)
    cfg.update({"attention_mode": "smart"})             # change → wipes
    t = 2000.0
    attention.note_directed(now=t)
    assert attention.window_open(now=t + 1)
    cfg.update({"attention_mode": "smart"})             # SAME value → must not wipe
    assert attention.window_open(now=t + 1)
    cfg.update({"attention_mode": "always"})            # real change → wipes
    assert attention._state["last_directed"] == 0.0
