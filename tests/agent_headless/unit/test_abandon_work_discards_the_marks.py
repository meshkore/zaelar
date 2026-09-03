"""Stopping is DISCARDING: no mark anywhere may keep saying «we are in the middle of X».

The operator, live and for the second time (2026-08-31): he pressed Reset, restarted everything, and the fresh
session's FIRST greeting said «sigo con lo del digestólogo en Soria» — with not one worker alive. Measured
chain: `reset_all` froze the pending escalation into `trabajo_interrumpido` BY DESIGN (the cautious 2026-07-10
sequence: freeze so a restart can resume), the durable `task.*` slots survived, the [RESET] short-term record
said the work «queda CONGELADO» — an invitation to resume, read by a model — and the window seeding
(`memory.recent_window`) re-imported the wiped conversation verbatim. Four doors, all walked through.

His decision supersedes 2026-07-10: «si he hecho un puto reset es para que me lo dejes limpio … si en la memoria
de corto plazo o en el estado estaba marcado que estábamos haciendo una tarea, eso también se tiene que
limpiar». And by VOICE too: «para todo lo que estamos haciendo y quédate tranquilo» must kill AND clean, without
closing the session.

`abandon_work` is the shared core (Reset button + voice order). `reset_all` adds what only a reset means:
ledger blank, rehydration trace forgotten, widgets blanked, and the CONVERSATION buffer invalidated — «el chat
se borra» includes the seed, or the wiped conversation walks back in through the side door.
"""
import time

import pytest

from memory import api as mem
from memory import db as memdb
from widgets import store as _wstore
from nucleo import reset


