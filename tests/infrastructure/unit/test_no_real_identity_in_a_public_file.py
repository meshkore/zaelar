"""No real identity in a file this public repo tracks (V2-778 F0-5, 2026-09-30).

The rule has stood since 2026-08-14 — the catalogue of what is tested is public, the diary of what was tested is
ours — and the demo week broke it again without anything going red: the operator's own address sat in
`connectors/email/mailbox.py` and a memory gate, the demo's test contacts and errands in the docstrings of four
`nucleo/flash` modules and in some ninety tests. They were replaced by neutral placeholders (`@example.com`, Quinn,
Rowan, Orion). This is the ratchet that keeps the count at zero: a rule in prose was what had failed.

The patterns are assembled from pieces so this file does not match itself.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
_PIECES = ("pro" + "ars", "and" + "rew", "eth" + "an", "inworld " + "receipt", "hel" + "ix")
_RX = re.compile("|".join(_PIECES), re.I)


def _tracked() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=ENGINE, capture_output=True, text=True)
    return [p for p in r.stdout.split("\0") if p]


def test_no_tracked_file_carries_a_real_identity():
    hits = []
    for rel in _tracked():
        p = ENGINE / rel
        try:
            if p.stat().st_size > 2_000_000:
                continue
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n = len(_RX.findall(text))
        if n:
            hits.append(f"{rel}: {n}")
    assert not hits, ("a real identity (the operator's address, the demo's contacts) is in a PUBLIC file — use a "
                      f"neutral placeholder (@example.com, Quinn, Rowan): {hits[:20]}")
