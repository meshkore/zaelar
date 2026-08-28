"""V2-469 · `offered` only read the BROWSER's notes — the search channel and the worker's narration were
invisible, and rule 1 of the rubric had nowhere to look.

Measured in `cheapest-monitor__us` (00:04): 10 real system notes pushed («Una búsqueda web ha devuelto
esto…») and the worker narrating «El LG 27UP650K-W aparece a $194.99 en Amazon (mínimo histórico)» then
«Confirmado por varias fuentes (Technobezz $194.99, Lifehacker $196.99)» — and `offered.n_offered: 0`,
because the parser required the navigator's «SACADO» header. With offered empty, the judge's rule 1
(«busca el nombre y el precio en offered.with_price») failed open into [alta] «afirmación de éxito falsa»
over a price the worker had verified against two sources.
"""
import json
import sqlite3

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, events):
    p = tmp_path / "s.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for ts, kind, label, payload in events:
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                    (ts, "observer", kind, label, json.dumps(payload, ensure_ascii=False)))
    con.commit(); con.close()
    return str(p)


_SEARCH_NOTE = ("[SISTEMA] Una búsqueda web ha devuelto esto, trabajando en «Find a good-value monitor for "
                "Alex (a work monitor, not gaming-focused»: LG 27UP650K-W 27-inch Ultrafine 4K UHD "
                "(3840 x 2160) IPS ... - Amazon — The 27-inch UHD 4K IPS display reproduces clear images")
_NARRATION = "El LG 27UP650K-W aparece a **$194.99 en Amazon** (mínimo histórico). Verifico que sea reciente."


def test_a_search_note_is_an_offer(tmp_path):
    db = _db(tmp_path, [(1000, "brain", "nota", {"text": _SEARCH_NOTE})])
    out = verify.offered_to_brain(db)
    assert out["n_offered"] == 1
    assert any("LG 27UP650K-W" in t for t in out["titles"])


def test_the_workers_narration_is_readable_by_the_judge(tmp_path):
    db = _db(tmp_path, [(1000, "task", "💬 worker", {"text": _NARRATION})])
    out = verify.offered_to_brain(db)
    assert any("$194.99" in n for n in out.get("narrated") or [])


def test_the_browser_note_still_parses_exactly_as_before(tmp_path):
    nav = ("El navegador ha SACADO esto de la página, trabajando en «busca monitores»: "
           "Dell S2725QS — 289 € — https://x.example/a. Nadie más lo sabe.")
    db = _db(tmp_path, [(1000, "brain", "nota", {"text": nav})])
    out = verify.offered_to_brain(db)
    assert out["titles"] == ["Dell S2725QS"]
    assert out["with_price"] == ["Dell S2725QS — 289 €"]


def test_the_rubric_tells_the_judge_about_the_narration():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text(encoding="utf-8")
    assert "narrated" in src.split("INVENTÓ un dato", 1)[1][:900]
