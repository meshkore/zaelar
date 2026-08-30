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
                                          "min_sim": 0.30, "max_sim": 0.40, "jaccard_max": 0.31,
                                          "engine_metric": "contención", "engine_bar": 0.45,
                                          "over_engine_bar": False}],
                              "worst": 4, "continuations_visible": True},
    }))
    assert "4 workers para UN encargo" in joined and "Busca planes con ninos" in joined
    # …y a CUÁL de los dos defectos apunta, con la vara REAL del motor. El informe decía «por debajo de su
    # 0,60» y las dos mitades eran falsas desde el 2026-08-23: ni la métrica era Jaccard ni la vara 0,60.
    assert "por debajo de su 0.45" in joined
    assert "0,60" not in joined, "el informe sigue citando la vara vieja del motor"


def test_escalations_are_not_WORKERS_and_the_report_must_not_say_they_are():
    """El grupo cuenta PETICIONES DE ESCALADA con el mismo texto (`text_source: escalate.requested`), no
    workers nacidos. Llamarlas «workers» inventa un hecho — y lo inventaba con el desmentido pegado.

    Medido en `cheapest-monitor__us` (2026-08-30): el informe imprimió «2 workers para UN encargo … se paga
    entero cada vez» mientras el MISMO bloque traía `worker_health.spawned: 1` y
    `duplicate_errands.n_spawned: 1`. Un worker nació; nadie pagó dos veces. La acusación viajó hasta un
    encargo y la desmontó dev-main leyendo la base del plató: el instrumento gastó el tiempo de otro agente.

    La cota es CONSERVADORA a propósito: `n_spawned` es de toda la ventana, así que si un grupo dice más
    peticiones que workers nacidos en la ronda entera, esas peticiones no pueden haber sido workers.
    """
    from tests.use_cases.e2e.agent import report as reportmod
    joined = "\n".join(reportmod._mechanism_numbers({
        "worker_health": {"spawned": 1, "ok": 0, "still_running": 1},
        "duplicate_errands": {"n_spawned": 1, "worst": 2, "continuations_visible": True,
                              "groups": [{"n": 2, "goal": "Investigate current work monitors", "identical": True,
                                          "min_sim": 1.0, "max_sim": 1.0, "jaccard_max": 1.0,
                                          "engine_metric": "contención", "engine_bar": 0.45,
                                          "over_engine_bar": True}]},
    }))
    assert "2 workers para UN encargo" not in joined, "vuelve a contar peticiones y llamarlas workers"
    assert "se paga entero cada vez" not in joined, "afirma un doble cobro que su propio contador desmiente"
    assert "solo 1 worker(s) NACIDO(S)" in joined
    # Y el hueco tiene que quedar SEÑALADO, porque es el hallazgo de verdad: una escalada que abre su hoja en
    # pantalla y no llega a nacer deja una caja esperando trabajo que nadie empezó.
    assert "no llegaron a nacer" in joined


def test_and_a_REAL_double_spawn_is_still_reported_as_such():
    """El contrapeso, sin el cual lo de arriba es «desactivar el detector»: cuando de verdad nacen dos workers
    para un encargo, el informe tiene que seguir diciéndolo con todas las letras."""
    from tests.use_cases.e2e.agent import report as reportmod
    joined = "\n".join(reportmod._mechanism_numbers({
        "worker_health": {"spawned": 2, "ok": 1},
        "duplicate_errands": {"n_spawned": 2, "worst": 2, "continuations_visible": True,
                              "groups": [{"n": 2, "goal": "Busca un hotel", "identical": True,
                                          "min_sim": 1.0, "max_sim": 1.0, "jaccard_max": 1.0,
                                          "engine_metric": "contención", "engine_bar": 0.45,
                                          "over_engine_bar": True}]},
    }))
    assert "2 workers para UN encargo" in joined
    assert "se paga entero cada vez" in joined


def _rounds(tmp_path, spawns: list[str], asked: list[str] | None = None) -> str:
    """Los DOS eventos que existen de verdad: la escalada (texto completo) y el nacimiento (goal recortado)."""
    db = tmp_path / "r.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    for i, g in enumerate(asked or []):
        con.execute("INSERT INTO events VALUES (?,?,?)",
                    ("escalate.requested", json.dumps({"request": g}), 1000 + i * 1000))
    for i, g in enumerate(spawns):
        con.execute("INSERT INTO events VALUES (?,?,?)",
                    ("worker.spawned", json.dumps({"id": str(i + 1), "goal": g}), 1500 + i * 1000))
    con.commit()
    con.close()
    return str(db)


