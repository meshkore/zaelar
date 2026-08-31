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


# ── …and only what was requested is EXECUTED ──────────────────────────────────────────────────────────
# The other half of the operator's rule (2026-08-21, with its screenshot in front of us: five cards for one
# search). They were not five errands: it was ONE running four times, each worker opening its own sheet.
# `worker_health` said “4 launched,” which reads as healthy concurrency.
import json      # noqa: E402
import sqlite3   # noqa: E402


def _spawns(tmp_path, goals: list[str]) -> str:
    """A database with the REAL `worker.spawned` events read by the harness, not a mock of the reader."""
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
    """The measured case. The four `goal` values share a long prefix and differ in the tail—the payload
    truncates them to 120 characters—so counting EXACT repeats would have returned zero and the round would
    have come out clean."""
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
    """Sensitivity, and this is the costly side: over-grouping turns a healthy batch into a duplicate
    report and nobody looks at the column again."""
    db = _spawns(tmp_path, [
        "Busca un hotel de cuatro estrellas en Sevilla para cuatro noches en septiembre",
        "Cancela la suscripcion de Netflix del operador antes de la proxima renovacion",
    ])
    r = verify.duplicate_errands(db, since=0)
    assert r["groups"] == [] and r["worst"] == 0


def test_an_identical_repeat_is_told_apart_from_a_paraphrase(tmp_path):
    """They accuse different things: an identical repeat is a dedup that did not run, while a reformulation
    is a dedup that ran and failed to recognize it. Mixing them sends us to look in the wrong place."""
    db = _spawns(tmp_path, ["Buscar entradas del concierto de Rosalia en Madrid en agosto",
                            "Buscar entradas del concierto de Rosalia en Madrid en agosto"])
    r = verify.duplicate_errands(db, since=0)
    assert r["identical_repeats"] == 1
    assert r["groups"][0]["identical"] is True and r["groups"][0]["max_sim"] == 1.0


def test_one_worker_is_never_a_duplicate(tmp_path):
    r = verify.duplicate_errands(_spawns(tmp_path, ["Busca un hotel en Sevilla"]), since=0)
    assert r["read"] is True and r["n_spawned"] == 1 and r["groups"] == []


def test_an_unreadable_store_is_NOT_a_clean_round(tmp_path):
    """`read: False` and “zero duplicates” are not the same, and this column exists precisely because a zero
    is reassuring. Without a database to read, the report cannot claim that the batch was clean."""
    r = verify.duplicate_errands(str(tmp_path / "no-existe.db"), since=0)
    assert r["read"] is False and r["groups"] == []


def test_the_report_SAYS_it_when_an_errand_ran_twice():
    """The half that no measurement sees: getting the finding into the report. Measuring it without printing
    it leaves the round just as blind as before."""
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
    # …and WHICH of the two defects it points to, using the engine's REAL threshold. The report said “below its
    # 0.60” and both halves had been false since 2026-08-23: neither the metric nor the threshold was 0.60.
    assert "por debajo de su 0.45" in joined
    assert "0,60" not in joined, "el informe sigue citando la vara vieja del motor"


