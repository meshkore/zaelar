"""What the prompt modules emitted survives their move into `nucleo/turn/prompt/` (refactor2710-08, V2-826 §2b).

The static emit diff (merge-base → 08) finds 0 LOST and two pairs that only MOVED: the memory viewer's `memory.updated`
highlight from the recall block, and the introduction pack's phase-closed row. This reads them as EVENTS, from their new
homes: same kind, same label.

Disarm: rename the phase label in `packs/introduction.close` and the second test goes red.
"""
from __future__ import annotations


def test_the_introduction_says_its_phase_is_over(monkeypatch):
    from voice import observer
    from nucleo.turn.prompt.packs import introduction
    rows = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: rows.append((kind, label)))
    monkeypatch.setattr(introduction, "is_active", lambda: True)
    introduction.close("test")
    assert ("phase", "🎓 presentación terminada — su contexto se archiva") in rows
