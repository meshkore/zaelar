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


def test_los_ERRORES_de_puente_se_siguen_diciendo():
    """V2-399 seguía en pie: un worker cuyos puentes fallan no es un worker sin criterio."""
    txt = mechanism_facts(_mech(worker_bridges={
        "read": True, "sessions": 1, "by_bridge": {"nav_cli": 1}, "errors": {"nav_cli": 3}}))
    assert "PUENTES DEL WORKER CON ERRORES" in txt and "nav_cli ×3" in txt
