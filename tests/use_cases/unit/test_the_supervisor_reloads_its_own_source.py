"""Un proceso de Python no vuelve a leer su propio fichero (V2-372).

El supervisor llevaba desde las 08:03 corriendo el código de las 07:59, así que DOS arreglos suyos de esa
misma mañana estuvieron inertes sin que nada lo dijera:

    09:42  V2-363 — una avería del arnés no es un caso que falla
    10:12  V2-367 — los 103 escenarios que nunca habían corrido entran en la rotación

Medido a las 11:00: la ronda de `things-to-do-nearby-weekend__es` es INFRA en su propio informe —el juez no
devolvió JSON tras tres intentos, la conversación había ido bien y quedó guardada en `pending/`— y el diario
la apuntó **FAIL**, exactamente lo que V2-363 había arreglado tres horas antes. Y la rotación seguía siendo
la de 32 escenarios, no la de 132.

Lo que lo hace MUDO es la asimetría: `una_ronda` lanza la ronda como SUBPROCESO, así que el runner, el juez,
los escenarios y el motor entero SÍ se recargan en cada vuelta. El único que se queda atrás es este fichero
— el que CLASIFICA el resultado y ELIGE el orden. Desde fuera todo parece al día, y el parte hasta lleva el
`sha` de HEAD leído al empezar la ronda: **el diario afirma haber medido un commit cuyo clasificador no
estaba cargado.**

Cuarta vez de la misma familia («árbol limpio no es proceso al día») y la primera en la que quien lo paga es
el instrumento con el que se decide dónde trabajar.
"""
import pytest

from tests.use_cases.e2e.agent import supervisor as S


@pytest.fixture
def espia(monkeypatch):
    """Sustituye lo IRREVERSIBLE (el re-exec) y lo compartido (el diario) por testigos."""
    visto = {"exec": None, "diario": []}
    monkeypatch.setattr(S.os, "execv", lambda *a: visto.__setitem__("exec", a))
    monkeypatch.setattr(S, "_apunta", lambda **f: visto["diario"].append(f))
    monkeypatch.setattr(S, "_sha", lambda: "abc1234")
    return visto


def test_la_fuente_INTACTA_no_reinicia_nada(espia, monkeypatch):
    monkeypatch.setattr(S, "_huella", lambda: "misma")
    S._recargar_si_cambie("misma")
    assert espia["exec"] is None
    assert espia["diario"] == []


def test_la_fuente_CAMBIADA_se_recarga(espia, monkeypatch):
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    monkeypatch.setattr(S, "_fuente_utilizable", lambda: True)
    S._recargar_si_cambie("vieja")
    assert espia["exec"] is not None
    assert "tests.use_cases.e2e.agent.supervisor" in espia["exec"][1]


def test_la_recarga_DEJA_RASTRO_en_el_diario(espia, monkeypatch):
    """Un reinicio silencioso convierte «llevo tres horas midiendo» en una afirmación imposible de auditar:
    quien lea el diario tiene que poder ver dónde cambió el código con el que se estaba midiendo."""
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    monkeypatch.setattr(S, "_fuente_utilizable", lambda: True)
    S._recargar_si_cambie("vieja")
    (fila,) = espia["diario"]
    assert fila["resultado"] == "RECARGA"
    assert "vieja" in fila["motivo"] and "nueva" in fila["motivo"]


def test_una_fuente_ROTA_no_mata_el_bucle(espia, monkeypatch):
    """El bucle no puede pararse — es el único requisito que el operador ha repetido. Re-ejecutar sobre un
    fichero a medio escribir sería justo eso, y medir con código desfasado es peor defecto que quedarse sin
    medir solo si uno cree que las dos cosas cuestan igual. No cuestan igual."""
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    monkeypatch.setattr(S, "_fuente_utilizable", lambda: False)
    S._recargar_si_cambie("vieja")
    assert espia["exec"] is None
    assert espia["diario"] == []


def test_una_huella_ILEGIBLE_tampoco_reinicia(espia, monkeypatch):
    """`_huella()` devuelve "" si no puede leerse el fichero. Tratar eso como «cambió» reiniciaría en bucle."""
    monkeypatch.setattr(S, "_huella", lambda: "")
    S._recargar_si_cambie("vieja")
    assert espia["exec"] is None


def test_sin_huella_inicial_no_se_hace_nada(espia, monkeypatch):
    monkeypatch.setattr(S, "_huella", lambda: "nueva")
    S._recargar_si_cambie("")
    assert espia["exec"] is None


# ── lo que la fuente REAL tiene que cumplir ────────────────────────────────────────────────────────────────

def test_la_fuente_real_compila_y_tiene_huella():
    assert S._fuente_utilizable() is True
    assert len(S._huella()) == 12


