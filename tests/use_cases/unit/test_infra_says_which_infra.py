"""`INFRA` sin motivo es un agujero de operación, no de estilo.

Las cuatro puertas que llevan a INFRA piden acciones **opuestas**: el arnés se cayó (bug del instrumento),
los turnos volvieron vacíos (recargar un proveedor), el recall semántico estaba degradado (levantar el
prewarm) o el juez no dio nota (mirar su cadena). Desde el tablero se ven las cuatro exactamente igual.

Medido el 2026-08-28 con el plató 24/7 ya corriendo: dos filas pasaron de FAIL a INFRA en una hora, y
reconstruir cuál de las cuatro ramas las había movido fue **imposible** — el dict de la ronda ya no existe
cuando alguien lee el tablero. En un bucle que nadie mira durante ocho horas, ésa es la diferencia entre
«está midiendo» y «lleva toda la noche produciendo basura a toda velocidad», y la segunda es peor que estar
parado porque parado se nota.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import status as S


def _ronda(**kw):
    base = {"scenario": "x__es", "tier": 2,
            "run": {"transcript": [{}] * 12, "mechanism_report": {}},
            "verdict": {"overall": 3, "scores": {"mecanismo": 3}, "veredicto": "bien"}}
    base.update(kw)
    return base


def test_turnos_vacios_lo_dicen_con_su_cuenta():
    r = _ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})
    assert S._state(3, r) == "INFRA"
    assert "VACÍOS" in r["_infra_reason"] and "5 de 6" in r["_infra_reason"]


def test_el_recall_degradado_nombra_su_backend():
    r = _ronda(run={"transcript": [{}] * 12,
                    "mechanism_report": {"embeddings": {"degraded": True, "backend": "hash"}}})
    assert S._state(3, r) == "INFRA"
    assert "recall" in r["_infra_reason"] and "hash" in r["_infra_reason"]


def test_una_excepcion_de_verdad_y_el_juez_mudo_son_distintos():
    """Reescrito 2026-08-28, NO volteado: la propiedad —dos puertas, dos motivos distintos— es la misma. Lo
    que cambió es que `crashed` ya no se traduce a una frase inventada sino que se imprime la que trae dentro,
    así que el fixture pasa la frase real de una excepción en vez de un `True` pelado."""
    a = _ronda(run={"crashed": "ZeroDivisionError en el juez · autopsia: …",
                    "transcript": [], "mechanism_report": {}})
    S._state(3, a)
    b = _ronda()
    S._state(None, b)
    assert a["_infra_reason"] != b["_infra_reason"]
    assert "ZeroDivisionError" in a["_infra_reason"] and "juez no devolvió nota" in b["_infra_reason"]


def test_una_ronda_SANA_no_lleva_motivo():
    """La mitad de sensibilidad: un motivo que sale siempre deja de ser un motivo."""
    r = _ronda()
    assert S._state(3, r) == "FAIL"
    assert "_infra_reason" not in r


def test_el_motivo_llega_a_la_fila_y_al_tablero(tmp_path, monkeypatch):
    """La cadena entera: si se queda en el dict de la ronda no lo lee nadie."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})],
             sandboxed=True)
    fila = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["scenarios"]["x__es"]
    assert fila["state"] == "INFRA" and "VACÍOS" in (fila["infra_reason"] or "")
    tablero = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "INFRA —" in tablero and "VACÍOS" in tablero


