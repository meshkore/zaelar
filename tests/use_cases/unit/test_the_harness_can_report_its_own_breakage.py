"""V2-291 — el único camino que existe para decir «esta ronda no mide al producto» estaba roto.

`_run_scenario` marca la ronda como avería del ARNÉS cuando el modelo que hace de usuario se sale de su papel más
de una vez (V2-285: su reacción a un turno imposible no dice nada de zaelar). Esa marca se escribía en `run_data`
**treinta y siete líneas antes de que `run_data` existiera**, así que la rama entera reventaba con un
`UnboundLocalError`.

Medido el 2026-08-24 12:35 en `search-buy-camera__es`: la ronda salió

    INFRA: cannot access local variable 'run_data' where it is not associated with a value

con **0 turnos, sin transcript y sin informe de mecanismo** — o sea que además se llevó por delante la evidencia
de todo lo que SÍ había pasado en esa ronda. El camino escrito para reconocer una avería del arnés era él mismo
una avería del arnés, y no había corrido nunca desde que se escribió.

Lo que este fichero guarda son las dos mitades: que el marcador llega a `run_data` (y que el marcador es lo que
`status.py` lee para no contar la ronda contra el caso), y que **ninguna escritura en `run_data` precede a su
definición** — que es la clase, no la instancia.
"""
import ast
import pathlib

RUN = pathlib.Path(__file__).resolve().parents[2] / "use_cases" / "e2e" / "agent" / "run.py"


def _fn(name: str) -> ast.FunctionDef:
    tree = ast.parse(RUN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} ya no existe en run.py — si se renombró, este guarda mira al vacío")


def test_nothing_writes_run_data_before_it_exists():
    """LA CLASE, no el caso: `_run_scenario` es una función larga y de un solo uso —no hay forma de instanciarla
    sin motor, sandbox y modelo— así que lo que se puede comprobar barato es el ORDEN. Un `run_data[...]` por
    encima de su asignación es un `UnboundLocalError` esperando a que se cumpla su condición, y aquí la condición
    era «el arnés se rompió», o sea la que menos se ejercita y más caro cuesta perder."""
    fn = _fn("_run_scenario")
    born = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name) and t.id == "run_data"]
    assert born, "`run_data` ya no se asigna por nombre: revisa este guarda antes de fiarte de él"
    first = min(born)
    early = [n.lineno for n in ast.walk(fn)
             if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
             and n.value.id == "run_data" and n.lineno < first]
    assert not early, (f"`run_data[...]` en las líneas {early}, y no nace hasta la {first}: esa rama revienta "
                       f"con UnboundLocalError el día que se cumpla su condición")


def test_the_breakage_marker_is_the_one_the_scoreboard_reads():
    """El marcador no vale por existir: `status.py` decide con ÉL si la ronda cuenta contra el caso. Si alguien
    lo renombra en un lado, la ronda vuelve a puntuar al producto por un fallo nuestro — en silencio."""
    src = RUN.read_text(encoding="utf-8")
    status = (RUN.parent / "status.py").read_text(encoding="utf-8")
    assert 'run_data["crashed"] = crashed' in src
    assert 'run.get("crashed")' in status


def test_the_marker_survives_next_to_the_evidence():
    """La ronda averiada tiene que llegar al informe CON su transcript y su mecanismo. La versión rota no solo no
    marcaba: se llevaba por delante los 0 turnos y todo lo medido, que es lo que hace falta para entender qué
    pasó."""
    src = RUN.read_text(encoding="utf-8")
    i = src.index('run_data = {"transcript": transcript')
    j = src.index('run_data["crashed"] = crashed')
    assert i < j, "el marcador se escribe antes de que `run_data` traiga la evidencia"
