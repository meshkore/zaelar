"""Two readers that could still answer an ABSENCE without having seen it (V2-400).

They come from the tester's reliability audit (operator's instruction, 2026-08-27), not from a biting
round: they are the two remaining forms of the V2-396 class ("I asked and there was nothing" ≠ "I
could not ask"), found by reading each reader's code, and they are closed BEFORE costing a verdict.

1. **The `session_events` cap.** The event stream—the backbone of the entire report—is read with
   `limit=2000`. Historical measured maximum: 1,128 over 381 rounds, so it has never bitten—but the day
   a round exceeds it, families, widget_ops, and the entire audit will be calculated from a TRUNCATED
   stream and nothing anywhere will say so. It is invisible by construction, the exact failure class of
   this audit. The cap is raised (×2, ×3.5 margin over the highest seen value) and, above all, hitting the
   cap is REPORTED: to the report and the judge.

2. **`recall()` during seeding.** `except: return []`—if the engine does not answer during the 15
   iterations of the 45 s loop, `landed=False` and the judge reads "recall does NOT return them," which
   claims that it was asked. The truth was "it could not be asked." The protection for the agent happened
   to be the same; the claim was false.
"""
import ast
from pathlib import Path

from tests.use_cases.e2e.agent import judge as J, probe_client as P

BASE = Path("tests/use_cases/e2e/agent")


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


# ── 1. the cap ─────────────────────────────────────────────────────────────────────────────────────────────

def test_el_techo_da_margen_real_sobre_el_maximo_medido():
    import inspect
    sig = inspect.signature(P.session_events)
    assert sig.parameters["limit"].default >= 4000, "1.128 medidos: 2.000 de techo era margen ×1,8, no ×3,5"


def test_tocar_el_tope_se_apunta_en_el_informe():
    """`run.py` must check the RAW stream (before the time filter) against the cap—the filter
    hides truncation: 500 filtered events may come from a raw stream that hit the cap."""
    tree = ast.parse((BASE / "run.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_scenario")
    asigna = [n for n in ast.walk(fn) if isinstance(n, ast.Subscript)
              and isinstance(n.slice, ast.Constant) and n.slice.value == "event_stream_at_cap"]
    assert asigna, "nadie apunta en el informe que el flujo tocó techo"


def test_el_juez_lee_el_tope_como_informe_RECORTADO():
    txt = _texto(J.mechanism_facts({"event_stream_at_cap": {"raw": 4000, "limit": 4000}}))
    assert "RECORTADO" in txt.upper()
    assert "no prueba" in txt


def test_sin_tocar_el_tope_no_hay_aviso():
    assert "RECORTADO" not in _texto(J.mechanism_facts({"n_events": 300})).upper()


# ── 2. recall during seeding ─────────────────────────────────────────────────────────────────────────────

def test_un_recall_caido_devuelve_None(monkeypatch):
    def _boom(path, body, timeout=30.0):
        raise OSError("conexión rechazada")
    monkeypatch.setattr(P, "_post", _boom)
    assert P.recall("qué le gusta") is None, "una petición caída no es una memoria vacía"


def test_un_recall_vacio_sigue_siendo_lista_vacia(monkeypatch):
    monkeypatch.setattr(P, "_post", lambda path, body, timeout=30.0: {"results": []})
    assert P.recall("qué le gusta") == []


def test_la_siembra_incontestable_se_distingue_de_la_que_no_aterrizo():
    """The PROPERTY, not presence: the first guard grepped for `"unverifiable"` and survived
    `"unverifiable": False`—the word remained in the source with the decision dead."""
    from tests.use_cases.e2e.agent.run import seed_outcome
    caido = seed_outcome(sown=3, landed=False, asked_ok=False, waited=45.0, probe="vela")
    assert caido["unverifiable"] is True
    vacio = seed_outcome(sown=3, landed=False, asked_ok=True, waited=45.0, probe="vela")
    assert vacio["unverifiable"] is False, "se preguntó y no estaba: eso NO es incontestable"
    ok = seed_outcome(sown=3, landed=True, asked_ok=True, waited=6.0, probe="vela")
    assert ok["landed"] and not ok["unverifiable"]


def test_el_bucle_de_siembra_distingue_contestar_de_caerse(monkeypatch):
    """Actually driven, not grepped: with recall always down (None) → asked_ok False; with recall
    answering empty → asked_ok True without landing; with recall returning the seed → it landed."""
    from tests.use_cases.e2e.agent import run as R
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    monkeypatch.setattr(R.probe_client, "recall", lambda q, k=8: None)
    assert R._await_seed_landing("vela")[0:2] == (False, False)
    monkeypatch.setattr(R.probe_client, "recall", lambda q, k=8: [])
    assert R._await_seed_landing("vela")[0:2] == (False, True)
    monkeypatch.setattr(R.probe_client, "recall", lambda q, k=8: [{"text": "le gusta la vela"}])
    assert R._await_seed_landing("vela")[0:2] == (True, True)


def test_el_juez_dice_NO_SE_PUDO_PREGUNTAR():
    run = {"memory_seed": {"sown": 3, "landed": False, "unverifiable": True, "waited_s": 45.0,
                           "probe": "vela ligera"}}
    nota = J.seed_note_for(run["memory_seed"])
    assert "NO SE PUDO PREGUNTAR" in nota.upper()
    assert "no las devuelve" not in nota, "la nota vieja afirmaba que se preguntó"


# ── 3. the unreadable agenda that was "confirmed" empty ─────────────────────────────────────────────────

def test_una_agenda_ilegible_no_es_una_agenda_vacia(monkeypatch):
    """`widget_rows` swallows the error INSIDE (returns []), so run.py's try/except never catches it and
    the judge received "EMPTY—looked at and confirmed, zero appointments" for an agenda no one could read.
    Reading must go through `widget_data`, which does return None when it could not be inspected."""
    monkeypatch.setattr(P, "_get", lambda path, timeout=15.0: {"error": "conexión rechazada"})
    assert P.widget_data("agenda") is None
    src = (BASE / "run.py").read_text()
    assert 'widget_rows("agenda"' not in src, "la agenda se sigue leyendo por el lector que miente"
    assert 'widget_data("agenda")' in src


def test_la_nota_de_no_aterrizo_sigue_intacta():
    nota = J.seed_note_for({"sown": 3, "landed": False, "waited_s": 45.0, "probe": "x"})
    assert "NO VERIFICADA" in nota
    nota_ok = J.seed_note_for({"sown": 3, "landed": True, "probe": "x"})
    assert "NO VERIFICADA" not in nota_ok
