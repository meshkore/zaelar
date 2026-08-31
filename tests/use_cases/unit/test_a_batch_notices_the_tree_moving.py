"""Tree guards run ONCE, and a batch lasts for hours (V2-282).

Measured on 2026-08-24: I started four cases with a clean tree and the engine freshly started —both guards
correctly said yes— and edited `nucleo/` while they were running. From the second case onward, code was measured
that no longer existed on disk. And because the marker is written PER SCENARIO, that garbage enters the shared
dashboard case by case, with today's date and the appearance of a valid measurement.

This is literally the damage that `dirty_tree_refusal` exists to prevent — its own docstring says “a round
measured halfway through an edit cannot be compared with any other” — and the guard could not see it because
it only looks BEFORE the first case.

⚠️ SECOND PART, measured on the SAME day and worse than the first. The guard written to close that gap asked for
`config.code_stamp()`, which MEMOIZES, and declared movement with `or bool(dirty)`. Two defects in one:

  1. with the cached stamp it COULD NOT see an edit halfway through a batch — meaning it closed none of what
     is described above, it only appeared to;
  2. and it stopped the batch after the FIRST case whenever the tree was already dirty at startup, which is
     normal when another agent has files in flight. Four cases per batch became one for an entire afternoon.

“It is dirty” and “it has moved” are two distinct claims welded into one. A dirty and STILL tree is perfectly
comparable with itself; what breaks the comparison is for the CONTENT to change, with or without a commit.
That is why a FINGERPRINT is now compared with itself.

The source tests in this file are not enough, and that must be said: either of the two defects above would have
passed ANY grep —the line was present and was the one being sought— so the important half is the BEHAVIOR tests
for `engine_fingerprint`/`engine_moved`, which run against a real git repository.
"""
import inspect
import subprocess

from tests.use_cases.e2e.agent import config as cfgmod
from tests.use_cases.e2e.agent import run as runmod


# ---------------------------------------------------------------- the fingerprint, against a real git repository

def _repo(tmp_path):
    """A repo with one commit, one engine file, and another under `tests/` — the boundary respected by the fingerprint.

    `git init` runs in `engine/`, not in `tmp_path`, and that is NOT cosmetic: `git status --porcelain` gives
    paths relative to the REPO ROOT, so excluding `tests/` only matches if the repo root is the same as the root
    that `engine_fingerprint` calculates from its `__file__`. It is in the real tree (the engine is its own repo,
    separate from the workspace); setting it up differently here would make a broken exclusion appear to work.
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
    """`engine_fingerprint` resolves its root from its own `__file__`; we point it at the test repo."""
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
    """THE case that cost the afternoon: another agent with files in flight from BEFORE the batch started."""
    root, _ = _repo(tmp_path)
    (root / "nucleo.py").write_text("x = 2\n")      # dirty BEFORE the first fingerprint
    a = _fingerprint_at(monkeypatch, root)
    b = _fingerprint_at(monkeypatch, root)
    assert not cfgmod.engine_moved(a, b), (
        "sucio no es movido: si esto vuelve a ser True, la tanda se para tras el primer caso otra vez")


def test_editar_SIN_commitear_SI_es_movimiento(tmp_path, monkeypatch):
    """The original form: the files change and the sha stays the same."""
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
    """The harness edits itself constantly; counting it would leave the guard triggering all the time."""
    root, _ = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "tests" / "t.py").write_text("y = 2\n")
    assert not cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_commitear_un_cambio_del_MOTOR_si_mueve_la_huella(tmp_path, monkeypatch):
    """An engine change moves the fingerprint whether you commit it or not: what is compared is the CONTENT."""
    root, git = _repo(tmp_path)
    (root / "nucleo.py").write_text("x = 3\n")
    a = _fingerprint_at(monkeypatch, root)
    git("add", "-A"); git("commit", "-qm", "otro")
    assert cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_commitear_SOLO_tests_NO_mueve_el_motor(tmp_path, monkeypatch):
    """My own defect, and the SAME one this file came to fix: there, “dirty” was not “moved”, and here
    “there is a new commit” is not either. The same afternoon paid twice — one harness commit and one from an
    agent— each cutting a batch in half, with the engine identical on both sides."""
    root, git = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "tests" / "t.py").write_text("y = 3\n")
    git("add", "-A"); git("commit", "-qm", "solo tests")
    assert not cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_un_fichero_del_motor_BORRADO_si_mueve_la_huella(tmp_path, monkeypatch):
    """Sensitivity in the opposite direction: hashing the blob list must detect an absence, not just a content
    change."""
    root, git = _repo(tmp_path)
    a = _fingerprint_at(monkeypatch, root)
    (root / "nucleo.py").unlink()
    git("add", "-A"); git("commit", "-qm", "fuera")
    assert cfgmod.engine_moved(a, _fingerprint_at(monkeypatch, root))


def test_no_saber_NO_es_haberse_movido():
    """Unlike `stale_engine_refusal`: there, not knowing requires refusal because the damage is silent and costly;
    here it would be a false alarm for the batch, and an unreadable fingerprint is proof of nothing."""
    assert cfgmod.engine_moved("", "abc") is False
    assert cfgmod.engine_moved("abc", "") is False
    assert cfgmod.engine_moved("", "") is False


def test_la_huella_NO_memoiza():
    """`code_stamp()` caches deliberately and therefore was not suitable here: a fingerprint called twice to
    compare itself with itself cannot always return the same thing by design."""
    src = inspect.getsource(cfgmod.engine_fingerprint)
    assert "global" not in src and "_CODE_STAMP" not in src


# ---------------------------------------------------------------- the wiring inside the loop

def test_la_comprobacion_esta_DENTRO_del_bucle_de_casos():
    src = inspect.getsource(runmod._run_batch)
    i_bucle = src.find("for scenario in chosen:")
    assert i_bucle > 0
    assert 0 <= src.find("_tree_at_start") < i_bucle, "el sello se toma antes del bucle, que es donde vale"
    assert src.find("config.engine_fingerprint()", i_bucle) > i_bucle, (
        "hay que volver a MIRAR el árbol dentro del bucle, no releer un sello cacheado")


def test_NO_pregunta_por_code_stamp_dentro_del_bucle():
    """The exact trap: `code_stamp()` memoizes, so asking it inside the loop means asking the past."""
    src = inspect.getsource(runmod._run_batch)
    i_bucle = src.find("for scenario in chosen:")
    assert "config.code_stamp()" not in src[i_bucle:]


def test_para_la_tanda_y_dice_como_retomarla():
    src = inspect.getsource(runmod._run_batch)
    assert "--start-at {scenario.id}" in src, (
        "sin decir por dónde se retoma, parar la tanda cuesta volver a correr lo ya medido")
    assert "el MOTOR se ha movido" in src


def test_NO_dispara_en_el_primer_caso():
    """The first case is already covered by the startup guards; asking again would stop before measuring."""
    src = inspect.getsource(runmod._run_batch)
    assert "if results and not allow_dirty:" in src, (
        "la comprobación tiene que exigir que YA haya un caso corrido, o la tanda no arranca nunca")


def test_y_se_puede_apagar_con_allow_dirty():
    """`--allow-dirty` means “I am deliberately measuring my own change”: if it were not respected, the fixing
    agent could not measure its work in progress — which is exactly what that flag exists for."""
    assert "allow_dirty" in inspect.signature(runmod._run_batch).parameters
    src = inspect.getsource(runmod)
    # and ALL THREE paths pass it: forgetting one would silently measure dirty, which is the original failure
    assert src.count('allow_dirty=getattr(args, "allow_dirty", False),\n') >= 3
