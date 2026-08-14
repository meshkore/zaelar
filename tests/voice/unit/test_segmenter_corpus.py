"""The segmenter, measured against the WHOLE local session registry (V2-095, 2026-08-14).

`test_segmenter.py` pins the rule against the 89 transcripts of a single session. That is how the rule was BUILT,
which is exactly why it is not enough to trust it: a rule tuned on one session is fitted to one session. This file
replays **every session the operator has on this machine** (195 files, 804 transcripts at the time of writing) and
measures the rule against production behaviour.

## The labels come from PRODUCTION, not from reading the sentence

For each final operator transcript, what happened NEXT in the real session decides the label:

  * **incomplete** — another operator transcript followed with no assistant answer in between, AND the turn was
    cancelled. The operator was still talking; the turn opened over that fragment was worth nothing.
  * **complete** — that transcript got an assistant answer.

## Why the `complete` label is NOT ground truth (and what that changes)

The agent answering a fragment IS the bug this rule exists to fix, so `complete` is contaminated by construction:
`'Es decir, actualiza la'` and `'Dejándolo preparado para'` are labelled complete because production answered them.
Measuring false positives against that set would score the rule against the very failure it corrects.

The `incomplete` label is contaminated too, in the other direction, and the split is measurable: **79 of the 275 end
with terminal punctuation**. Those are FINISHED sentences where the operator went on to add another one — a
different problem (multi-sentence dictation) that a "does this sentence dangle?" rule cannot own and should not be
blamed for. So the recall assertion below covers only the 196 with no terminal punctuation, which is the class this
rule is actually responsible for.

Being precise about that split is the whole point: reporting a single blended recall number would credit the rule
for a class it can't reach and punish it for another it shouldn't touch.

## The corpus is NOT committed, deliberately

These are verbatim recordings of the operator talking, including travel plans and appointments. **This repository is
public**, and `CLAUDE.md` records the leak that made this rule non-negotiable: 110 of 186 committed voice-battery
reports carried the operator's name and agenda items. So this test reads the registry at RUNTIME from
`.meshkore/logs/sessions/` (gitignored) and skips where there is none — same shape as
`tests/infrastructure/unit/test_roadmap_closure.py`. A clean clone skips; the operator's machine measures.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nucleo.flash import segmenter

ENGINE = Path(__file__).resolve().parents[3]
SESSIONS = ENGINE / ".meshkore/logs/sessions"

_TERMINAL = re.compile(r"[.!?…]['\")\]]*$")
_CANCEL = "turno cancelado"

# Floor for recall over fragments with no terminal punctuation. A RATCHET, like the closure guard: measured at 79%,
# pinned a little below so normal corpus growth doesn't turn into a red build, and it can only ever be raised.
# A rule that scores below this has stopped recognising dangling speech and needs looking at, not relaxing.
_RECALL_FLOOR = 0.70


def _label_session(p: Path) -> list[tuple[str, str]]:
    evs = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evs.append(json.loads(line))
        except Exception:
            continue
    idx = [i for i, e in enumerate(evs)
           if e.get("kind") == "transcript" and e.get("role") == "user" and (e.get("text") or "").strip()]
    out: list[tuple[str, str]] = []
    for n, i in enumerate(idx):
        text = (evs[i].get("text") or "").strip()
        nxt = idx[n + 1] if n + 1 < len(idx) else len(evs)
        between = evs[i + 1:nxt]
        answered = any(e.get("kind") == "transcript" and e.get("role") == "assistant"
                       and (e.get("text") or "").strip() for e in between)
        cancelled = any(_CANCEL in str(e.get("label") or "") for e in between)
        if answered:
            out.append((text, "complete"))
        elif cancelled and n + 1 < len(idx):
            out.append((text, "incomplete"))
    return out


# `para` is the trap that makes this guard hard to write: it is BOTH the imperative of «parar» and the commonest
# preposition in Spanish. «Para el» and «para ir de Denia a Ibiza,» are prepositions and genuine fragments — a guard
# that called them stop orders would demand the rule ship them and make things worse.
#
# Orthography settles it without any guessing: attaching the pronoun shifts the stress, so the imperative is written
# `páralo` / `párate` (accented, or with an enclitic), while the bare `para` is the preposition. So the guard only
# claims the UNAMBIGUOUS forms. Bare `para` on its own is covered by `_ALSO_A_VERB` inside the rule and by
# `test_segmenter.py`; here it is deliberately left out rather than half-guessed.
_STOP = re.compile(
    r"^\s*(?:vale[,. ]+|ok[,. ]+|y\s+|pues\s+)*(?:que\s+lo\s+)?"
    r"(?:p[áa]ra(?:lo|la|los|las|me|te)\b|p[áa]rate\b|pares\b|detén(?:lo|la|te)?\b"
    r"|ci[ée]rra(?:lo|la|los|las|me|melo)\b|cancél(?:alo|ala|amelo)\b"
    r"|c[áa]llate\b|basta\b|stop\b|d[ée]jalo\b|apág(?:alo|ue)\b)", re.I)


def _is_stop_order(t: str) -> bool:
    # A trailing comma is the STT saying out loud that more is coming («ciérrame todos los widgets,»); holding that
    # is correct behaviour, not a missed stop order.
    return bool(_STOP.match(t)) and not re.search(r"[,;:]\s*$", t)


def _corpus() -> dict[str, str]:
    """Deduped, and a phrase that appears with BOTH labels is dropped: an ambiguous label is worse than no label."""
    seen: dict[str, set[str]] = {}
    for p in sorted(SESSIONS.glob("*.jsonl")):
        for text, lab in _label_session(p):
            seen.setdefault(text, set()).add(lab)
    return {t: next(iter(labs)) for t, labs in seen.items() if len(labs) == 1}


pytestmark = pytest.mark.skipif(
    not SESSIONS.is_dir() or not list(SESSIONS.glob("*.jsonl")),
    reason="the session registry is local to the operator's machine (gitignored): nothing to measure here")


@pytest.fixture(scope="module")
def corpus() -> dict[str, str]:
    c = _corpus()
    if len(c) < 30:
        pytest.skip(f"registry too small to measure anything ({len(c)} labelled transcripts)")
    return c


def test_recall_sobre_fragmentos_sin_puntuacion(corpus):
    """The class this rule OWNS: the operator paused mid-sentence and the STT did not close it."""
    frags = [t for t, lab in corpus.items() if lab == "incomplete" and not _TERMINAL.search(t)]
    hits = [t for t in frags if segmenter.looks_incomplete(t)[0]]
    recall = len(hits) / len(frags)
    assert recall >= _RECALL_FLOOR, (
        f"recall dropped to {recall:.0%} ({len(hits)}/{len(frags)}), floor is {_RECALL_FLOOR:.0%}. "
        f"Escaped: {[t for t in frags if not segmenter.looks_incomplete(t)[0]][:10]}")


def test_nunca_se_retiene_una_orden_de_PARAR(corpus):
    """The one thing this layer must never do. V2-092 is called «parar es parar»; a stop order delayed by up to
    `max_delay` is the operator watching the agent ignore them.

    This is not hypothetical — it is the bug this file caught. The first version of the rule treated final
    punctuation as irrelevant whenever the last word was a function word, so **«Y que lo pares todo.» and
    «Ciérralo todo y páralo todo.» were held**, both ending in «todo». Hence the _HARD/_SOFT split in the rule.
    """
    held = [t for t in corpus if _is_stop_order(t) and segmenter.looks_incomplete(t)[0]]
    assert not held, f"ORDERS TO STOP being held: {[(t, segmenter.looks_incomplete(t)[1]) for t in held]}"


def test_nunca_se_retiene_un_backchannel_ni_una_autorizacion(corpus):
    """«sí» / «no» / «vale» close a turn by definition, and they are how the operator authorises something
    irreversible. Holding the answer to a confirmation is holding the confirmation."""
    from voice import endpointing as ep
    bad = [t for t in corpus if ep.is_backchannel(t) and segmenter.looks_incomplete(t)[0]]
    assert not bad, f"backchannels being held: {bad}"


def test_las_ordenes_cortas_de_widget_pasan(corpus):
    """The regression that a single-session corpus hid: the first version of rule 5 («short and unclosed») held
    EVERY short order the operator gives — «pon música», «abre la agenda», «sube el volumen» — which is the most
    frequent thing they say.

    The membership test has to be decidable WITHOUT asking the rule, or the guard is circular. It is: an order that
    starts with an imperative and whose last word is a CONTENT word is complete («pon música»); one that ends on a
    function word is truncated («ponme también el», «busca también en todas las»), and holding that is right. Word
    count says nothing either way — that was the flaw in the first version of this guard.
    """
    verbs = re.compile(r"^\s*(abre|abr[ei]me|cierra|ci[ée]rrame|pon|ponme|quita|s[uú]be|baja|ens[ée]ñame|"
                       r"mu[ée]strame|dame|busca|sigue|siguiente|reproduce|vac[íi]a)\b", re.I)
    held = []
    for t in corpus:
        if not verbs.match(t) or re.search(r"[,;:]\s*$", t):
            continue
        words = re.sub(r"[^\w áéíóúüñÁÉÍÓÚÜÑ]+", " ", t).split()
        if len(words) < 2:
            continue
        last = segmenter._norm(words[-1])
        if last in segmenter._DANGLING or last in segmenter._NEEDS_OBJECT:
            continue                          # ends on a function word: truncated, holding it is correct
        if segmenter.looks_incomplete(t)[0]:
            held.append(t)
    assert not held, f"short orders being held: {[(t, segmenter.looks_incomplete(t)[1]) for t in held]}"


def test_el_techo_de_retencion_entrega_siempre(corpus):
    """No matter how incomplete the analysis thinks a phrase is, past `MAX_HOLD_S` it ships. Checked over the real
    corpus and not just one string: this layer can delay a turn, never lose it."""
    frags = [t for t, lab in corpus.items() if lab == "incomplete"][:200]
    still_held = [t for t in frags if segmenter.should_hold(t, held_s=segmenter.MAX_HOLD_S + 0.1)[0]]
    assert not still_held, f"held past the ceiling: {still_held[:5]}"
