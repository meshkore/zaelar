"""Las guardas de árbol corren UNA vez, y una tanda dura horas (V2-282).

Medido el 2026-08-24: arranqué cuatro casos con el árbol limpio y el motor recién levantado —las dos guardas
dijeron que sí, con razón— y edité `nucleo/` mientras corrían. Del segundo caso en adelante se midió código
que ya no existía en disco. Y como el marcador se escribe POR ESCENARIO, esa basura entra en el tablero
compartido caso a caso, con su fecha de hoy y su aire de medida buena.

Es literalmente el daño que `dirty_tree_refusal` existe para impedir — su propia docstring dice «una ronda
medida a mitad de una edición no se puede comparar con ninguna otra» — y la guarda no podía verlo, porque
solo mira ANTES del primer caso.

⚠️ SEGUNDA PARTE, medida el MISMO día y peor que la primera. La guarda escrita para cerrar eso preguntaba
`config.code_stamp()`, que MEMOIZA, y declaraba movimiento con `or bool(dirty)`. Dos defectos en uno:

  1. con el stamp cacheado NO PODÍA ver una edición a mitad de tanda — o sea que no cerraba nada de lo de
     arriba, solo lo parecía;
  2. y paraba la tanda tras el PRIMER caso siempre que el árbol ya estuviera sucio al arrancar, que es lo
     normal cuando otro agente tiene ficheros en vuelo. Cuatro casos por tanda se convirtieron en uno
     durante una tarde entera.

«Está sucio» y «se ha movido» son dos afirmaciones distintas soldadas en una. Un árbol sucio y QUIETO es
perfectamente comparable consigo mismo; lo que rompe la comparación es que el CONTENIDO cambie, con commit o
sin él. Por eso ahora se compara una HUELLA contra sí misma.

Los tests de fuente de este fichero no bastan y hay que decirlo: los dos defectos de arriba habrían pasado
CUALQUIER grep —la línea estaba escrita y era la que se buscaba— así que la mitad importante son los tests de
CONDUCTA sobre `engine_fingerprint`/`engine_moved`, que corren contra un repo git de verdad.
"""
import inspect
import subprocess

from tests.use_cases.e2e.agent import config as cfgmod
from tests.use_cases.e2e.agent import run as runmod


# ---------------------------------------------------------------- la huella, contra un repo git de verdad

def _repo(tmp_path):
    """Un repo con un commit, un fichero de motor y otro bajo `tests/` — la frontera que la huella respeta.

    El `git init` va en `engine/`, no en `tmp_path`, y eso NO es cosmético: `git status --porcelain` da rutas
    relativas a la RAÍZ DEL REPO, así que la exclusión de `tests/` solo casa si la raíz del repo es la misma
    que la raíz que `engine_fingerprint` calcula desde su `__file__`. En el árbol real lo es (el motor es su
    propio repo, separado del workspace); montarlo de otra forma aquí pondría en verde una exclusión rota.
    """
    root = tmp_path / "engine"
    root.mkdir()

    def git(*a):
        subprocess.run(["git", *a], cwd=str(root), capture_output=True, text=True, check=False)

    git("init", "-q")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (root / "nucleo.py").write_text("x = 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "t.py").write_text("y = 1\n")
    git("add", "-A"); git("commit", "-qm", "base")
    return root, git


def _fingerprint_at(monkeypatch, root):
    """`engine_fingerprint` resuelve su raíz desde su propio `__file__`; se la apuntamos al repo de prueba."""
    fake_file = root / "tests" / "use_cases" / "e2e" / "agent" / "config.py"
    monkeypatch.setattr(cfgmod, "__file__", str(fake_file), raising=False)
    return cfgmod.engine_fingerprint()


def test_la_huella_es_ESTABLE_si_nadie_toca_nada(tmp_path, monkeypatch):
    root, _ = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    b = _fingerprint_at(monkeypatch, root)
    assert a and a == b, "dos lecturas seguidas del mismo árbol tienen que dar lo mismo"
    assert not cfgmod.engine_moved(a, b)


def test_un_arbol_SUCIO_y_QUIETO_no_se_ha_movido(tmp_path, monkeypatch):
    """EL caso que costó la tarde: otro agente con ficheros en vuelo desde ANTES de arrancar la tanda."""
    root, _ = _repo(tmp_path)
    (root / "nucleo.py").write_text("x = 2\n")      # sucio ANTES de la primera huella
    a = _fingerprint_at(monkeypatch, root)
    b = _fingerprint_at(monkeypatch, root)
    assert not cfgmod.engine_moved(a, b), (
        "sucio no es movido: si esto vuelve a ser True, la tanda se para tras el primer caso otra vez")


def test_editar_SIN_commitear_SI_es_movimiento(tmp_path, monkeypatch):
    """La forma original: los ficheros cambian y el sha se queda igual."""
    root, _ = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "nucleo.py").write_text("x = 99\n")
    b = _fingerprint_at(monkeypatch, root)
    assert cfgmod.engine_moved(a, b), "un cambio de CONTENIDO sin commit tiene que verse"