def test_escalations_are_not_WORKERS_and_the_report_must_not_say_they_are():
    """The group counts ESCALATION REQUESTS with the same text (`text_source: escalate.requested`), not
    spawned workers. Calling them “workers” invents a fact—and it did so with the refutation attached.

    Measured in `cheapest-monitor__us` (2026-08-30): the report printed “2 workers for ONE errand … paid in
    full each time” while the SAME block contained `worker_health.spawned: 1` and
    `duplicate_errands.n_spawned: 1`. One worker was born; nobody paid twice. The accusation reached an
    errand and dev-main dismantled it by reading the set's database: the instrument spent another agent's time.

    The bound is deliberately CONSERVATIVE: `n_spawned` covers the entire window, so if a group reports more
    requests than workers born in the whole round, those requests cannot have been workers.
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
    # And the gap must remain FLAGGED, because it is the real finding: an escalation that opens its sheet on
    # screen but never gets born leaves a box waiting for work that nobody started.
    assert "no llegaron a nacer" in joined


def test_and_a_REAL_double_spawn_is_still_reported_as_such():
    """The counterweight, without which the above would be “disabling the detector”: when two workers really
    are spawned for an errand, the report must continue to say so explicitly."""
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
    """The TWO events that really exist: the escalation (full text) and the birth (truncated goal)."""
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
    """The lesson that cost us a false accusation. The `goal` values for one errand share a long prefix,
    so comparing prefixes measures what they have in common and calls it similarity: the four
    `kid-friendly` values yielded 0.647–0.80 when read that way and 0.319–0.450 over the full text. A reader
    pointed at the truncated field does not fail—it MANUFACTURES the finding."""
    largo_a = ("Busca planes con ninos el domingo en el centro de Madrid. Quiero opciones concretas con "
               "horarios, precios, reservas, transporte publico, alternativas de interior por si llueve")
    largo_b = "Busca planes con ninos el domingo en el centro de Madrid. Prefiero museos y talleres"
    prefijo = "Busca planes con ninos el domingo en el centro de Madrid. "
    db = _rounds(tmp_path, spawns=[prefijo + "aaaa", prefijo + "bbbb"], asked=[largo_a, largo_b])
    r = verify.duplicate_errands(db, since=0)
    assert r["text_source"].startswith("escalate.requested"), r["text_source"]
    assert r["truncated_source"] is False


def test_with_only_the_truncated_field_it_SAYS_the_number_is_a_ceiling(tmp_path):
    """Keeping quiet about it would be dangerous: similarity read from a prefix is a CEILING, and anyone who
    reads it without that warning will use it to accuse a dedup that did its job."""
    r = verify.duplicate_errands(_rounds(tmp_path, spawns=["Busca un hotel en Sevilla para el lunes",
                                                           "Busca un hotel en Sevilla para el martes"]), since=0)
    assert r["truncated_source"] is True and "TRUNCADO" in r["text_source"]


def test_a_DEDUPED_escalation_is_not_counted(tmp_path):
    """The escalation that the engine DID stop leaves its `escalate.requested` and no worker. Counting it
    would accuse the dedup precisely in the cases where it worked—the same error, from the other side."""
    g = "Cancelar la suscripcion de Netflix del operador antes de la proxima renovacion del dia quince"
    db = tmp_path / "d.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, payload TEXT, ts_ms INTEGER)")
    con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps({"request": g}), 1000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("worker.spawned", json.dumps({"id": "1", "goal": g}), 2000))
    con.execute("INSERT INTO events VALUES (?,?,?)", ("escalate.requested", json.dumps({"request": g}), 60000))
    con.commit(); con.close()
    r = verify.duplicate_errands(str(db), since=0)
    assert r["groups"] == [], r          # the second was not born: the dedup worked and is not accused


def test_containment_survives_a_reformulation_that_jaccard_dismisses(tmp_path):
    """The metric change, with the measured numbers. The brain reformulates with a different level of detail
    (668 vs 298 characters in the real case), and Jaccard divides by the UNION, so the more it elaborates, the
    less an errand resembles itself. And the report must put the ENGINE number beside it to show which of the
    two defects it points to."""
    largo = ("Busca planes con ninos el domingo en el centro de Madrid con horarios precios reservas "
             "transporte publico alternativas interiores museos talleres espectaculos parques")
    corto = "Busca planes con ninos el domingo en el centro de Madrid"
    r = verify.duplicate_errands(_rounds(tmp_path, spawns=[largo, corto], asked=[largo, corto]), since=0)
    assert r["worst"] == 2, r
    g = r["groups"][0]
    assert g["min_sim"] >= 0.9                      # containment: the short one is almost entirely inside the long one
    assert g["jaccard_max"] < 0.6                   # Jaccard would have discarded it…
    # …and the ENGINE no longer uses Jaccard. This assert said `over_engine_bar is False` with the comment “the engine
    # would discard it,” and that engine claim stopped being true the same day it was written: F4 moved
    # `find_duplicate` to containment with a threshold of 0.45, so this pair—containment ≥0.9—IS stopped by
    # today's dedup. The report was flagging a paraphrase that the engine already handles.
    assert g["engine_metric"] == "contención"
    assert g["over_engine_bar"] is True


# ── a RELAY is not a duplicate, and its similarity is 1.0 BY CONSTRUCTION ─────────────────────────────
# Measured in `search-secondhand-monitor__es` (2026-08-23 23:24). The report said “2 workers for ONE errand
# · containment 1.0 · paid in full each time,” and the second worker was the RELAY for a provider without quota that
# V2-238 deliberately built—the same one that the adjacent column of the SAME report (`worker_health.
# relayed`) already knew to call by name. Two readings of the same fact, one accusing the product.
#
# And this is not a false positive that can be fixed by tuning the threshold: the relay relaunches `rec.goal`
# LITERALLY, so containment is always 1.0. No threshold can distinguish it. What does distinguish it is where it
# comes from, and that travels in the event: `context.src`. Payloads copied from the real run.

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
    """Hiding it would be the opposite error: a relay pays tokens twice, and that is real."""
    r = verify.duplicate_errands(_relay_round(tmp_path), since=0)
    assert len(r["continuations"]) == 1
    assert r["continuations"][0]["src"] == "provider_failover"
    assert "relevo" in r["continuations"][0]["why"].lower()


def test_the_context_handoff_gets_the_same_treatment(tmp_path):
    """V2-117 relaunches the SAME errand when the context is exhausted. Same shape, same treatment."""
    r = verify.duplicate_errands(_relay_round(tmp_path, src="context_handoff"), since=0)
    assert r["groups"] == []
    assert r["continuations"][0]["src"] == "context_handoff"


def test_a_REAL_duplicate_is_still_reported(tmp_path):
    """Sensitivity, and this is the half that matters: removing the false positive cannot remove the true one."""
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
    """The spawn's `goal` does not say where it came from, so by that route a relay is indistinguishable.

    Keeping quiet about it returns the false positive in another form: the report would say “duplicate” with the
    same certainty as when it can actually know.
    """
    r = verify.duplicate_errands(_rounds(tmp_path, spawns=[_REQ[:120], _REQ[:120]]), since=0)
    assert r["worst"] == 2
    assert r["continuations_visible"] is False
    from tests.use_cases.e2e.agent import report as reportmod
    joined = "\n".join(reportmod._mechanism_numbers({"duplicate_errands": r}))
    assert "no se puede distinguir" in joined
