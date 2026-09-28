"""Demo pass 2026-09-28, R3: «find me five days in her vacation where i'm free» — the agenda read came back with
nothing booked in the stretch, and the answer was «I can't give you five free days, because the only thing on the
calendar is Anna's vacation… I have nothing to check your availability against». The read's doctrine («use ONLY
what is here; what is not here is not stored») was read as a ban on INFERRING. With the line that separates
inventing a datum from reasoning with the data, the live composer answered 3/3 with five free dates."""
from nucleo.flash import widget_read as wr


def test_the_read_may_reason_and_may_not_invent():
    sysm = wr.compose_system("LANG", "find me five free days", "agenda", "q", "- 2026-12-20 Anna vacation",
                             answered=True)
    assert "INVENTAR un dato, no RAZONAR" in sysm and "un día sin citas es un día libre" in sysm


def test_the_doctrine_is_interpolated_not_printed_as_a_placeholder():
    for answered in (True, False):
        sysm = wr.compose_system("LANG", "x", "agenda", "q", "block", answered=answered)
        assert "{doctrine}" not in sysm and ("REGISTRO" in sysm or "RESUMEN" in sysm)