def test_en_una_fila_INFRA_el_motivo_manda_sobre_el_veredicto(tmp_path, monkeypatch):
    """El veredicto habla de un producto que en esa ronda NO llegó a medirse. Leerlo como si sí invita justo
    al diagnóstico equivocado, que es el error que este nodo existe para no repetir."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    r = _ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})
    r["verdict"]["veredicto"] = "el producto no entregó nada"
    S.record([r], sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert fila.index("INFRA —") < fila.index("el producto no entregó nada")
    assert "no medible" in fila


def test_el_motivo_que_YA_venia_escrito_no_se_sustituye_por_una_suposicion():
    """`crashed` no es «se cayó»: es un campo con TRES inquilinos —el conductor fuera de papel (V2-313), una
    fuente de verdad ilegible (V2-396), y una excepción real con su autopsia— y **cada uno trae ya escrita su
    frase**. La primera versión de este nodo puso un motivo genérico y era falso para los tres.

    Medido una hora después de escribirlo, sobre `best-plumber-same-day__us`: el tablero decía «el arnés se
    cayó», el log no tenía ni un traceback y el veredicto era un 2/5 de producto perfectamente normal. La
    frase real, que estaba en el campo, decía «el conductor se salió de su papel en 1 línea(s) del transcript
    (turno 13): la ronda no mide al producto» — otra cosa, y con otra acción detrás.

    Adivinar un motivo teniendo el bueno delante es el mismo error que este nodo existe para arreglar.
    """
    frase = "el conductor se salió de su papel en 1 línea(s) del transcript (turno(s) 13)"
    r = _ronda(run={"crashed": frase, "transcript": [{}] * 12, "mechanism_report": {}})
    assert S._state(2, r) == "INFRA"
    assert r["_infra_reason"] == frase, "se sustituyó el motivo real por uno inventado"


def test_y_el_juez_marcando_INFRA_es_OTRA_cosa():
    """La mitad de sensibilidad: las dos puertas iban juntas en una condición y decían lo mismo."""
    r = _ronda(verdict={"overall": 1, "scores": {}, "veredicto": "INFRA: no hubo respuesta"})
    assert S._state(1, r) == "INFRA"
    assert "juez" in r["_infra_reason"] and "conductor" not in r["_infra_reason"]


# ── Una fila verde no puede esconder que el juez dijo que no ────────────────────────────────────────────────
def test_una_fila_VERDE_cuyo_juez_dice_que_NO_lo_enseña(tmp_path, monkeypatch):
    """`PASS` es el umbral del arnés (overall ≥ 4 y mecanismo ≥ 3) y «listo para producción» es la opinión del
    juez: dos preguntas distintas, las dos válidas, y no se fuerza a que coincidan. Lo que no puede es
    esconderse — una fila verde que abre con «No está listo para producción» le da al lector dos cosas
    contrarias en la misma línea, y la que se queda es el icono.

    Medido el 2026-08-28: 2 de las 13 verdes del tablero, las dos de esa madrugada.
    """
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(verdict={"overall": 4, "scores": {"mecanismo": 4},
                              "veredicto": "No está listo para producción: el bloqueador nº1 es…"})],
             sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert "✅" in fila and "el juez dice que NO está listo" in fila


def test_y_una_verde_conforme_no_arrastra_el_aviso(tmp_path, monkeypatch):
    """Un aviso que sale en cada fila verde deja de ser un aviso."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(verdict={"overall": 5, "scores": {"mecanismo": 5},
                              "veredicto": "Sí, está listo para producción: la ejecución es impecable."})],
             sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert "✅" in fila and "NO está listo" not in fila


def test_solo_se_mira_el_ARRANQUE_del_veredicto():
    """En el cuerpo la misma frase aparece a menudo negada, y buscarla en cualquier sitio marcaría filas que
    dicen justo lo contrario."""
    assert S._judge_says_not_ready("No está listo para producción: …")
    assert not S._judge_says_not_ready("El caso funciona; sería falso decir que no está listo.")
    assert not S._judge_says_not_ready("")


# ── y la ronda de infraestructura tiene que DECIRSE, no solo guardarse (2026-08-30) ───────────────────────
def test_el_supervisor_no_puede_leer_una_ronda_INFRA_como_FAIL():
    """`status.py::_infra` ya marcaba la fila INFRA con su motivo, y su propio comentario avisa de que fundir
    INFRA con FAIL «es como un marcador empieza a mentir». Pero el SUPERVISOR clasifica leyendo la SALIDA del
    runner, no el informe — así que veía «PASSED 0/1» y anotaba FAIL.

    Medido: la ronda de las 14:26 corrió con el recall degradado (el proveedor de embeddings se cayó a mitad),
    `status.json` la guardó como `state: INFRA` con su motivo, y la línea que lee el operador dijo FAIL. Dos
    vistas del mismo dato en desacuerdo, y la que se lee era la mala — que es exactamente cómo una ronda de
    infraestructura acaba atribuida al producto.
    """
    from tests.use_cases.e2e.agent.supervisor import _veredicto_de_cola

    cola = "INFRA: recall semántico DEGRADADO en esta ronda (backend: cloud)\nPASSED 0/1 (overall>=4)"
    assert _veredicto_de_cola(cola) == "INFRA", "una ronda con la infraestructura caída se anota como fallo del producto"

    # Los contrapesos, sin los cuales esto es «marcarlo todo INFRA»: una ronda normal que falla sigue siendo
    # FAIL, y una que pasa sigue siendo PASS.
    assert _veredicto_de_cola("PASSED 0/1 (overall>=4)") == "FAIL"
    assert _veredicto_de_cola("PASSED 1/1 (overall>=4)") == "PASS"


