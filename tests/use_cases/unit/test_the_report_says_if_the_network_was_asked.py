"""V2-489 — the report says whether the worker ASKED THE NETWORK before searching on its own.

The data was already being collected (`verify.worker_bridges()['by_bridge']`), and only its ERRORS were
published. That is why the fact that the MeshKore network had produced **399 reports without a single query**
had to be discovered manually when auditing it (V2-486/487): no round reported it, whether it used the network
or not.

Now that asking the network first is a product behavior—and not an extra—the round has to state it. It is
stated as a FACT and with its limitation made clear: detection is based on the bridge name appearing in the
worker session log, so **presence is strong and absence is weaker**. A log that could not be read cannot
distinguish “it did not ask” from “we did not see it,” and a blind instrument that asserts the former creates a
defect—the kind that has already cost six false accusations.
"""
from tests.use_cases.e2e.agent.judge import mechanism_facts


def _mech(**extra) -> dict:
    base = {"families_observed": [], "expected_signals": [], "missing_signals": [], "n_events": 3}
    base.update(extra)
    return base


def test_lo_DICE_cuando_el_worker_pregunto_a_la_red():
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 1, "by_bridge": {"mesh_cli": 1, "nav_cli": 2}, "errors": {}}))
    assert "mesh_cli" in txt and "PREGUNTÓ A LA RED" in txt


def test_una_ronda_rapida_por_la_red_no_es_una_ronda_floja():
    """Without this phrase, a round that resolves in seconds because the network helped it reads as little work."""
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 1, "by_bridge": {"mesh_cli": 1}, "errors": {}}))
    assert "NO es haber hecho menos trabajo" in txt


def test_lo_DICE_cuando_NO_la_consulto_y_no_lo_convierte_en_falta():
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 1, "by_bridge": {"nav_cli": 4}, "errors": {}}))
    assert "NO consultó la red" in txt
    assert "No lo puntúes por sí solo" in txt, (
        "un hecho de mecanismo convertido en reproche de conducta es como se fabrica un defecto falso")


def test_un_log_ILEGIBLE_no_afirma_nada():
    """`read: False` = it could not be inspected. Saying “it did not consult the network” there would invent an absence."""
    txt = mechanism_facts(_mech(worker_bridges={"read": False, "sessions": 0, "by_bridge": {}, "errors": {}}))
    assert "NO consultó la red" not in txt and "PREGUNTÓ A LA RED" not in txt


def test_sin_informe_de_puentes_tampoco_afirma_nada():
    txt = mechanism_facts(_mech())
    assert "consultó la red" not in txt and "PREGUNTÓ A LA RED" not in txt


def test_los_ERRORES_de_puente_se_siguen_diciendo_PERO_SIN_ATRIBUIR():
    """V2-399 still stands: a worker whose bridges fail is not a worker without judgment, so the fact has to
    reach the judge. What must NOT reach it is an attribution.

    `errors[bridge]` is incremented once for each NAMED bridge in a session that contained `Exit code 2`—the
    detector itself says: “a match in the session, not an attribution.” Measured in
    `search-buy-motorcycle__us` (2026-08-30): `{nav_cli: 1, worker_bridge: 1, mesh_cli: 1}` was ONE failure, the
    judge read three broken bridges, signed [high] against the product, and invented details (“missing
    arguments, file errors”) that it never received—only counters had reached it.
    """
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 1, "by_bridge": {"nav_cli": 1, "mesh_cli": 1},
        "errors": {"nav_cli": 1, "mesh_cli": 1}, "sessions_with_exit2": 1}))

    assert "Exit code 2" in txt, "el hecho tiene que seguir llegando al juez"
    assert "nav_cli" in txt and "mesh_cli" in txt, "y con los puentes que había en esa sesión"
    # The part that prevents the false defect: the honest number is SESSIONS, and the limitation is written down.
    assert "1 sesión(es)" in txt, "vuelve a contar puentes en vez de sesiones rotas"
    assert "NO una atribución" in txt
    assert "NO describas la causa" in txt, "sin esto el juez se inventa el detalle que no recibió"


def test_sin_sesiones_en_la_ventana_lo_DICE_en_vez_de_callarse():
    """A section that appears sometimes and not others without saying why is worse than one that never appears:
    the missing line would be read as “it did not ask.” Measured: in the 21:06 round the record was there but
    the line did not appear, and there was no way to know which of the two things had happened."""
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 0, "by_bridge": {}, "errors": {}}))
    assert "NINGUNA sesión de worker cae dentro de esta ronda" in txt
    assert "ni que preguntara a la red ni que no" in txt


