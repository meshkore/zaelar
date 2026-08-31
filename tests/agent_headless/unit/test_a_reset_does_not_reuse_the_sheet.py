"""A RESET rewound the counter but not the seal, so the next search inherited—and erased—the previous
one's box (V2-283).

Measured in the 2026-08-24 03:02 batch: FOUR cases in a single studio process, and all four tasks
landed in `results--c2567e-1`. The same box, started with `begin_task(fresh=True)` each time, so each
case erased the previous one's findings. The MONITOR case report contained six GUITARRA titles, and
the GUITARRA report contained BICICLETA titles.

This is LITERALLY what the operator asked us to eliminate when requesting one sheet per task: “with this rule we
will not make mistakes by erasing searches.” And it is not test-only: `nucleo/reset.py::reset_all()` is the operator's
⏻—“we start from zero”—so in production, after a reset, the next search inherits the previous one's box and starts it.

The cause: `sheet_id_for` combines `boot_id()` with the `task_id`, and `escalate.reset()` rewinds that counter
while the seal remains the same—stable seal × rewound counter = same id. V2-259 closed the PROCESS RESTART
path with `boot_id()`; this is the same failure through the reset path, and the seal could not detect it because
it only changed when a process started.

⚠️ And the seal module stated the opposite: its docstring said “for TESTS … production never rewinds a
sequence,” and that was false on the day it was written—`reset_all` had called it from the very beginning. The class
of problem that module exists to prevent was occurring through the path its author thought was for tests.
"""
from nucleo import runtime_ids as R
from nucleo.flash import escalate


def test_rebobinar_el_contador_hace_ROTAR_el_sello():
    antes, seq_antes = R.boot_id(), R.next_seq("prueba.hoja")
    R.reset_seq("prueba.hoja")
    despues, seq_despues = R.boot_id(), R.next_seq("prueba.hoja")
    assert seq_antes == seq_despues, "el contador SÍ rebobina — eso no cambia, es lo que pide «de cero»"
    assert antes != despues, "el sello sobrevivió al rebobinado: los ids vuelven a chocar"


def test_y_por_eso_dos_encargos_separados_por_un_reset_NO_comparten_hoja():
    """The measured case, using the function that actually composes the id."""
    from nucleo import sheets
    escalate.reset()
    primero = sheets.sheet_id_for(escalate._next_seq("escalate.task"))
    escalate.reset()                                  # the operator's ⏻, or the reset between harness cases
    segundo = sheets.sheet_id_for(escalate._next_seq("escalate.task"))
    assert primero != segundo, (
        "la segunda búsqueda hereda la caja de la primera y `begin_task(fresh=True)` la borra")


def test_el_contador_SIGUE_rebobinando_no_se_arregla_congelandolo():
    """Sensitivity from the other side: stopping the rewind would make the ids grow forever after each reset,
which is not what was requested—the seal must change, not the counter."""
    escalate.reset()
    a = escalate._next_seq("escalate.task")
    escalate.reset()
    assert escalate._next_seq("escalate.task") == a == 1


def test_dentro_de_UNA_sesion_los_ids_siguen_siendo_estables():
    """The seal must NOT rotate just from breathing: if it changed on every call, a live task's sheet would move
out from under whoever is looking at it."""
    R.next_seq("prueba.estable")
    a = R.boot_id()
    for _ in range(5):
        R.next_seq("prueba.estable")
    assert R.boot_id() == a


def test_la_docstring_ya_NO_afirma_que_produccion_no_rebobina():
    """The false claim was why nobody looked here. It remains written down that it is not true."""
    d = R.reset_seq.__doc__ or ""
    # We check the CORRECTION, not the absence of the phrase: the new docstring CITES the old one to explain the
    # failure, and a guard that confuses the explanation with the claim would force us to delete the why (the same trap
    # as the `--start-at` message a few hours earlier).
    assert "was FALSE" in d, "la docstring vuelve a afirmar, sin más, que producción no rebobina"
    assert "reset_all" in d, "hay que decir QUIÉN rebobina en producción"