def test_the_full_request_wins_over_the_truncated_goal(tmp_path):
    """La lección que costó una acusación falsa. Los `goal` de un mismo encargo comparten un prefijo largo,
    así que comparar prefijos mide lo que tienen en común y lo llama parecido: los cuatro de
    `kid-friendly` daban 0.647-0.80 leídos así y 0.319-0.450 sobre el texto entero. Un lector apuntado al
    campo recortado no falla — FABRICA el hallazgo."""
    largo_a = ("Busca planes con ninos el domingo en el centro de Madrid. Quiero opciones concretas con "
               "horarios, precios, reservas, transporte publico, alternativas de interior por si llueve")
    largo_b = "Busca planes con ninos el domingo en el centro de Madrid. Prefiero museos y talleres"
    prefijo = "Busca planes con ninos el domingo en el centro de Madrid. "
    db = _rounds(tmp_path, spawns=[prefijo + "aaaa", prefijo + "bbbb"], asked=[largo_a, largo_b])
    r = verify.duplicate_errands(db, since=0)
    assert r["text_source"].startswith("escalate.requested"), r["text_source"]
    assert r["truncated_source"] is False


def test_with_only_the_truncated_field_it_SAYS_the_number_is_a_ceiling(tmp_path):
    """Callarlo sería lo peligroso: una similitud leída sobre un prefijo es un TECHO, y quien la lea sin
    ese aviso la usará para acusar a un dedup que hizo su trabajo."""
    r = verify.duplicate_errands(_rounds(tmp_path, spawns=["Busca un hotel en Sevilla para el lunes",
                                                           "Busca un hotel en Sevilla para el martes"]), since=0)
    assert r["truncated_source"] is True and "TRUNCADO" in r["text_source"]


def test_a_DEDUPED_escalation_is_not_counted(tmp_path):
    """La escalada que el motor SÍ paró deja su `escalate.requested` y ningún worker. Contarla acusaría al
    dedup justo de los casos en los que funcionó — el mismo error, por el otro lado."""
    g = "Cancelar la suscripcion de Netflix del operador antes de la proxima renovacion del dia quince"
    db = tmp_path / "d.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps({"request": g}), 1000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("worker.spawned", json.dumps({"id": "1", "goal": g}), 2000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps({"request": g}), 60000))
    con.commit(); con.close()
    r = verify.duplicate_errands(str(db), since=0)
    assert r["groups"] == [], r          # la segunda no nació: el dedup funcionó y no se le acusa


def test_containment_survives_a_reformulation_that_jaccard_dismisses(tmp_path):
    """El cambio de métrica, con los números medidos. El cerebro reformula con distinto nivel de detalle
    (668 vs 298 caracteres en el caso real) y Jaccard divide por la UNIÓN, así que cuanto más elabora menos
    se parece un encargo a sí mismo. Y el informe tiene que llevar el número del MOTOR al lado para saber a
    cuál de los dos defectos apunta."""
    largo = ("Busca planes con ninos el domingo en el centro de Madrid con horarios precios reservas "
             "transporte publico alternativas interiores museos talleres espectaculos parques")
    corto = "Busca planes con ninos el domingo en el centro de Madrid"
    r = verify.duplicate_errands(_rounds(tmp_path, spawns=[largo, corto], asked=[largo, corto]), since=0)
    assert r["worst"] == 2, r
    g = r["groups"][0]
    assert g["min_sim"] >= 0.9                      # contención: el corto está casi entero dentro del largo
    assert g["jaccard_max"] < 0.6                   # Jaccard lo habría descartado…
    # …y el MOTOR ya no usa Jaccard. Este assert decía `over_engine_bar is False` con el comentario «el motor
    # lo descartaría», y era una afirmación sobre el motor que dejó de ser cierta el mismo día que se
    # escribió: F4 movió `find_duplicate` a contención con la vara en 0,45, así que este par —contención
    # ≥0,9— SÍ lo para el dedup de hoy. El informe estaba señalando una paráfrasis que el motor ya resuelve.
    assert g["engine_metric"] == "contención"
    assert g["over_engine_bar"] is True