# ── the “offered” counter has to say WHAT it refers to (2026-08-30) ──────────────────────────────────────
def test_las_DOS_cabeceras_del_bloque_se_leen(tmp_path):
    """The engine writes that block from TWO places with two phrasings—`live_blocks.py` puts “WHAT IT HAS
    ALREADY DELIVERED (name and price, from the sheet):” and `task_block.py` puts “— ALREADY DELIVERED (from
    its sheet):”—and this reader only knew the first.

    Measured in round 20260830-1409, the cleanest of the day: `n_offered: 0` while the prompt contained
    “LG 27US500-W Ultrafine — $243.99”; “Acer Nitro VG270K — $159.99”; “CRUA Dual Mode 4K 160Hz — $229.99”.
    A zero caused by failing to recognize a phrasing is indistinguishable from a zero caused by there being
    nothing—and this one pointed at the product.
    """
    import json as _j
    import sqlite3

    from tests.use_cases.e2e.agent import verify

    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms REAL, topic TEXT, kind TEXT, payload TEXT)")
    for sp in ('… — YA ENTREGADO (de su hoja): «LG 27US500-W Ultrafine — $243.99»; '
               '«Acer Nitro VG270K — $159.99» (llevas 68s). Si el operador pregunta…',
               '… LO QUE YA HA ENTREGADO (nombre y precio, de la hoja): «Dell S2725QS — $199». OJO: …'):
        con.execute("INSERT INTO events (ts_ms, topic, kind, payload) VALUES (?,?,?,?)",
                    (1000.0, "observer", "flash", _j.dumps({"system_prompt": sp})))
    con.commit(); con.close()

    o = verify.offered_to_brain(str(db))
    assert "LG 27US500-W Ultrafine" in o["titles"], "la redacción de task_block sigue siendo invisible"
    assert "Dell S2725QS" in o["titles"], "y la de live_blocks tiene que seguir leyéndose"
    assert o["n_offered"] >= 3


def test_una_PISTA_no_se_cuenta_como_candidato(tmp_path):
    """V2-510 labels article pages “not a candidate yet.” Counting them as offers produces the number that makes
    it seem the agent chose poorly despite having plenty to choose from: measured, 33 “offered,” of which 30
    were review headlines."""
    import json as _j
    import sqlite3

    from tests.use_cases.e2e.agent import verify

    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms REAL, topic TEXT, kind TEXT, payload TEXT)")
    sp = ('… — YA ENTREGADO (de su hoja): «Acer Nitro VG270K — $159.99»; '
          '«The 6 Best 27-Inch Monitors of 2026 - RTINGS.com — PÁGINA WEB por mirar, aún no es un candidato» '
          '(llevas 40s). Si el operador pregunta…')
    con.execute("INSERT INTO events (ts_ms, topic, kind, payload) VALUES (?,?,?,?)",
                (1000.0, "observer", "flash", _j.dumps({"system_prompt": sp})))
    con.commit(); con.close()

    o = verify.offered_to_brain(str(db))
    assert o["candidates"] == ["Acer Nitro VG270K"]
    assert o["leads"] and "RTINGS" in o["leads"][0]
    assert o["n_candidates"] == 1, "una página por mirar no es una ficha ofrecida"
    # And the parts ADD UP: what arrives by note has no qualifier, so it is counted as unclassified
    # instead of slipping into one of the two sides.
    assert o["n_offered"] == o["n_candidates"] + len(o["leads"]) + o["n_unclassified"]


def test_la_PROSA_del_prompt_no_produce_candidatos(tmp_path):
    """Loosening the pattern to the word “DELIVERED” to cover the second phrasing made it match
    INSTRUCTIONS in the prompt that contain it, producing “candidates” such as “taking steps,” “the usual one,”
    or “you have two things: first the electricity bill and second your prescription”—five fixed strings,
    identical in every round, which also poisoned `delivered_by_name`, because it is fed from here.

    A matcher loosened to cover a new case swallows the old noise.
    """
    import json as _j
    import sqlite3

    from tests.use_cases.e2e.agent import verify

    db = tmp_path / "s.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms REAL, topic TEXT, kind TEXT, payload TEXT)")
    sp = ('Cuando el operador te ha ENTREGADO algo, no lo repitas: «el de siempre», «va dando pasos». '
          'Ejemplo: si te dice «tienes dos cosas: primero el recibo de la luz», eso NO es un candidato. '
          '… — YA ENTREGADO (de su hoja): «Acer Nitro VG270K — $159.99» (llevas 40s).')
    con.execute("INSERT INTO events (ts_ms, topic, kind, payload) VALUES (?,?,?,?)",
                (1000.0, "observer", "flash", _j.dumps({"system_prompt": sp})))
    con.commit(); con.close()

    o = verify.offered_to_brain(str(db))
    assert o["candidates"] == ["Acer Nitro VG270K"], f"la prosa se coló: {o['candidates']}"
    for basura in ("el de siempre", "va dando pasos", "el recibo de la luz"):
        assert not any(basura in c for c in o["candidates"] + o["leads"]), f"«{basura}» sigue contando"