def test_el_runner_ANUNCIA_el_motivo_no_solo_la_palabra():
    """Con «INFRA» a secas el supervisor clasifica bien y el operador sigue sin saber cuál de las cuatro
    puertas fue: arnés caído, turnos vacíos, recall degradado o juez sin nota piden acciones OPUESTAS."""
    import inspect

    from tests.use_cases.e2e.agent import run as R

    src = inspect.getsource(R)
    assert 'print(f"INFRA: {r[\'_infra_reason\']}")' in src or "INFRA: {r['_infra_reason']}" in src, \
        "el runner anuncia INFRA sin decir de cuál — el motivo ya lo tiene delante"


def test_SANO_lo_decide_el_motor_no_una_copia_del_arnes():
    """Esta regla decía `backend != "ollama"`, y era verdad hasta la mañana del 2026-08-30: Ollama era el
    titular. V2-501 movió el titular a un proveedor de NUBE y la línea se quedó con la idea vieja de «sano»,
    así que **16 rondas de ese día salieron marcadas «recall DEGRADADO» con la memoria funcionando**: el
    endpoint contestaba en 0,29 s y el plató daba memoria OK. Dieciséis rondas archivadas como INFRA por una
    regla que envejeció en una mañana.

    Por eso no se copia la lista: se importa de quien la decide. Si el motor cambia de titular, el arnés
    cambia con él y nadie tiene que acordarse.
    """
    from memory.embeddings import _HEALTHY
    from tests.use_cases.e2e.agent import verify

    assert verify._backends_sanos() == tuple(_HEALTHY), (
        "el arnés guarda su propia idea de «sano» — es la que envejeció y archivó 16 rondas buenas")
    # Y la propiedad que importa en los dos sentidos: el titular de hoy NO es degradado, y el fallback SÍ.
    assert "cloud" in verify._backends_sanos()
    assert "hash" not in verify._backends_sanos(), "el hashing léxico no puede pasar por memoria sana"


def test_un_plato_SIN_NAVEGADOR_no_mide_una_busqueda():
    """Medido el 2026-08-30: el Chromium del plató US se cayó y no volvió. El log repetía «Waiting for the
    browser to settle before retrying» con HARD RESET cada pocos minutos, y las rondas salían con la hoja
    VACÍA — indistinguibles de «el producto no encuentra nada». La serie asentada bajó 3→3→2→1→0→0 y yo estaba
    a un mensaje de mandarlo como defecto de extracción.

    La firma es inequívoca y no se confunde con buscar mal: **un worker que busca mal aterriza en páginas
    malas; uno sin navegador no aterriza en ninguna.**
    """
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 0, "n_walls": 0},
        "worker_outcome": {"navigations": 3, "extractions": 0},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) == "INFRA"
    assert "NO tiene navegador" in r["_infra_reason"] and "3 intento" in r["_infra_reason"]


def test_pero_una_busqueda_MALA_sigue_siendo_del_producto():
    """El contrapeso, sin el cual esto archiva como INFRA cualquier ronda floja: si el worker SÍ aterrizó en
    páginas, buscó mal y eso es del producto."""
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 6, "n_walls": 0},
        "worker_outcome": {"navigations": 6, "extractions": 2},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) != "INFRA", "una búsqueda mala se está archivando como avería del plató"


def test_y_sin_poder_leer_el_recorrido_no_se_ACUSA():
    """Una ausencia de dato no es un dato: si el recorrido no se pudo leer, no se puede decir que no hubiera
    navegador."""
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": False, "n_pages": 0},
        "worker_outcome": {"navigations": 3},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) != "INFRA"


def test_un_puente_que_no_contesta_tampoco_mide_una_busqueda():
    """La variante que se coló (2026-08-30, `search-secondhand-monitor__es`): las 7 llamadas murieron EN EL
    PUENTE, `navigations` quedó a 0, y la condición del plató-sin-navegador —que exige intentos de navegar—
    no vio nada. La ronda salió FAIL siendo avería.

    La firma: el worker NOMBRÓ `nav_cli` (o sea que lo intentó), su sesión murió en Exit code 2, y ni una
    página se alcanzó. Un worker que decide no navegar no nombra `nav_cli`."""
    from tests.use_cases.e2e.agent.status import _state

    r = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 0},
        "worker_outcome": {"navigations": 0},
        "worker_bridges": {"read": True, "by_bridge": {"nav_cli": 1}, "sessions_with_exit2": 1},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r) == "INFRA"
    assert "puente del navegador no contestó" in r["_infra_reason"]

    # Contrapeso: un worker que ni intentó el navegador (caso conversacional) no es una avería.
    r2 = {"run": {"mechanism_report": {
        "page_journey": {"read": True, "n_pages": 0},
        "worker_outcome": {"navigations": 0},
        "worker_bridges": {"read": True, "by_bridge": {"mem_cli": 2}, "sessions_with_exit2": 0},
    }}, "verdict": {"overall": 2}}
    assert _state(2, r2) != "INFRA"
