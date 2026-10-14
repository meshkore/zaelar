"""Node 2.690 — on voice, an unbacked claim about a row is corrected after the words (they have streamed).

Spoken words cannot be cut, so `row_claims.said_after` sends one correction sentence — «Correction: I don't have this
verified for «iphone 17 256gb»: available.» — and returns the turn's words with it; a clean turn sends nothing. The
post-stream chain calls it right after the provenance caveat (`post_stream_settle`).

Disarm: `said_after` returning `spoken` unconditionally → the first test goes red; unwire it from the settle chain →
the wiring test goes red.
"""
from __future__ import annotations

import ast
from pathlib import Path

from i18n import langs
from nucleo.flash import claim_backing as B
from nucleo.flash import row_claims as R

ENGINE = Path(__file__).resolve().parents[3]
ROW = {"title": "iphone 17 256gb", "price": "699", "facts": [{"label": "Disponible ahora", "value": "?"}]}


class _Speech:
    @staticmethod
    def sanitize(text, drop_metadata=True):
        return text


def _sources(monkeypatch):
    monkeypatch.setattr(B, "rows", lambda: B.rows_of({"items": [ROW], "criteria": {"hard": ["Disponible ahora"]}}))
    monkeypatch.setattr(B, "texts", lambda *a, **k: [])
    monkeypatch.setattr(B, "goals", lambda: "")
    monkeypatch.setattr(B, "in_errand", lambda: True)


def test_the_correction_is_said_after_the_streamed_claim(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _sources(monkeypatch)
    sent = []
    spoken = "Yes, the 699 one is still available."
    total = R.said_after(spoken, sent.append, _Speech, "is the 699 one still available?")
    en = langs.spec("en")
    assert len(sent) == 1 and sent[0].startswith(en.claim_correction) and "available" in sent[0]
    assert total.startswith(spoken) and total.endswith(sent[0])


def test_a_clean_turn_sends_nothing(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _sources(monkeypatch)
    sent = []
    spoken = "The 699 one is the cheapest on the sheet; I haven't verified its stock yet."
    assert R.said_after(spoken, sent.append, _Speech, "and the 699?") == spoken and not sent


def test_the_settle_chain_says_it_after_the_streamed_words():
    tree = ast.parse((ENGINE / "nucleo/flash/post_stream_settle.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "said_after" and getattr(n.func.value, "id", "") == "_pst_rc"]
    assert calls, "post_stream_settle no longer says the row-claims correction"


def test_a_name_he_said_a_turn_ago_backs_the_spoken_answer(monkeypatch):
    """Demo pass 124 (2026-10-14), M2: «how's apple stock doing today» then «what about the last month» — the
    answer «Over the last month Apple is at 342.08 USD, up 2.70%.» got «Correction: I don't have that candidate on the
    sheet…» after it, inside a shortlist context (the monitors errand had just ended). The voice read only this turn's
    words; the conversation names Apple, as the text channel's `guard` already saw."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _sources(monkeypatch)
    sent = []
    spoken = "Over the last month Apple is at 342.08 USD, up 2.70%."
    window = [{"role": "user", "content": "how's apple stock doing today, show me the chart"},
              {"role": "assistant", "content": "Here's Apple's chart for today."}]
    assert R.said_after(spoken, sent.append, _Speech, "what about the last month", window) == spoken and not sent
    assert R.said_after(spoken, [].append, _Speech, "what about the last month") != spoken, "the case reproduces"


def test_the_settle_chain_hands_the_conversation_to_the_correction():
    src = (ENGINE / "nucleo/flash/post_stream_settle.py").read_text(encoding="utf-8")
    assert 'operator_text or text, list(getattr(brain, "_window", None) or []))' in src


def test_what_the_card_answered_backs_the_words_built_on_it(monkeypatch):
    """Demo pass 125 (2026-10-14), M3: «and the nasdaq, over the whole year» → «The NASDAQ Composite is at 26,676.49
    USD…» then «Correction: I don't have that candidate…». «Composite» was in the markets card's own answer — the
    data-op's return is a source, like a web search's."""
    from nucleo.flash import data_ops
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.setattr(B, "rows", lambda: [])
    monkeypatch.setattr(B, "goals", lambda: "")
    monkeypatch.setattr(B, "in_errand", lambda: True)
    monkeypatch.setattr(data_ops, "_LAST_ANSWER", {"at": 0.0, "text": ""})
    spoken = "The NASDAQ Composite is at 26,676.49 USD, up 17.62% over the past year."
    heard = "and the nasdaq, over the whole year"
    assert R.said_after(spoken, [].append, _Speech, heard) != spoken, "the case reproduces without the card's answer"
    data_ops.answer_of({"ok": True, "result": {"symbol": "^IXIC", "name": "NASDAQ Composite", "price": 26676.49}})
    sent = []
    assert R.said_after(spoken, sent.append, _Speech, heard) == spoken and not sent
