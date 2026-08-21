"""A card nobody asked for is a defect, and the harness has to SEE it.

The operator caught it on screen (2026-08-21) and the automated walk had not: an empty «Navegador» card
sitting on top of the browser card that was actually working. Nothing ordered it open — the canvas reports
its open set, the server normalises `navegador::t2` down to `navegador` for the prompt, and the audit emit
of that new id travels on the same SSE bus the canvas takes orders from. The canvas obeys its own report.

These tests pin the READER, not the engine fix: `ghost_widgets` must recognise the signature, and — the
part that matters more — it must never claim a clean canvas when there was no canvas to look at.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.use_cases.e2e.agent import verify  # noqa: E402


def _snap(instances):
    """One `canvas (instancias)` event, in the shape the observability API really hands back: the fields
    land FLAT inside a JSON-string payload, not under an `extra` key (see `verify._fields`)."""
    import json
    return {"cat": "ui", "label": "canvas (instancias)",
            "payload": json.dumps({"label": "canvas (instancias)", "cat": "ui",
                                   "extra": {"instances": list(instances), "n": len(instances)}})}


def test_the_base_card_next_to_its_own_instance_is_a_ghost():
    r = verify.ghost_widgets([_snap(["navegador::t1"]), _snap(["navegador::t1", "navegador"])])
    assert r["observed"] is True
    assert [g["id"] for g in r["ghosts"]] == ["navegador"]
    assert r["ghosts"][0]["alongside"] == ["navegador::t1"]


def test_an_instance_alone_is_not_a_ghost():
    r = verify.ghost_widgets([_snap(["results", "navegador::t2"])])
    assert r["ghosts"] == [] and r["observed"] is True


def test_a_base_card_with_no_instance_of_it_is_not_a_ghost():
    """`results` open on its own is the normal case today and must not be reported: the defect is a base
    card DUPLICATING an instance of itself, not a base card existing."""
    r = verify.ghost_widgets([_snap(["results", "navegador::t2"]), _snap(["results", "agenda"])])
    assert r["ghosts"] == []


def test_no_canvas_attached_is_NOT_reported_as_clean():
    """The whole point. The echo needs a real frontend reporting its canvas, so an unattended round has no
    snapshot at all — which is why the walk went days without seeing this. `observed=False` keeps that
    distinction alive; a reader that returned «0 ghosts» here would be asserting a check it never ran."""
    r = verify.ghost_widgets([{"cat": "widget", "label": "show", "payload": '{"extra":{"id":"navegador::t1"}}'}])
    assert r["observed"] is False
    assert r["ghosts"] == [] and r["n_snapshots"] == 0


def test_the_reader_survives_the_shapes_the_api_really_returns():
    """Junk in the stream cannot take the reader down: a round that raises here loses its whole verdict."""
    r = verify.ghost_widgets([None, 42, {}, {"label": "canvas (instancias)"},
                              {"payload": "not json"}, _snap(["navegador::t1", "navegador"])])
    assert [g["id"] for g in r["ghosts"]] == ["navegador"]


def test_the_last_canvas_is_carried_so_the_report_can_show_it():
    r = verify.ghost_widgets([_snap(["results"]), _snap(["results", "navegador::t2", "navegador"])])
    assert r["last"] == ["results", "navegador::t2", "navegador"]
    assert r["max_cards"] == 3


# ── …y solo se EJECUTA lo que se ha pedido ────────────────────────────────────────────────────────────
# La otra mitad de la regla del operador (2026-08-21, con su captura delante: cinco tarjetas para una
# búsqueda). No eran cinco encargos: era UNO corriendo cuatro veces, cada worker abriendo su hoja.
# `worker_health` decía «4 lanzados», que se lee como concurrencia sana.
import json      # noqa: E402
import sqlite3   # noqa: E402


def _spawns(tmp_path, goals: list[str]) -> str:
    """Una base con los eventos `worker.spawned` REALES que lee el arnés, no un mock del lector."""
    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    for i, g in enumerate(goals):
        con.execute("INSERT INTO events VALUES (?,?,?)",
                    ("worker.spawned", json.dumps({"id": str(i + 1), "goal": g}), 1000 + i))
    con.commit()
    con.close()
    return str(db)


def test_four_reformulations_of_one_errand_are_ONE_group(tmp_path):
    """El caso medido. Los cuatro `goal` comparten un prefijo largo y difieren en la cola —el payload los
    recorta a 120 caracteres— así que contar repeticiones EXACTAS habría devuelto cero y la ronda habría
    salido limpia."""
    db = _spawns(tmp_path, [
        "Busca planes para hacer con ninos este domingo 23 de agosto en el centro de Madrid (Espana). El operador vive",
        "Busca planes para hacer con ninos este domingo 23 de agosto, cerca del centro de Madrid (zona centro). Deben ser",
        "Busca planes para hacer con ninos este domingo 23 de agosto en el centro de Madrid, cerca del centro de la ciudad",
        "Busca planes para hacer con ninos este domingo 23 de agosto en el centro de Madrid (Espana). Quiero opciones con",
    ])
    r = verify.duplicate_errands(db, since=0)
    assert r["read"] is True and r["n_spawned"] == 4
    assert r["worst"] == 4, r
    assert r["groups"][0]["min_sim"] >= 0.6


def test_two_DIFFERENT_errands_are_not_grouped(tmp_path):
    """Sensibilidad, y es el lado caro: agrupar de más convierte una tanda sana en un informe de
    duplicados y nadie vuelve a mirar la columna."""
    db = _spawns(tmp_path, [
        "Busca un hotel de cuatro estrellas en Sevilla para cuatro noches en septiembre",
        "Cancela la suscripcion de Netflix del operador antes de la proxima renovacion",
    ])
    r = verify.duplicate_errands(db, since=0)
    assert r["groups"] == [] and r["worst"] == 0


def test_an_identical_repeat_is_told_apart_from_a_paraphrase(tmp_path):
    """Acusan cosas distintas: una repetición idéntica es un dedup que no corrió, una reformulación es un
    dedup que corrió y no supo verlo. Mezclarlas manda a mirar el sitio equivocado."""
    db = _spawns(tmp_path, ["Buscar entradas del concierto de Rosalia en Madrid en agosto",
                            "Buscar entradas del concierto de Rosalia en Madrid en agosto"])
    r = verify.duplicate_errands(db, since=0)
    assert r["identical_repeats"] == 1
    assert r["groups"][0]["identical"] is True and r["groups"][0]["max_sim"] == 1.0


def test_one_worker_is_never_a_duplicate(tmp_path):
    r = verify.duplicate_errands(_spawns(tmp_path, ["Busca un hotel en Sevilla"]), since=0)
    assert r["read"] is True and r["n_spawned"] == 1 and r["groups"] == []


def test_an_unreadable_store_is_NOT_a_clean_round(tmp_path):
    """`read: False` y «cero duplicados» no son lo mismo, y esta columna existe justo porque un cero
    tranquiliza. Sin base que leer, el informe no puede afirmar que la tanda fue limpia."""
    r = verify.duplicate_errands(str(tmp_path / "no-existe.db"), since=0)
    assert r["read"] is False and r["groups"] == []


def test_the_report_SAYS_it_when_an_errand_ran_twice():
    """La mitad que ninguna medición ve: que el hallazgo llegue al informe. Medirlo y no imprimirlo deja
    la ronda igual de ciega que antes."""
    from tests.use_cases.e2e.agent import report as reportmod
    joined = "\n".join(reportmod._mechanism_numbers({
        "worker_health": {"spawned": 4, "ok": 2},
        "duplicate_errands": {"groups": [{"n": 4, "goal": "Busca planes con ninos", "identical": False,
                                          "min_sim": 0.647, "max_sim": 0.8}], "worst": 4},
    }))
    assert "4 workers para UN encargo" in joined and "Busca planes con ninos" in joined
