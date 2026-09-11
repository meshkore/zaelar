"""The phrasebook: a greeting is answered from a table, in any language, and nothing else is (V2-674).

Measured in the operator's own English session (sid fdd096a3, 2026-09-11) before a line was written:
«Hello and good morning. How are you?» → 3 440 ms of model covered by «Let me explain…»; «You were saying?»
→ «One sec, checking…» and then an INVENTED WhatsApp errand; «Hey, mate. You there?» → «Let me check that
for you…». None of the three is a request.

The asymmetry this file exists to hold: answering «hola» with a model costs three seconds, and answering a
real request with «¡Hola! Dime.» is a broken product. So the permissive cases are checked with one test each
and the REFUSING cases with many — a false positive here is the expensive direction.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nucleo.flash import presence, smalltalk
from voice.engine.core import langs

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture()
def es():
    return langs.smalltalk_book("es")


@pytest.fixture()
def en():
    return langs.smalltalk_book("en")


# ── the three measured sentences ────────────────────────────────────────────────────────────────────────
def test_the_operators_own_greeting_never_reaches_a_model(en):
    """His literal first sentence of that session, two phrases glued by «and» with no punctuation."""
    assert smalltalk.classify("Hello and good morning. How are you?", en) == "how_are_you"


def test_the_answered_intent_is_the_one_that_ASKS(es):
    """«Hola, ¿qué tal?» is a question with a greeting in front of it. Answering the greeting would leave
    the question hanging, which is the whole reason the LAST hit wins."""
    assert smalltalk.classify("Hola, ¿qué tal?", es) == "how_are_you"
    assert smalltalk.classify("Hola.", es) == "greeting"


def test_a_knock_with_an_address_in_the_middle_is_still_a_knock(en):
    """«Hey, mate. You there?» — the word standing between this sentence and the presence lane was «mate»."""
    voc = tuple(en.get("vocatives") or ())
    assert presence.is_presence_check("Hey, mate. You there?", "", voc)
    assert presence.is_presence_check("You there?", "", voc)
    # …and an address with a REQUEST after it is not a knock, whatever the address.
    assert not presence.is_presence_check("mate, open the agenda", "", voc)


def test_a_question_about_the_conversation_gets_no_thinking_sound():
    from voice.engine.speech import filler_audio
    assert filler_audio.filler_kind("You were saying?") == "social"
    assert filler_audio.filler_kind("what were you saying") == "social"


# ── the refusals, which are the expensive direction ─────────────────────────────────────────────────────
@pytest.mark.parametrize("phrase", [
    "abre la agenda",
    "Hola, ¿me abres la agenda?",          # a greeting with cargo is a real turn
    "¿Qué tal el tiempo en Madrid?",       # «qué tal» inside a real question
    "gracias por abrir la agenda",
    "adiós a todos los widgets abiertos",
    "buenos días, ¿qué tengo hoy?",
    "hola qué tal el partido",
    "",
    "   ",
])
def test_a_sentence_with_cargo_is_never_small_talk(es, phrase):
    assert smalltalk.classify(phrase, es) == ""


def test_one_unknown_piece_disqualifies_the_whole_utterance(es):
    """The rule is decomposition, not containment: every segment must be phatic."""
    assert smalltalk.classify("Hola. Pon música.", es) == ""


def test_an_utterance_longer_than_small_talk_is_refused(es):
    assert smalltalk.classify("hola " * 12, es) == ""


# ── the bounce gate ─────────────────────────────────────────────────────────────────────────────────────
def test_bien_only_means_im_fine_right_after_we_asked(es):
    """«bien» on its own is usually an ANSWER to something we asked. It may only be read as small talk while
    our own previous reply handed the question back — V2-665's defect with the roles reversed."""
    assert smalltalk.classify("bien", es) == ""
    assert smalltalk.classify("bien", es, bounce_pending=True) == "im_fine"


def test_the_bounce_flag_comes_from_the_reply_we_are_about_to_give(es):
    assert smalltalk.bounces("how_are_you", es) is True
    assert smalltalk.bounces("greeting", es) is False
    assert smalltalk.bounces("thanks", es) is False


