"""Tests de la ACOTACIÓN por contexto del enrutado de widgets (V2-078, idea del operador): ante un EMPATE de
score, el widget objetivo se desempata por prioridad **abiertos > usados hace poco > catálogo** — genérico, sin
frases hardcodeadas. Cubre `runtime.identify` (tiebreak + score), `state.push_recent_widgets` (MRU) y el orden/
anotación de `brief.for_prompt`."""
from widgets import runtime


def _row(wid: str, kw: str) -> dict:
    """Fila del índice de identify para un widget ficticio con UNA keyword (para forzar empates controlados)."""
    return {"w": {"id": wid, "title": wid}, "kws": [kw], "kw_tokens": {kw},
            "name": wid, "title": wid, "name_tokens": {wid}, "desc_tokens": set()}


def test_tie_broken_by_open(monkeypatch):
    # Dos widgets con la MISMA keyword → "cita" empata a ambos.
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # Sin contexto: ambiguo, sin match.
    r = runtime.identify("una cita")
    assert r["match"] is None and r["ambiguous"] is True and r["score"] > 0
    # Con 'agenda' ABIERTA: gana agenda.
    r = runtime.identify("una cita", open_ids=["agenda"])
    assert r["match"] == "agenda" and r["ambiguous"] is False


def test_open_beats_recent(monkeypatch):
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # 'mensajeria' abierta, 'agenda' reciente → manda la ABIERTA (1ª capa).
    r = runtime.identify("una cita", open_ids=["mensajeria"], recent_ids=["agenda"])
    assert r["match"] == "mensajeria"


def test_recent_breaks_tie_when_nothing_open(monkeypatch):
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # Nada abierto, pero 'agenda' usada hace poco → gana por la 2ª capa.
    r = runtime.identify("una cita", recent_ids=["agenda"])
    assert r["match"] == "agenda"


def test_recent_normalises_instance_ids(monkeypatch):
    monkeypatch.setattr(runtime, "_identify_index", lambda: [_row("agenda", "cita"), _row("mensajeria", "cita")])
    # ids de instancia (navegador::t1) se normalizan a la base.
    r = runtime.identify("una cita", recent_ids=["agenda::t9"])
    assert r["match"] == "agenda"


def test_unambiguous_name_ignores_context(monkeypatch):
    # 'agenda' gana por score (id-hit=3) aunque 'mensajeria' esté abierta → el contexto solo rompe EMPATES.
    monkeypatch.setattr(runtime, "_identify_index",
                        lambda: [_row("agenda", "cita"), _row("mensajeria", "mensaje")])
    r = runtime.identify("abre la agenda", open_ids=["mensajeria"])
    assert r["match"] == "agenda"


def test_push_recent_widgets_mru(tmp_path, monkeypatch):
    # MRU real contra el estado: dedup, la más reciente delante, cap.
    from memory import state
    seen = {}

    def _read():
        return dict(seen.get("v", dict(state._DEFAULT)))

    def _write(d):
        seen["v"] = dict(d)

    monkeypatch.setattr(state, "read", _read)
    monkeypatch.setattr(state, "write", _write)
    state.push_recent_widgets("agenda")
    state.push_recent_widgets(["mensajeria", "clock"])
    state.push_recent_widgets("agenda")           # re-uso → sube al frente, sin duplicar
    out = _read()["recent_widgets"]
    assert out[0] == "agenda"
    assert out.count("agenda") == 1
    assert set(out) == {"agenda", "mensajeria", "clock"}
    # cap: nunca crece sin límite
    for i in range(20):
        state.push_recent_widgets(f"w{i}")
    assert len(_read()["recent_widgets"]) <= state._RECENT_CAP


def test_for_prompt_orders_and_marks():
    from widgets import brief
    txt = brief.for_prompt(open_ids=["agenda"], recent_ids=["clock"])
    # El abierto se marca EN PANTALLA; el reciente, usado hace poco.
    assert "EN PANTALLA" in txt and "usado hace poco" in txt
    lines = [l for l in txt.splitlines() if l.startswith("- ")]
    ids = [l.split()[1] for l in lines]
    assert ids and ids[0] == "agenda"                 # el abierto va primero
    assert ids.index("clock") < ids.index("mensajeria")  # el reciente antes que uno cualquiera del catálogo
