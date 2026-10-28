"""A fix is a mechanism, never a word: regexes and word tables in product code only get RARER (CRIT-W10).

Operator, 2026-10-19: «no más arreglos para que tests individuales funcionen. Tenemos que hacer mejoras a nivel
estructural que arreglen el sistema y como resultado los tests funcionen — esto es un producto global, que debe
poder atender cualquier request.»

The doctrine was already written (CRIT-W1, «mechanisms, not rules») and it did not hold: the 72-hour audit V2-783
classified 30 of 99 product commits as a regex, a word table or a net over the model's words, born from one
recorded case each — 87 `re.compile` added and 4 removed, `search/` alone from 43 to 83. A sentence in a document
loses to a red test every time; this is the test.

Counted by AST over tracked product files (tests and `i18n/` excluded — `i18n/` is the DECLARED home of language
data, one table per language, so moving vocabulary there is a payment, not a loophole):
  · `re.compile(…)` calls anywhere;
  · module-level word tables — a set / frozenset / tuple / list / dict-of-keys literal, or `"…".split()`, holding
    three or more strings.
The totals may only fall. A new one is paid by removing one elsewhere in the same commit — which is the point:
before adding a word, find the verdict, the declared datum or the structure that makes the words unnecessary.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

#: Measured 2026-10-19 at 295ff4ec (366 files). Lower these when you remove; never raise them.
MAX_REGEXES = 501   # refactor2710-03: the word gates over our own reply went (was 532); refactor2710-01: the old text channel went (was 543); V2-806: the spoken-rule parsers went
MAX_WORD_TABLES = 462  # refactor2710-03: the claim vocabulary went; refactor2710-12: two dispatch tables read off their handler names; refactor2710-01: the old text channel's reply door went; refactor2710-11: a guessed dimension row went (was 476)


def _strings(v) -> int:
    if isinstance(v, ast.Call) and getattr(v.func, "id", "") in ("frozenset", "set", "tuple", "list") and v.args:
        v = v.args[0]
    if isinstance(v, (ast.Set, ast.List, ast.Tuple)):
        return sum(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in v.elts)
    if isinstance(v, ast.Dict):
        # A record of state or of numeric limits (`{"sid": None, "ts": 0.0}`, `{"tracks": 10}`) names fields, it
        # reads no words: a table maps words to words (or to declared values), so at least one value is a string
        # or a name.
        if v.values and all(isinstance(x, ast.Constant) and not isinstance(x.value, str) for x in v.values):
            return 0
        return sum(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in v.keys if k is not None)
    if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "split"
            and isinstance(v.func.value, ast.Constant) and isinstance(v.func.value.value, str)):
        return len(v.func.value.value.split())
    return 0


def _counts() -> dict[str, tuple[int, int]]:
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    out: dict[str, tuple[int, int]] = {}
    for rel in files:
        if rel.startswith(("tests/", "i18n/")) or "/tests/" in rel or not (ENGINE / rel).exists():
            continue
        try:
            tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rx = sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "compile"
                 and getattr(n.func.value, "id", "") == "re" for n in ast.walk(tree))
        # `A, B, C = "a", "b", "c"` declares named constants, one per target — not a table anything is looked up in.
        wt = sum(isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None and _strings(n.value) >= 3
                 and not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple))
                 for n in tree.body)
        if rx or wt:
            out[rel] = (rx, wt)
    return out


def test_regexes_and_word_tables_only_get_rarer():
    counts = _counts()
    rx = sum(a for a, _ in counts.values())
    wt = sum(b for _, b in counts.values())
    top = sorted(counts.items(), key=lambda kv: -sum(kv[1]))[:5]
    assert rx <= MAX_REGEXES and wt <= MAX_WORD_TABLES, (
        f"product code holds {rx} regexes (ceiling {MAX_REGEXES}) and {wt} word tables (ceiling {MAX_WORD_TABLES}). "
        "A fix that adds words reads ONE case; the product must answer any request (CRIT-W10). Find the verdict, the "
        "declared datum or the structure instead — or pay it by removing one elsewhere. Largest holders: "
        + ", ".join(f"{k} {v}" for k, v in top))


def test_the_ceiling_is_not_slack():
    """A ceiling far above the count lets the next patch in unseen: lower it when you remove (slack ≤ 10)."""
    counts = _counts()
    assert MAX_REGEXES - sum(a for a, _ in counts.values()) <= 10
    assert MAX_WORD_TABLES - sum(b for _, b in counts.values()) <= 10
