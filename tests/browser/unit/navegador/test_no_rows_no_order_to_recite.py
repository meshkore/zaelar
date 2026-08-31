"""V2-330 — with no written rows, the face CANNOT order it to recite them: it was an impossible imperative.

The block said «TELL IT in this turn WHATEVER FITS, with name and price», and the rows (`_rows_bit`) are only
added when the sheet ALREADY has one with a name. Without them, the turn received an order it could not fulfill, and
the model answered with the only honest thing left to it: «I'll let you know as soon as I have something».

MEASURED across the studio turns (2026-08-25, from 21:00 onward), counting only those in which this
face fires:

    WITHOUT rows in the prompt : 14 turns · 79 % respond with waiting
    WITH rows in the prompt    : 45 turns · 42 % respond with waiting

The 79 % was not disobedience: it was the only way out we left it. And that is how it looked from the outside — five of the
ten cases with mechanism ≥4 and result ≤3 carried this verdict, and the one for `search-buy-camera__es` quotes the
instruction by name:

    «the model ignores that the task already has results (instruction 'TELL IT') and lies by saying it is still
     searching»

This is exactly the trap that the docstring of `_sheet_top_rows` has named since V2-298 — «an instruction that the
prompt makes impossible to fulfill is not an instruction; it is a trap for the model AND for whoever reads the
transcript»— and we wrote it ourselves.

⚠️ The remaining 42 % (with rows in front of it and still waiting) is ANOTHER defect, and this change does not touch it.
"""
import pytest

from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def _estado(goal, sheet, items):
    tid = T.create(goal, sheet=sheet)
    T.set_status(tid, "working")
    T.set_results(tid, {"conclusion": "", "items": [{"title": "algo"}]})   # the task DID find something
    if items:
        SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados", "items": items})
    return "\n".join(LB.navegador_lines())


def test_sin_filas_NO_se_le_ordena_recitar():
    st = _estado("Busca una guitarra acústica", "v330-1", [])
    assert "CUÉNTALE en este turno LO QUE ENCAJE" not in st, (
        "se le pide con nombre y precio algo que el prompt no le da")


def test_sin_filas_se_le_dice_la_VERDAD_de_lo_que_hay():
    """Rewritten 2026-08-28 (V2-443), NOT reverted. The property is the same —with no rows, it is told the truth about
    what exists, neither an impossible recital nor a refusal— and what changed is WHICH truth that is.

    V2-330 wrote it as «YA HA ENCONTRADO algo», and with no rows that can only be read from `kept`: the count
    reported by the worker itself. Measured in `find-theatre-tickets__us` (2026-08-28), that claim was FALSE
    eleven times in one round — `worker_outcome.found: []`, the sheet empty everywhere. The claim is
    now marked as what it is (the worker's, unchecked) and our fact —not a single row has arrived— is stated
    firmly.
    """
    st = _estado("Busca una guitarra acústica", "v330-2", [])
    assert "DICE QUE YA TIENE CANDIDATOS" in st and "no la hemos comprobado" in st
    assert "NO ha llegado ni una fila" in st


def test_se_separa_NO_HA_LLEGADO_de_NO_HA_ENCONTRADO():
    """Rewritten 2026-08-28 (V2-443), NOT reverted — and this is the rewrite that matters most to understand.

    V2-330 prohibited «no ha encontrado nada» because with the worker producing, the opposite is happening, and
    that remains true: the world may be full and we may not know it. What the prohibition swept away
    was the TRUE and useful phrase —«todavía no ha llegado nada»—, which speaks about DELIVERY and is our
    fact. Without it, the only way out left to the turn was to claim that it was already bringing things out.

    So the prohibition is not lifted: it is split in two, which is what allows the operator to decide whether to
    wait or change course.
    """
    st = _estado("Busca una guitarra acústica", "v330-3", [])
    assert "«NO HA ENCONTRADO nada»" in st and "NO LO SABES" in st
    assert "«TODAVÍA NO HA LLEGADO nada» es cierto y puedes decirlo" in st


def test_no_se_le_deja_INVENTARSE_un_nombre():
    """The risk of the fix on the other side: if it is simply told «cuéntale que va bien», it fills in the gap."""
    st = _estado("Busca una guitarra acústica", "v330-4", [])
    assert "NO te inventes nombres" in st


def test_CON_filas_el_imperativo_de_siempre_sigue_intacto():
    """The important sensitivity: this change MUST NOT remove the order to recite when it does have something to recite."""
    st = _estado("Busca una guitarra acústica", "v330-5",
                 [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"}])
    assert "CUÉNTALE en este turno LO QUE ENCAJE" in st
    assert "LO QUE YA HA ENTREGADO" in st
    assert "Fender CD-60 — 120 €" in st
    assert "DICE QUE YA TIENE CANDIDATOS" not in st


def test_las_dos_ramas_son_EXCLUYENTES():
    """A task cannot receive both orders at once: that would be the contradiction V2-318 removed."""
    con = _estado("Busca un monitor", "v330-6", [{"title": "Monitor MSI 27", "price": "100 €"}])
    sin = _estado("Busca otra cosa", "v330-7", [])
    assert ("CUÉNTALE en este turno LO QUE ENCAJE" in con) != ("CUÉNTALE en este turno LO QUE ENCAJE" in sin)
