"""Dos lectores que aún podían responder una AUSENCIA sin haberla visto (V2-400).

Salen de la auditoría de fiabilidad del tester (orden del operador, 2026-08-27), no de una ronda que
mordiera: son las dos formas que quedaban de la clase de V2-396 («pregunté y no había nada» ≠ «no pude
preguntar»), encontradas leyendo el código de cada lector, y se cierran ANTES de costar un veredicto.

1. **El tope de `session_events`.** El flujo de eventos —el TRONCO del informe entero— se lee con
   `limit=2000`. Máximo histórico medido: 1.128 en 381 rondas, así que nunca ha mordido — pero el día que
   una ronda lo supere, familias, widget_ops y la auditoría entera se calcularán sobre un flujo RECORTADO
   y nada en ninguna parte lo dirá. Es el fallo invisible por construcción, la clase exacta de esta
   auditoría. Se sube el techo (×2, margen ×3,5 sobre el máximo visto) y, sobre todo, tocar el tope SE
   DICE: al informe y al juez.

2. **`recall()` en la siembra.** `except: return []` — si el motor no contesta las 15 veces del bucle de
   45 s, `landed=False` y el juez lee «el recall NO las devuelve», que afirma que se preguntó. La verdad
   era «no se pudo preguntar». La protección al agente era la misma de casualidad; la afirmación era
   falsa.
"""
import ast
from pathlib import Path

from tests.use_cases.e2e.agent import judge as J, probe_client as P

BASE = Path("tests/use_cases/e2e/agent")


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


# ── 1. el tope ─────────────────────────────────────────────────────────────────────────────────────────────

def test_el_techo_da_margen_real_sobre_el_maximo_medido():
    import inspect
    sig = inspect.signature(P.session_events)
    assert sig.parameters["limit"].default >= 4000, "1.128 medidos: 2.000 de techo era margen ×1,8, no ×3,5"


def test_tocar_el_tope_se_apunta_en_el_informe():
    """`run.py` tiene que mirar el flujo CRUDO (antes del filtro por tiempo) contra el techo — el filtro
    esconde el recorte: 500 eventos filtrados pueden venir de un crudo que tocó techo."""
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


# ── 2. el recall de la siembra ─────────────────────────────────────────────────────────────────────────────

def test_un_recall_caido_devuelve_None(monkeypatch):
    def _boom(path, body, timeout=30.0):
        raise OSError("conexión rechazada")
    monkeypatch.setattr(P, "_post", _boom)
    assert P.recall("qué le gusta") is None, "una petición caída no es una memoria vacía"


def test_un_recall_vacio_sigue_siendo_lista_vacia(monkeypatch):
    monkeypatch.setattr(P, "_post", lambda path, body, timeout=30.0: {"results": []})
    assert P.recall("qué le gusta") == []


def test_la_siembra_incontestable_se_distingue_de_la_que_no_aterrizo():
    """La PROPIEDAD, no la presencia: el primer guarda grepeaba `"unverifiable"` y sobrevivía a
    `"unverifiable": False` — la palabra seguía en el fuente con la decisión muerta."""
    from tests.use_cases.e2e.agent.run import seed_outcome
    caido = seed_outcome(sown=3, landed=False, asked_ok=False, waited=45.0, probe="vela")
    assert caido["unverifiable"] is True
    vacio = seed_outcome(sown=3, landed=False, asked_ok=True, waited=45.0, probe="vela")
    assert vacio["unverifiable"] is False, "se preguntó y no estaba: eso NO es incontestable"
    ok = seed_outcome(sown=3, landed=True, asked_ok=True, waited=6.0, probe="vela")
    assert ok["landed"] and not ok["unverifiable"]


def test_el_bucle_de_siembra_distingue_contestar_de_caerse(monkeypatch):
    """Conducido de verdad, no grepeado: con recall siempre caído (None) → asked_ok False; con recall
    contestando vacío → asked_ok True sin aterrizar; con recall trayendo la siembra → aterrizó."""
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


# ── 3. la agenda ilegible que se «confirmaba» vacía ────────────────────────────────────────────────────────

def test_una_agenda_ilegible_no_es_una_agenda_vacia(monkeypatch):
    """`widget_rows` traga el error DENTRO (devuelve []), así que el try/except de run.py no salta nunca y
    el juez recibía «VACÍA — mirada y confirmada, cero citas» sobre una agenda que nadie pudo leer. La
    lectura tiene que ir por `widget_data`, que sí devuelve None cuando no se pudo mirar."""
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