# ── un RELEVO no es un duplicado, y su parecido es 1,0 POR CONSTRUCCIÓN ────────────────────────────────
# Medido en `search-secondhand-monitor__es` (2026-08-23 23:24). El informe decía «2 workers para UN encargo
# · contención 1,0 · se paga entero cada vez», y el segundo worker era el RELEVO por proveedor sin cuota que
# V2-238 construyó a propósito — el mismo que la columna de al lado del MISMO informe (`worker_health.
# relayed`) ya sabía llamar por su nombre. Dos lecturas del mismo hecho, una acusando al producto.
#
# Y no es un falso positivo que se arregle afinando la vara: el relevo relanza `rec.goal` LITERAL, así que
# la contención es 1,0 siempre. Ninguna vara puede distinguirlo. Lo que sí lo distingue es de dónde viene, y
# eso viaja en el evento: `context.src`. Payloads copiados de la corrida real.

_REQ = ("Busca un monitor de segunda mano (usado) de al menos 27 pulgadas por menos de 150€, "
        "preferiblemente en Wallapop. Encuentra varias opciones reales que cumplan")


def _relay_round(tmp_path, src: str = "provider_failover") -> str:
    db = tmp_path / "relay.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps(
        {"id": 1, "request": _REQ, "context": {"src": "probe", "trace": "T1·a4c3", "surface": "lista"}}), 1000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("worker.spawned", json.dumps(
        {"id": "1", "kind": "web", "goal": _REQ[:120]}), 2000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("worker.done", json.dumps(
        {"id": "1", "ok": False, "status": "relevada"}), 32000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps(
        {"id": 2, "request": _REQ, "context": {"src": src, "kind": "web", "trace": "T1·a4c3",
                                               "relay_gen": 1}}), 33000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("worker.spawned", json.dumps(
        {"id": "2", "kind": "web", "goal": _REQ[:120]}), 34000))
    con.commit(); con.close()
    return str(db)


def test_a_provider_relay_is_not_reported_as_a_duplicate(tmp_path):
    r = verify.duplicate_errands(_relay_round(tmp_path), since=0)
    assert r["groups"] == [], r
    assert r["n_spawned"] == 2, "el segundo worker existió: no se esconde, se explica"


def test_but_the_cost_of_the_relay_STAYS_visible(tmp_path):
    """Esconderlo sería el error contrario: un relevo paga tokens dos veces y eso es real."""
    r = verify.duplicate_errands(_relay_round(tmp_path), since=0)
    assert len(r["continuations"]) == 1
    assert r["continuations"][0]["src"] == "provider_failover"
    assert "relevo" in r["continuations"][0]["why"].lower()


def test_the_context_handoff_gets_the_same_treatment(tmp_path):
    """V2-117 relanza el MISMO encargo al agotarse el contexto. Misma forma, mismo trato."""
    r = verify.duplicate_errands(_relay_round(tmp_path, src="context_handoff"), since=0)
    assert r["groups"] == []
    assert r["continuations"][0]["src"] == "context_handoff"


def test_a_REAL_duplicate_is_still_reported(tmp_path):
    """Sensibilidad, y es la mitad que importa: quitar el falso positivo no puede quitar el verdadero."""
    db = tmp_path / "dup.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    for i, ts in ((1, 1000), (2, 33000)):
        con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps(
            {"id": i, "request": _REQ, "context": {"src": "probe"}}), ts))
        con.execute("INSERT INTO events VALUES (?,?,?)", ("worker.spawned", json.dumps(
            {"id": str(i), "goal": _REQ[:120]}), ts + 1000))
    con.commit(); con.close()
    r = verify.duplicate_errands(str(db), since=0)
    assert r["worst"] == 2, r
    assert r["continuations"] == []


def test_reading_only_the_spawn_SAYS_it_cannot_tell(tmp_path):
    """El `goal` del spawn no dice de dónde viene, así que por esa vía un relevo es indistinguible.

    Callarlo devuelve el falso positivo con otra cara: el informe diría «duplicado» con la misma seguridad
    que cuando sí puede saberlo.
    """
    r = verify.duplicate_errands(_rounds(tmp_path, spawns=[_REQ[:120], _REQ[:120]]), since=0)
    assert r["worst"] == 2
    assert r["continuations_visible"] is False
    from tests.use_cases.e2e.agent import report as reportmod
    joined = "\n".join(reportmod._mechanism_numbers({"duplicate_errands": r}))
    assert "no se puede distinguir" in joined
