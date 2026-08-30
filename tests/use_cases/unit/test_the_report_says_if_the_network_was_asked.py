"""V2-489 — el informe dice si el worker PREGUNTÓ A LA RED antes de buscar por su cuenta.

El dato ya se recogía (`verify.worker_bridges()['by_bridge']`) y solo se publicaban sus ERRORES. Por eso el
hecho de que la red MeshKore llevara **399 informes sin una sola consulta** hubo que sacarlo a mano al
auditarla (V2-486/487): ninguna ronda lo decía, ni cuando la usaba ni cuando no.

Ahora que preguntar primero a la red es una conducta del producto —y no un extra—, la ronda tiene que
enunciarla. Se enuncia como HECHO y con su límite dicho: la detección es por aparición del nombre del puente
en el log de la sesión del worker, así que **la presencia es fuerte y la ausencia lo es menos**. Un log que no
se pudo leer no distingue «no preguntó» de «no lo vimos», y un instrumento ciego que afirma lo primero
fabrica un defecto — la clase que ya costó seis acusaciones falsas.
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
    """Sin esta frase, una ronda que resuelve en segundos porque la red le sirvió se lee como poco trabajo."""
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
    """`read: False` = no se pudo mirar. Decir ahí «no consultó la red» sería inventar una ausencia."""
    txt = mechanism_facts(_mech(worker_bridges={"read": False, "sessions": 0, "by_bridge": {}, "errors": {}}))
    assert "NO consultó la red" not in txt and "PREGUNTÓ A LA RED" not in txt


def test_sin_informe_de_puentes_tampoco_afirma_nada():
    txt = mechanism_facts(_mech())
    assert "consultó la red" not in txt and "PREGUNTÓ A LA RED" not in txt


def test_los_ERRORES_de_puente_se_siguen_diciendo_PERO_SIN_ATRIBUIR():
    """V2-399 sigue en pie: un worker cuyos puentes fallan no es un worker sin criterio, así que el hecho tiene
    que llegar al juez. Lo que NO puede llegar es como una atribución.

    `errors[puente]` suma una vez por cada puente NOMBRADO en una sesión que contenía `Exit code 2` — el propio
    detector lo dice: «una coincidencia en la sesión, no una atribución». Medido en
    `search-buy-motorcycle__us` (2026-08-30): `{nav_cli: 1, worker_bridge: 1, mesh_cli: 1}` era UN fallo, el
    juez leyó tres puentes rotos, firmó [alta] contra el producto e inventó los detalles («argumentos
    faltantes, errores de fichero») que nunca recibió — solo le habían llegado unos contadores.
    """
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 1, "by_bridge": {"nav_cli": 1, "mesh_cli": 1},
        "errors": {"nav_cli": 1, "mesh_cli": 1}, "sessions_with_exit2": 1}))

    assert "Exit code 2" in txt, "el hecho tiene que seguir llegando al juez"
    assert "nav_cli" in txt and "mesh_cli" in txt, "y con los puentes que había en esa sesión"
    # La parte que impide el falso defecto: el número honesto es de SESIONES, y el límite va escrito.
    assert "1 sesión(es)" in txt, "vuelve a contar puentes en vez de sesiones rotas"
    assert "NO una atribución" in txt
    assert "NO describas la causa" in txt, "sin esto el juez se inventa el detalle que no recibió"


def test_sin_sesiones_en_la_ventana_lo_DICE_en_vez_de_callarse():
    """Una sección que a veces sale y a veces no, sin decir por qué, es peor que una que no sale nunca: la
    ausencia de la línea se leería como «no preguntó». Medido: en la ronda de las 21:06 el registro estaba
    ahí y la línea no salió, y no había forma de saber cuál de las dos cosas había pasado."""
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 0, "by_bridge": {}, "errors": {}}))
    assert "NINGUNA sesión de worker cae dentro de esta ronda" in txt
    assert "ni que preguntara a la red ni que no" in txt


# ── el contador de «ofrecido» tiene que decir de QUÉ es (2026-08-30) ──────────────────────────────────────
def test_las_DOS_cabeceras_del_bloque_se_leen(tmp_path):
    """El motor escribe ese bloque desde DOS sitios con dos redacciones —`live_blocks.py` pone «LO QUE YA HA
    ENTREGADO (nombre y precio, de la hoja):» y `task_block.py` pone «— YA ENTREGADO (de su hoja):»— y este
    lector solo conocía la primera.

    Medido en la ronda 20260830-1409, la más limpia del día: `n_offered: 0` mientras el prompt traía
    «LG 27US500-W Ultrafine — $243.99»; «Acer Nitro VG270K — $159.99»; «CRUA Dual Mode 4K 160Hz — $229.99».
    Un cero por no reconocer una redacción es indistinguible de un cero por no haber nada — y ese apuntaba
    al producto.
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
    """V2-510 etiqueta las páginas de artículo «aún no es un candidato». Contarlas como ofertas produce el
    número que hace pensar que el agente eligió mal teniendo de sobra: medido, 33 «ofrecidos» de los que 30
    eran titulares de reseñas."""
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
    # Y las partes SUMAN: lo que llega por nota no lleva calificador, así que se cuenta como sin clasificar
    # en vez de colarse en uno de los dos lados.
    assert o["n_offered"] == o["n_candidates"] + len(o["leads"]) + o["n_unclassified"]


def test_la_PROSA_del_prompt_no_produce_candidatos(tmp_path):
    """Aflojar el patrón a la palabra «ENTREGADO» para cubrir la segunda redacción hizo que casara con
    INSTRUCCIONES del prompt que la contienen, y de ahí salían «candidatos» como «va dando pasos», «el de
    siempre» o «tienes dos cosas: primero el recibo de la luz y segundo tu receta» — cinco cadenas fijas,
    idénticas en todas las rondas, que además envenenaban `delivered_by_name`, porque se alimenta de aquí.

    Un matcher que se afloja para cubrir un caso nuevo se traga el ruido del viejo.
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
