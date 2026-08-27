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
    ronda se perdería. El sitio es después del `sleep`, con la vuelta ya cerrada."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text()
    i_ronda, i_sleep, i_rec = (src.index("una_ronda(esc)"), src.index("time.sleep(PAUSA_S)"),
                               src.index("_recargar_si_cambie(_mia)"))
    assert i_ronda < i_sleep < i_rec


def test_el_arranque_DICE_con_qué_fuente_corre():
    """Sin esta línea, «llevo tres horas midiendo» y «llevo tres horas midiendo con el código de hace tres
    horas» se ven exactamente igual en el terminal del operador."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text()
    assert "fuente {_mia}" in src and "HEAD {_sha()}" in src
