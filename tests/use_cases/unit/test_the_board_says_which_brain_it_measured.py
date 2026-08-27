"""Una nota del marcador es una nota SOBRE algo, y ese algo es el cerebro que hizo el trabajo.

Cada fila ya sellaba qué JUEZ la calificó (`status.record`'s `judge`), por una medición del 2026-08-20: la
cadena del juez cae a otro proveedor cuando al titular se le acaba la cuota, y un caso que «bajó de 3 a 2»
puede haber cambiado solo de regla de medir. Un piso más abajo pasa lo mismo y pesa más: el juez es el
instrumento, el cerebro ES el producto.

Medido el 2026-08-27: una tanda de casos US corrió con z.ai sin cuota de 5 horas, así que sus Brain Workers
los sirvió el escalón de RELEVO (`deepseek-v4-flash`) en vez del titular que la nube contrata (`glm-5.3`).
Cinco filas con nota 1-2 iban a quedarse al lado de filas medidas con el titular, idénticas a la vista y
sobre otro producto. Lo cacé leyendo el log a mano; ni el tablero ni el registro lo guardaban en ningún sitio.

Los tests fijan la FORMA REAL del flujo, que es donde esto no hace ruido al romperse:
  · `observer.emit` hace `ev.update(extra)`, así que el modelo llega APLANADO y el payload es un STRING JSON.
  · `worker_start` lo reusa el ARRANQUE del motor de voz («motor de voz arriba»), que no tiene worker detrás
    y llama a su modelo `llm_model`.
  · una fila de relevo NO tiene `kind == "perf"`: el `extra={"kind": "exhausted"}` de la cadena pisa el kind
    del evento al guardarse.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import status as S
from tests.use_cases.e2e.agent import verify as V


def _worker_row(model: str, backend: str = "claude_code") -> dict:
    """Un `worker_start` tal y como lo devuelve `/api/observability/events`, no como se emite en proceso."""
    return {"kind": "worker_start", "cat": "worker",
            "payload": json.dumps({"kind": "worker_start", "label": f"worker · {backend}",
                                   "cat": "worker", "id": "1", "model": model, "layer": "web"})}


def _boot_row() -> dict:
    """El arranque del motor de voz: MISMO kind, ningún worker detrás, y su modelo se llama `llm_model`."""
    return {"kind": "worker_start", "cat": "worker",
            "payload": json.dumps({"kind": "worker_start", "label": "motor de voz arriba", "role": "system",
                                   "cat": "worker", "profile": "remote", "llm_model": "(default)"})}


def _relay_row(frm: str = "z.ai", to: str = "deepseek", why: str = "exhausted") -> dict:
    """Un relevo REAL: el `kind` guardado es el motivo, no `perf` — por el `ev.update(extra)` de `emit`."""
    return {"kind": why, "cat": "system",
            "payload": json.dumps({"kind": why, "cat": "system", "role": "cluster_brain",
                                   "label": f"\U0001f50c cerebro de cluster: «{frm}» sin crédito",
                                   "provider": frm, "next": to})}


def test_reads_the_model_from_the_shape_the_api_returns():
    got = V.brains_that_ran([_worker_row("glm-5.3"), _worker_row("glm-5.3")])
    assert got["n_by_worker"] == {"claude_code/glm-5.3": 2}
    assert got["mixed"] is False


def test_the_voice_engine_booting_is_not_a_brain_worker():
    """Sin esta línea toda ronda queda sellada con un cerebro que no corrió."""
    assert V.brains_that_ran([_boot_row()])["n_by_worker"] == {}
    got = V.brains_that_ran([_boot_row(), _worker_row("glm-5.3")])
    assert got["n_by_worker"] == {"claude_code/glm-5.3": 1}
    assert got["mixed"] is False, "el arranque no puede hacer que una ronda parezca mixta"


def test_a_chain_that_moved_mid_round_is_loud():
    """La mitad de la ronda es un producto y la mitad otro: ningún sello único sería honesto."""
    got = V.brains_that_ran([_worker_row("glm-5.3"), _worker_row("deepseek-v4-flash"),
                             _worker_row("deepseek-v4-flash")])
    assert got["mixed"] is True
    assert S._brain_stamp({"brains": got}) == "deepseek-v4-flash+glm-5.3", "el más usado primero"


def test_the_relay_is_read_by_its_label_not_by_its_kind():
    """Filtrar por `kind == 'perf'` encuentra CERO relevos en una ronda llena de ellos."""
    relays = V.brains_that_ran([_relay_row()])["relays"]
    assert relays == [{"role": "cluster_brain", "from": "z.ai", "to": "deepseek", "why": "exhausted"}]


def test_the_two_other_event_shapes_read_the_same():
    """Anidada bajo `extra` y leída directa del sqlite: el mismo hecho no depende de por dónde entró."""
    nested = [{"kind": "worker_start", "payload": {"extra": {"model": "glm-5.3", "label": "worker · cc"}}}]
    flat = [json.loads(_worker_row("glm-5.3")["payload"])]
    assert V.brains_that_ran(nested)["n_by_worker"] == {"cc/glm-5.3": 1}
    assert V.brains_that_ran(flat)["n_by_worker"] == {"claude_code/glm-5.3": 1}


def test_a_round_with_no_worker_is_not_an_unstamped_round():
    """`—` es una ausencia MEDIDA (caso conversacional); `?` es una fila anterior a que esto existiera.
    Confundirlas dejaría leer cada fila vieja como si nadie hubiera trabajado en ella."""
    assert S._brain_stamp({"brains": {"n_by_worker": {}}}) == ""
    assert S._brain_cell({"brain": ""}) == "—"
    assert S._brain_cell({"overall": 4}) == "?"
    assert S._brain_cell({"brain": "glm-5.3"}) == "`glm-5.3`"


def test_the_stamp_travels_from_the_mechanism_report_to_the_ledger_row(tmp_path, monkeypatch):
    """La cadena entera: eventos → informe de mecanismo → fila del registro → columna del tablero."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    mech = {"brains": V.brains_that_ran([_worker_row("glm-5.3")]), "families_observed": ["worker"]}
    S.record([{"scenario": "x__us", "tier": 2, "run": {"mechanism_report": mech, "transcript": []},
               "verdict": {"overall": 4, "scores": {"mecanismo": 4}, "veredicto": "bien"}}], sandboxed=True)
    row = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["scenarios"]["x__us"]
    assert row["brain"] == "glm-5.3"
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "| brain |" in board and "`glm-5.3`" in board
