"""Leer el número más alto NO evita la colisión, y esto está medido: T448, T454 y T457 salieron duplicados
el mismo día (2026-08-20), cada uno con su reparación a mano.

La ventana es la que hay entre «mira cuál es el último» y «escribe el fichero»: los dos lados miran, los dos
obtienen el mismo número, y solo después escriben. Y un número duplicado no es un desorden cosmético — dos
ficheros comparten `id`, así que el resolvedor del tick puede coger el que no es y re-medir un caso que nadie
pidió.

`claim_task` cierra la ventana con `open(..., "x")`: el primero se queda el nombre, el segundo recibe
FileExistsError y pasa al siguiente número.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import initiative as I


def test_two_claims_in_a_row_never_share_a_number(tmp_path):
    n1, p1 = I.claim_task(tmp_path / "tasks", "uc-caso-fix")
    n2, p2 = I.claim_task(tmp_path / "tasks", "uc-caso-fix")
    assert n1 != n2, "dos reservas seguidas se llevaron el mismo número"
    assert p1 != p2 and p1.exists() and p2.exists()


def test_the_file_exists_the_INSTANT_the_number_is_handed_out(tmp_path):
    """El punto entero: el número viene con el fichero ya creado. Si volviera solo el número, la ventana
    seguiría abierta hasta que alguien escribiese."""
    n, p = I.claim_task(tmp_path / "tasks", "uc-caso-fix")
    assert p.exists(), "el número se entregó sin reservar el fichero: la carrera sigue abierta"
    assert p.name == f"T{n}-uc-caso-fix.md"


def test_a_name_already_taken_by_SOMEONE_ELSE_is_skipped(tmp_path):
    """Simula al otro agente: el nombre que nos tocaría ya está ocupado, y hay que saltarlo en vez de pisarlo."""
    tasks = tmp_path / "tasks"
    tasks.mkdir(parents=True)
    n = I._next_task_number()
    (tasks / f"T{n}-uc-caso-fix.md").write_text("del otro agente")
    got, path = I.claim_task(tasks, "uc-caso-fix")
    assert got > n
    assert (tasks / f"T{n}-uc-caso-fix.md").read_text() == "del otro agente", "hemos pisado su tarea"


def test_it_creates_the_folder_if_it_is_a_new_module(tmp_path):
    n, p = I.claim_task(tmp_path / "modulo-nuevo" / "tasks", "uc-caso-fix")
    assert p.exists()