def test_un_fichero_NUEVO_sin_seguir_tambien_cuenta(tmp_path, monkeypatch):
    root, _ = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "otro.py").write_text("z = 1\n")
    assert cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_tocar_tests_NO_es_mover_el_motor(tmp_path, monkeypatch):
    """El arnés se edita a sí mismo a todas horas; contarlo dejaría la guarda disparando siempre."""
    root, _ = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "tests" / "t.py").write_text("y = 2\n")
    assert not cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_commitear_un_cambio_del_MOTOR_si_mueve_la_huella(tmp_path, monkeypatch):
    """Un cambio del motor mueve la huella lo commitees o no: lo que se compara es el CONTENIDO."""
    root, git = _repo(tmp_path)
    (root / "nucleo.py").write_text("x = 3\n")
    a = _fingerprint_at(monkeypatch, root)
    git("add", "-A"); git("commit", "-qm", "otro")
    assert cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_commitear_SOLO_tests_NO_mueve_el_motor(tmp_path, monkeypatch):
    """Mi propio defecto, y el MISMO que este fichero vino a arreglar: allí «sucio» no era «movido», y aquí
    «hay un commit nuevo» tampoco lo es. Se pagó dos veces la misma tarde — un commit del arnés y otro de un
    agente— cortando una tanda a mitad cada uno, con el motor idéntico a los dos lados."""
    root, git = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "tests" / "t.py").write_text("y = 3\n")
    git("add", "-A"); git("commit", "-qm", "solo tests")
    assert not cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_un_fichero_del_motor_BORRADO_si_mueve_la_huella(tmp_path, monkeypatch):
    """Sensibilidad por el lado contrario: hashear la lista de blobs tiene que notar una ausencia, no solo
    un cambio de contenido."""
    root, git = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "nucleo.py").unlink()
    git("add", "-A"); git("commit", "-qm", "fuera")
    assert cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_no_saber_NO_es_haberse_movido():
    """Al revés que `stale_engine_refusal`: allí no saber obliga a rechazar porque el daño es mudo y caro;
    aquí una falsa alarma para la tanda, y una huella ilegible no es prueba de nada."""
    assert cfgmod.engine_moved("", "abc") is False
    assert cfgmod.engine_moved("abc", "") is False
    assert cfgmod.engine_moved("", "") is False


def test_la_huella_NO_memoiza():
    """`code_stamp()` cachea a propósito y por eso no servía aquí: una huella que se llama dos veces para
    compararse consigo misma no puede devolver siempre lo mismo por construcción."""
    src = inspect.getsource(cfgmod.engine_fingerprint)
    assert "global" not in src and "_CODE_STAMP" not in src


# ---------------------------------------------------------------- el cableado dentro del bucle

def test_la_comprobacion_esta_DENTRO_del_bucle_de_casos():
    src = inspect.getsource(runmod._run_batch)
    i_bucle = src.find("for scenario in chosen:")
    assert i_bucle > 0
    assert 0 <= src.find("_tree_at_start") < i_bucle, "el sello se toma antes del bucle, que es donde vale"
    assert src.find("config.engine_fingerprint()", i_bucle) > i_bucle, (
        "hay que volver a MIRAR el árbol dentro del bucle, no releer un sello cacheado")


def test_NO_pregunta_por_code_stamp_dentro_del_bucle():
    """La trampa exacta: `code_stamp()` memoiza, así que preguntárselo dentro del bucle es preguntar al pasado."""
    src = inspect.getsource(runmod._run_batch)
    i_bucle = src.find("for scenario in chosen:")
    assert "config.code_stamp()" not in src[i_bucle:]


def test_para_la_tanda_y_dice_como_retomarla():
    src = inspect.getsource(runmod._run_batch)
    assert "--start-at {scenario.id}" in src, (
        "sin decir por dónde se retoma, parar la tanda cuesta volver a correr lo ya medido")
    assert "el MOTOR se ha movido" in src


def test_NO_dispara_en_el_primer_caso():
    """El primer caso ya lo cubren las guardas de arranque; volver a preguntarle sería pararse antes de medir."""
    src = inspect.getsource(runmod._run_batch)
    assert "if results and not allow_dirty:" in src, (
        "la comprobación tiene que exigir que YA haya un caso corrido, o la tanda no arranca nunca")


def test_y_se_puede_apagar_con_allow_dirty():
    """`--allow-dirty` es «mido mi propio cambio a posta»: si no lo respetara, el agente que arregla no puede
    medir su trabajo en curso — que es justo para lo que existe ese flag."""
    assert "allow_dirty" in inspect.signature(runmod._run_batch).parameters
    src = inspect.getsource(runmod)
    # y los TRES caminos se lo pasan: uno que se lo olvide mide sucio en silencio, que es el fallo de partida
    assert src.count('allow_dirty=getattr(args, "allow_dirty", False),\n') >= 3