@pytest.fixture(autouse=True)
def _own_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    # ⚠️ AND THE WIDGET STORE, which is the half that bit (V2-567). `reset_all()` does not only touch the
    # memory DB: it calls `widgets.reset.blank_all()`, which walks `store.DATA_DIR` — a path computed AT IMPORT
    # TIME from `workspace.root()`, so `ZAELAR_WORKSPACE` set in a fixture arrives too late to move it. Measured
    # 2026-09-03: two runs of the deterministic suite BLANKED THE OPERATOR'S LIVE WIDGETS mid-session — the log
    # names his real sheet, `results--7ff4fd-1` — and he watched his browser and results cards empty themselves
    # while a real errand was running. He reported it as the agent misbehaving, and the agent apologised for it.
    # `blank_all` reads `store.DATA_DIR` at CALL time, so pointing the attribute is enough.
    monkeypatch.setattr(_wstore, "DATA_DIR", str(tmp_path / "widgets_data"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _plant_the_digestologo_world():
    """The exact residue measured on the operator's engine after his reset."""
    mem.set_state({"trabajo_interrumpido": {
        "cuando": "2026-08-31 19:53", "navegador": [],
        "escaladas": [{"request": "Busca especialistas en aparato digestivo (digestólogos) en Soria"}],
        "widgets_en_curso": []}})
    mem.set_state({"activity": [{"goal": "digestólogos"}], "sessions": [{"id": "1"}]})
    mem.write_now("La cita médica online de Sanitas exige entrar en Mi Sanitas", level="mid",
                  kind="task", slot="task.sanitas.cita")
    mem.write_now("Operador: búscame un digestólogo · zaelar: voy con ello", level="short", kind="conv",
                  meta={"source": "conv", "u": "búscame un digestólogo", "a": "voy con ello"})
    mem.write_now("[whatsapp] Rakel: termino en casa", level="short", kind="msg", meta={"source": "whatsapp"})
    mem.write_now("El operador vive en Soria", level="long", kind="fact")


# ── abandon_work: the shared core (voice «para todo» included) ────────────────────────────────────────────
def test_abandon_work_wipes_every_we_are_working_mark():
    _plant_the_digestologo_world()
    out = reset.abandon_work(source="voz")
    st = mem.state()
    assert st.get("trabajo_interrumpido") == {}, \
        "the frozen escalation in state is the literal text the greeting resumed from — it cannot survive a stop"
    assert st.get("activity") == [] and st.get("sessions") == []
    assert mem.by_slot_prefix("task.") == [], \
        "durable task.* slots are «we are in the middle of X» pills — discarded work cannot keep them"
    assert out["killed"]["task_slots"] >= 1


def test_abandon_work_leaves_a_record_that_forbids_resuming():
    """The old [RESET] card said the work «queda CONGELADO» — read by a model, an invitation to resume. The
    record is instruction-shaped now (V2-214): nothing pending, do not resume, do not claim to continue."""
    _plant_the_digestologo_world()
    reset.abandon_work(source="reset")
    texts = [c.get("text", "") for c in (mem.recent_short(6) or [])]
    stop_cards = [t for t in texts if t.startswith("[PARADO]")]
    assert stop_cards, "the stop has to leave its record in short-term — the brain must learn work was discarded"
    assert "CONGELADO" not in stop_cards[0], "«frozen, resumable» is exactly the reading that caused the lie"
    assert "DESCARTAR" in stop_cards[0] and "no retomes" in stop_cards[0].lower()


def test_abandon_work_does_not_touch_memories_that_are_not_work():
    """It discards WORK, never memory: profile facts, ingested messages and the conversation stay. (The
    conversation falls only under reset_all — the voice order happens MID-conversation.)"""
    _plant_the_digestologo_world()
    reset.abandon_work(source="voz")
    assert len(mem.recent_by_source("whatsapp")) == 1, "an ingested message is not work in progress"
    assert mem.recent_window() != [], "the voice order must NOT erase the ongoing conversation"
    assert any("Soria" in (c.get("text") or "") for c in mem.salient_long(10)), "facts survive"


# ── reset_all: what only a reset adds ─────────────────────────────────────────────────────────────────────
def test_reset_also_clears_the_conversation_seed():
    """«El chat se borra» includes the SEED: `recent_window` is what the provider re-imports after a restart,
    and it is exactly how «sigo con lo del digestólogo» reached a session with zero workers alive."""
    _plant_the_digestologo_world()
    reset.reset_all()
    assert mem.recent_window() == [], \
        "the wiped conversation walked back in through the window seeding — the reset has to close that door"
    assert len(mem.recent_by_source("whatsapp")) == 1, "…but an ingested message is not conversation residue"


def test_reset_state_holds_no_trace_of_the_discarded_goal():
    """End to end on the surface the model actually reads: after a reset, the composed state cannot contain the
    discarded errand's words anywhere."""
    _plant_the_digestologo_world()
    reset.reset_all()
    import json
    blob = json.dumps(mem.state(), ensure_ascii=False)
    assert "digestólogo" not in blob and "digestivo" not in blob, \
        "the goal text surviving anywhere in state is what turned a clean greeting into «sigo con ello»"


def test_the_discarded_detail_travels_to_observability_not_memory():
    """Forensics are not lost: WHAT was killed rides in the return (→ the RESET event, archived with the
    session) instead of in the memory the next session reads. A LIVE pending escalation is planted — the
    snapshot reads the live queue, not the state residue."""
    from nucleo.flash import escalate
    escalate.reset()
    escalate.escalate_to_slowbrain("Busca digestólogos en Soria con buena reputación")
    try:
        out = reset.reset_all()
    finally:
        escalate.reset()
    assert out["discarded"]["escaladas"], "the observability archive keeps what the reset killed"
    assert "digestólogos" in out["discarded"]["escaladas"][0]["request"]
    assert mem.state().get("trabajo_interrumpido") == {}, "…and memory keeps NOTHING of it"


# ── the VOICE door: «Zaelar, para todo … y quédate tranquilo» ─────────────────────────────────────────────
from pathlib import Path

NUCLEO = Path(__file__).resolve().parents[3] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def test_stop_worker_todo_also_discards_the_marks():
    """Source guard on the voice seam (this repo's convention): killing the workers without wiping the marks is
    the half-measure that made the next greeting resume a dead task. The handler must route «todo» through the
    same core the Reset button uses."""
    src = "\n".join(l for l in NUCLEO.read_text(encoding="utf-8").splitlines()
                    if not l.strip().startswith("#"))
    i = src.find('elif name == "stop_worker":')
    j = src.find('elif name == "answer_worker":', i)
    assert 0 < i < j, "the stop_worker handler moved: this guard would be watching nothing"
    block = src[i:j]
    assert "abandon_work_soon" in block, \
        "stop_worker('todo') has to discard the marks too — cancel_soon alone leaves state saying work continues"
    assert 'if _w == "todo"' in block, "…and only for TODO: killing ONE task must not discard the others' marks"


def test_abandon_work_soon_runs_without_a_loop():
    """The voice path schedules it on a loop; tests and sync callers have none — it must run direct, not crash."""
    _plant_the_digestologo_world()
    reset.abandon_work_soon(source="voz")
    assert mem.state().get("trabajo_interrumpido") == {}


def test_the_stop_record_expires_instead_of_becoming_a_memory():
    """V2-568 — a stop order is over in minutes; it must never climb into permanent memory.

    Measured 2026-09-03 in the operator's live DB: 411 [PARADO]-lineage pills alive at level mid (132 written
    on Aug 28 alone, by lab resets). The leak is structural: the record was written WITHOUT a ttl, and
    `consolidator.promote` is age-based and never looks at ttl — so short→mid→long and a discarded afternoon
    becomes biography. `expire_ttl` kills by created+ttl at ANY level, which makes one declared ttl the whole
    fix: this walks the record through promotion AND expiry and asserts the grave wins."""
    from memory import consolidator
    _plant_the_digestologo_world()
    reset.abandon_work(source="reset")
    db = memdb.get_db()
    row = db.query("SELECT id, ttl_days FROM memories WHERE text LIKE '[PARADO]%' AND valid=1 "
                   "ORDER BY id DESC LIMIT 1")[0]
    assert row["ttl_days"] is not None and 0 < float(row["ttl_days"]) <= 7, \
        "the record must declare a short lifespan at the write — that is the entire mechanism"
    # A week later: promotion has had every chance to climb it; expiry must still win.
    later = int(consolidator._now()) + 8 * 86400
    consolidator.promote(now=later)
    consolidator.expire_ttl(now=later)
    r = db.query("SELECT valid FROM memories WHERE id=?", (row["id"],))[0]
    assert r["valid"] == 0, "promoted or not, the stop record has to be dead a week later"