# ── the pools ───────────────────────────────────────────────────────────────────────────────────────────
def test_the_same_greeting_twice_does_not_give_the_same_sentence(es):
    """The operator asked for «una especie de diálogo heurístico, un poco random», not a canned line."""
    first = smalltalk.reply_for("greeting", es)
    for _ in range(20):
        assert smalltalk.reply_for("greeting", es, avoid=first) != first


def test_an_empty_pool_answers_NOTHING_rather_than_answering_wrong():
    book = {"intents": {"greeting": {"cues": ["hola"], "replies": []}}}
    assert smalltalk.classify("hola", book) == "greeting"
    assert smalltalk.reply_for("greeting", book) == ""


def test_every_how_are_you_reply_hands_the_question_back():
    """The intent is declared `bounces`, and the next turn's «bien» is gated on that. A pool where some
    replies ask back and some do not makes the gate fire after a reply that asked nothing."""
    for code in ("es", "en"):
        book = langs.smalltalk_book(code)
        for reply in book["intents"]["how_are_you"]["replies"]:
            assert "?" in reply, f"{code}: {reply!r} does not hand the question back"


def test_a_cue_belongs_to_one_intent_unless_a_gate_separates_them():
    """Two ungated intents sharing a cue is an ambiguity nothing can resolve — the first one always wins and
    the other is dead. Sharing IS allowed when exactly one of them is gated (Spanish «todo bien»)."""
    for code in ("es", "en"):
        book = langs.smalltalk_book(code)
        seen: dict[str, list[str]] = {}
        for name, spec in book["intents"].items():
            for cue in spec["cues"]:
                seen.setdefault(smalltalk._norm(cue), []).append(name)
        for cue, owners in seen.items():
            if len(owners) > 1:
                gated = [o for o in owners if book["intents"][o].get("after_bounce")]
                assert len(owners) - len(gated) <= 1, f"{code}: {cue!r} shared by {owners}"


# ── language agnosticism ────────────────────────────────────────────────────────────────────────────────
def test_a_language_with_no_phrasebook_gets_no_canned_lines():
    """`spec()` answers with the ACTIVE language for anything it does not know, which would hand a German
    operator the ENGLISH table — and «hello» would then be answered in English, deterministically."""
    assert langs.smalltalk_book("de") == {}
    assert smalltalk.classify("Hallo", {}) == ""


def test_normalization_does_not_delete_a_non_latin_script():
    """An `[a-z]` allowlist — the first thing one writes here — empties a Chinese, Russian or Arabic
    utterance down to nothing, which would make this module silently unusable in every language but two."""
    for text in ("你好", "Привет", "مرحبا", "こんにちは"):
        assert smalltalk._norm(text), f"{text!r} normalized to nothing"


def test_a_generated_pack_wins_over_the_hardcoded_table(monkeypatch):
    fake = {"vocatives": ["tio"], "joiners": ["y"],
            "intents": {"greeting": {"cues": ["buenas"], "replies": ["¡Muy buenas!"]}}}
    monkeypatch.setattr("i18n.init.fillers.read_smalltalk", lambda code: fake)
    book = langs.smalltalk_book("es")
    assert book["intents"]["greeting"]["replies"] == ["¡Muy buenas!"]
    # …and an intent the pack did NOT translate keeps the hardcoded one instead of disappearing.
    assert book["intents"]["thanks"]["replies"]


def test_the_generated_pack_never_carries_the_behavioural_flags():
    """`bounces` / `after_bounce` are rules about the CONVERSATION, not facts about the language. A pack that
    could set them would let a translator quietly change how the lane behaves."""
    from i18n.init import smalltalk as gen
    parsed = gen._parse('{"intents": {"greeting": {"cues": ["x"], "replies": ["y"], "bounces": true},'
                        ' "how_are_you": {"cues": ["z"], "replies": ["w"]}}}')
    assert parsed["intents"]["greeting"].get("bounces") is None
    assert parsed["intents"]["how_are_you"]["bounces"] is True