def test_la_recarga_va_ENTRE_rondas_y_nunca_dentro():
    """A mitad de ronda hay un subproceso vivo con su navegador: re-ejecutar ahí lo dejaría huérfano y la
    ronda se perdería. El sitio es después del `sleep`, con la vuelta ya cerrada.

    Reescrito 2026-08-28, NO volteado: el ancla era el texto EXACTO `una_ronda(esc)` y se rompió al pasar el
    plató en la llamada (`una_ronda(esc, plato_de(esc))`, nodo 10.104). La propiedad protegida —el orden
    ronda → sleep → recarga— no cambió ni un ápice; lo que cambió es que ahora se busca la LLAMADA y no una
    de sus firmas posibles, para que el próximo argumento no vuelva a tumbar un test que no va de eso.
    """
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text()
    i_ronda, i_sleep, i_rec = (src.index("parte = una_ronda(esc"), src.index("time.sleep(PAUSA_S)"),
                               src.index("_recargar_si_cambie(_mia)"))
    assert i_ronda < i_sleep < i_rec


def test_el_arranque_DICE_con_qué_fuente_corre():
    """Sin esta línea, «llevo tres horas midiendo» y «llevo tres horas midiendo con el código de hace tres
    horas» se ven exactamente igual en el terminal del operador."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text()
    assert "fuente {_mia}" in src and "HEAD {_sha()}" in src


# ── El 24/7: lo que arranca al supervisor y lo vuelve a arrancar (V2-417) ────────────────────────────────
# Es shell y un plist, o sea lo que se rompe SIN HACER RUIDO: un `exec` que se cae deja a launchd vigilando
# un padre muerto, un candado sin comprobación real deja dos supervisores peleándose por UN navegador, y un
# `cd` con un nivel de más deja el envoltorio arrancando desde la carpeta equivocada. Nada de eso lanza.

_OPS = "tests/use_cases/e2e/agent/ops"
_ENV = "tests/use_cases/e2e/agent/supervisor_24x7.sh"


def _lee(ruta: str) -> str:
    from pathlib import Path
    return Path(ruta).read_text(encoding="utf-8")


def test_los_tres_ficheros_del_247_existen_y_son_ejecutables():
    import os
    from pathlib import Path
    for ruta in (_ENV, f"{_OPS}/keepalive.sh"):
        assert Path(ruta).exists(), f"falta {ruta}"
        assert os.access(ruta, os.X_OK), f"{ruta} no es ejecutable — launchd/el guardián fallan con 127"
    assert Path(f"{_OPS}/com.zaelar.usecases.supervisor.plist").exists()


def test_el_envoltorio_entra_al_bucle_con_exec():
    """Sin `exec`, quien vigila (launchd o el guardián) vigila a un shell padre que ya terminó, y el
    supervisor queda huérfano y sin nadie que lo levante cuando muera — que es justo para lo que existe."""
    src = _lee(_ENV)
    assert "exec caffeinate" in src and "exec ./.venv/bin/python" in src


def test_el_envoltorio_levanta_los_platos_antes_del_bucle():
    """Tras un reinicio no hay ningún plató vivo. Un supervisor contra puertos muertos no falla: escribe una
    fila INFRA por cada escenario de la rotación a toda velocidad, que es peor que estar parado."""
    src = _lee(_ENV)
    # La línea tiene que EJECUTARSE, no solo aparecer. Medido al desarmarlo el 2026-08-28: comentarla dejaba
    # el test verde sobre el defecto, porque el texto seguía ahí dentro del comentario.
    viva = [l for l in src.splitlines() if "tests.use_cases.lab up all" in l and not l.lstrip().startswith("#")]
    assert viva, "el envoltorio tiene que levantar los platós, no mencionarlos"
    assert src.index(viva[0]) < src.index("exec caffeinate")


def test_el_candado_del_guardian_se_comprueba_contra_el_proceso():
    """Un fichero de PID suelto NO basta: un guardián matado deja el suyo detrás y bloquea para siempre.
    Y dos guardianes son dos supervisores peleándose por el único navegador de cada plató."""
    src = _lee(f"{_OPS}/keepalive.sh")
    assert "kill -0" in src, "el candado tiene que preguntarle al SO si ese pid sigue vivo"
    assert "trap" in src and "rm -f" in src, "y soltarse al salir"


def test_el_plist_vigila_de_verdad():
    src = _lee(f"{_OPS}/com.zaelar.usecases.supervisor.plist")
    assert "<key>KeepAlive</key>" in src and "<key>RunAtLoad</key>" in src
    assert "<key>ThrottleInterval</key>" in src, ("sin respiro, un arranque que falla en bucle llena el "
                                                 "disco de logs en minutos")


def test_esta_escrito_por_que_launchd_no_basta_hoy():
    """El siguiente que lea esto va a intentar el plist. Que se entere aquí y no tras media hora: el repo
    vive bajo ~/Documents y TCC le niega la lectura a un agente de launchd (medido: `127 · can't open input
    file` sobre un fichero que existe y es ejecutable)."""
    src = _lee(f"{_OPS}/keepalive.sh")
    assert "TCC" in src and "Documents" in src and "127" in src
