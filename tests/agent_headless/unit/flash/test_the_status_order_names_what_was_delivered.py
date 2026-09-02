"""V2-556 — «¿tienes algo?» over three named cars was answered «sigo sin tener anuncios concretos».

Third round of the V2-222 family, and this time the branch that fixes it was ALREADY WRITTEN — fifteen lines
further down. The FIRST imperative the model reads about the operator asking for status only ever spoke about
the STEP («di el PASO concreto y el tiempo que lleva»), so that is the one it obeyed, and the anti-negation
paragraph below never got a turn. Measured in `search-buy-used-car__es` (2026-09-02, run v3): the prompt said

    … — YA ENTREGADO (de su hoja): «AUDI A3 1.6TDI S Line Edition 81kW — 10.990 EUR»; «AUDI Q5 2.0TDI
    quattro Ambition 177 — 9.590 EUR»; «BMW X3 2.0d — 9.980 EUR» (llevas 37s)

and the turn answered «Sigo sin tener anuncios concretos, la búsqueda va en el paso inicial y no ha avanzado.
Va lenta y puede haberse atascado» — negating a delivery AND inventing a stall at 37 seconds, over a block
that carries neither ENCALLADA nor SIN AVANZAR. Two instructions in one paragraph come out heads-or-tails:
the fork goes INSIDE the imperative.
"""
import pytest

from nucleo import dispatch as D
from nucleo.flash import live_blocks as LB
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.clear()
    yield
    T._tasks.clear()
    D._SESSIONS.clear()


def _errand_with_rows(sheet="v556-1"):
    rec = SessionRecord(task_id="w556", goal="coche diésel por menos de 12 mil", kind="web")
    rec.status, rec.sheet = "running", sheet
    D._SESSIONS["w556"] = rec
    SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados", "items": [
        {"title": "AUDI A3 1.6TDI S Line Edition 81kW", "price": "10.990 EUR"},
        {"title": "AUDI Q5 2.0TDI quattro Ambition 177", "price": "9.590 EUR"},
        {"title": "BMW X3 2.0d", "price": "9.980 EUR"}]})
    return rec


def test_the_status_order_itself_forks_on_what_was_delivered():
    """The order about «¿tienes algo?» has to name the delivered rows, not only the step."""
    _errand_with_rows()
    st = "\n".join(LB.pending_task_lines())
    orden = st[st.index("Si el operador pregunta el estado"):][:600]
    assert "YA ENTREGADO" in orden, "la primera orden sobre el estado sigue hablando SOLO del paso"
    assert "AUDI A3 1.6TDI S Line Edition 81kW — 10.990 EUR" in st, "las filas tienen que estar ahí"


def test_a_stall_may_only_be_claimed_when_the_block_says_so():
    """37 s is not a stall. The permission to say «se ha atascado» is tied to the block's own words."""
    _errand_with_rows(sheet="v556-2")
    st = "\n".join(LB.pending_task_lines())
    assert "ENCALLADA o SIN AVANZAR" in st
    assert "ENCALLADA:" not in st and "SIN AVANZAR:" not in st, "esta tarea NO está encallada: es la premisa"


def test_the_anti_negation_branch_is_still_there():
    """The paragraph V2-222 added stays: this change puts the fork EARLIER, it does not replace it."""
    _errand_with_rows(sheet="v556-3")
    st = "\n".join(LB.pending_task_lines())
    assert "negar una entrega que el operador tiene" in st