def test_a_pack_missing_half_an_intent_is_dropped_whole():
    """A cue with no replies would MATCH an utterance and then answer nothing — worse than no pack."""
    from i18n.init import smalltalk as gen
    assert gen._parse('{"intents": {"greeting": {"cues": ["hola"]}}}') == {}
    assert gen._parse('{"intents": {"invented": {"cues": ["a"], "replies": ["b"]}}}') == {}


# ── wiring: both channels, and the gates ────────────────────────────────────────────────────────────────
def _code(path: Path) -> str:
    """Source with comments and docstrings stripped — a guard that reads PROSE goes red when somebody
    documents the rule it enforces (V2-615's trap)."""
    import io
    import tokenize
    out, prev_end, prev_type = [], (1, 0), None
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING and prev_type in (None, tokenize.INDENT, tokenize.NEWLINE,
                                                             tokenize.NL):
                continue
            out.append(tok.string)
            prev_end, prev_type = tok.end, tok.type
    return " ".join(out)


def test_both_channels_answer_a_set_phrase():
    """V2-539's rule: wire BOTH channels, or the probe hands out verdicts the product never gives."""
    voice = _code(ENGINE / "voice/engine/llm/providers/nucleo.py")
    # The probe channel is TWO files since the V2-674 ratchet pass: the call site and the lane bodies. A
    # guard pointed at a single file goes green the day the lane silently falls out of the path (V2-555).
    probe = _code(ENGINE / "nucleo/flash/probe.py") + _code(ENGINE / "nucleo/flash/probe_actionmap.py")
    assert "small_talk" in voice, "the voice provider does not call the phrasebook lane"
    assert re.search(r"_smalltalk\s*\.\s*mirror", probe), "the probe channel has no phrasebook mirror"
    assert "try_fast_lanes" in probe, "the probe's lane chain is not wired from probe.py"


def test_the_lane_declines_on_the_first_turn_and_while_a_worker_is_asking():
    lane = _code(ENGINE / "voice/engine/llm/providers/fast_lane.py")
    m = re.search(r"async def small_talk\b.*?(?=\ndef |\nasync def |\Z)", lane, re.S)
    assert m, "small_talk not found"
    body = m.group(0)
    assert "first_turn or ask_waiting" in body, (
        "the two gates must both be checked: the kickoff is not a conversation yet, and a «gracias» while a "
        "worker's question is pending may be the ANSWER to it")


def test_the_exchange_lands_in_the_window_and_the_conv_buffer():
    """V2-605's canned-line lesson: a phrase of ours that skips the history erases its own story, and the
    next model turn answers a greeting it has no record of receiving."""
    lane = _code(ENGINE / "voice/engine/llm/providers/fast_lane.py")
    m = re.search(r"async def small_talk\b.*?(?=\ndef |\nasync def |\Z)", lane, re.S)
    body = m.group(0)
    assert "push_user" in body and "_window . append" in body.replace("_window.append", "_window . append")
    assert "kind = \"conv\"" in body.replace('kind="conv"', 'kind = "conv"')


def test_the_probe_mirror_is_deterministic(es):
    """A test channel that rolls dice cannot be asserted on — the mirror takes the FIRST phrase."""
    class _S:
        window: list = []
        smalltalk_bounce = False
    s = _S()
    s.window = []
    got = smalltalk.mirror("Hola.", s, "t1", es)
    assert got and got["action"] == "smalltalk"
    assert got["reply"] == [es["intents"]["greeting"]["replies"][0]]
    assert s.window[-1] == {"role": "assistant", "content": got["reply"][0]}


def test_the_probe_mirror_clears_the_bounce_on_any_other_turn(es):
    class _S:
        window: list = []
        smalltalk_bounce = True
    s = _S()
    s.window = []
    assert smalltalk.mirror("abre la agenda", s, "t1", es) is None
    assert s.smalltalk_bounce is False, (
        "a sentence that is not small talk takes the question out of the air; leaving the flag set lets a "
        "«bien» three turns later be read as an answer to a question nobody remembers asking")
