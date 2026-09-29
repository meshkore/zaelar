"""Demo pass 48 (2026-09-29), V1: the susurro auditor queued «I don't think I've got your name yet — what should I call
you?» twenty seconds after a reset, before the setup turn that gave the name; it rode the first demo turn four
minutes later, the reply ended in that question, and the question made the act repair stand down — the videos were
never searched. A note may say how long it stays true; the susurro's repairs do."""
import time

from voice import brain_notes


def test_an_expired_note_is_not_delivered(monkeypatch):
    brain_notes.drain()
    brain_notes.push("[SISTEMA] (susurro) I don't think I've got your name yet.", ttl_s=90)
    brain_notes.push("[SISTEMA] Brain worker · Tarea completada: three monitors")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 240)
    out = brain_notes.drain()
    assert out == ["[SISTEMA] Brain worker · Tarea completada: three monitors"], out


def test_a_fresh_one_still_is():
    brain_notes.drain()
    brain_notes.push("[SISTEMA] (susurro) repair", ttl_s=90)
    assert brain_notes.drain() == ["[SISTEMA] (susurro) repair"]


def test_the_susurro_repairs_carry_a_ttl():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[3] / "nucleo/susurro/apply.py").read_text("utf-8")
    assert "brain_notes.push(note, ttl_s=_REPAIR_TTL_S)" in src
