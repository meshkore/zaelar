"""V2-213 — «try another site» without saying WHICH one is a wish, not an instruction.

The wall reaches everywhere it should: the task records it (V2-176), the worker's CLI prints it (V2-186), the
turn says it out loud (V2-185, and `book-hotel`'s own transcript proves it: «it has been blocked a couple of
times… should I continue or stop?»). And the runs still ground against the same host: thirteen minutes on
`nh-hotels.com` in `book-hotel-night-known__es`, and `restaurant-tonight-madrid` ending on a DuckDuckGo results
page after Casa Lucio.

The missing piece was never the information. It was the ALTERNATIVE: the catalog held exactly ONE site per
category, so when the trusted one served an anti-bot page there was literally nowhere written down to go, and
the worker was asked to invent one mid-task. Naming the alternative is what turns the instruction into
something followable — the same lesson four bridges learned today.

The host that just blocked us is EXCLUDED: offering the site it is stuck on reads as «insist».
"""
import pytest

from nucleo.flash import site_catalog as sc


def test_the_walled_host_is_never_offered_back():
    alts = sc.alternatives_for("resérvame una noche en el Hotel Palacio de la Merced", "www.booking.com", "es")
    assert alts
    assert not any("booking.com" in u for _, u in alts)


def test_without_a_wall_host_the_trusted_site_leads():
    """Same function serves «where should I be», and the trusted entry is the answer when nothing blocked us."""
    alts = sc.alternatives_for("resérvame una noche en un hotel", "", "es")
    assert alts[0][0] == "Booking.com"


def test_an_errand_with_no_category_gets_NOTHING_rather_than_a_guess():
    """Empty is a legitimate answer. Inventing a site is the guessing this exists to stop, and the caller still
    says «try another site» without naming one — no worse than before, and honest about what we know."""
    assert sc.alternatives_for("móntame un widget para mis entrenamientos", "", "es") == []


def test_every_locale_offers_the_same_categories_an_alternative():
    """The catalog is kept symmetric on purpose (a category present in one locale and missing in the other fails
    silently, as this module's own comment says). Alternatives must not break that symmetry."""
    with_alts = {loc: {c for c, e in cats.items() if e.alts} for loc, cats in sc.SITE_CATALOG.items()}
    assert with_alts["es"] == with_alts["us"]


def test_no_alternative_points_at_its_own_trusted_site():
    """A list whose first «alternative» is the site that just failed is the bug wearing a different hat."""
    for cats in sc.SITE_CATALOG.values():
        for entry in cats.values():
            for _, url in entry.alts:
                assert url != entry.url


@pytest.mark.parametrize("goal,walled,expect_absent", [
    ("entradas de teatro en Madrid", "www.entradas.com", "entradas.com"),
    ("resérvame mesa esta noche en Casa Lucio", "www.thefork.es", "thefork"),
    ("resérvame una noche en un hotel en Burgos", "www.booking.com", "booking.com"),
])
def test_the_measured_categories_have_somewhere_to_go(goal, walled, expect_absent):
    alts = sc.alternatives_for(goal, walled, "es")
    assert alts, goal
    assert not any(expect_absent in u for _, u in alts)


def test_A_SHOPPING_ERRAND_GETS_NOTHING_and_that_is_a_KNOWN_LIMIT():
    """Not a gap in this fix — a consequence of a decision made elsewhere and written down there:
    `generic_marketplace` is deliberately NOT detected by `category_of` («the bare verb "compra" would sweep in
    ordinary chat»). No category means no alternative, so `cheapest-monitor` walling on a shop still gets the
    plain «try another site».

    Asserted rather than left implicit so that whoever DOES teach the catalog to recognise shopping (its own
    front, with its own measurement) finds out here that walls start naming alternatives for it too, instead of
    discovering it in a run."""
    assert sc.alternatives_for("búscame un monitor bueno para trabajar", "www.amazon.es", "es") == []


def test_the_bridge_prints_them_under_the_wall():
    """The half that makes it behaviour. A field annotated and not printed is a fix that dies one line short of
    its reader — the exact failure V2-186 was written for."""
    import contextlib
    import io

    from nucleo import nav_cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        nav_cli._print_state({"ok": True, "url": "https://www.booking.com/x", "title": "t",
                              "wall": "el sitio interpuso una verificación anti-robot",
                              "wall_alts": [{"name": "Trivago", "url": "https://www.trivago.es"}]})
    out = buf.getvalue()
    assert "⛔ MURO" in out and "Trivago" in out and "https://www.trivago.es" in out


def test_a_wall_with_no_alternative_still_prints_the_wall():
    """Sensitivity: the alternatives are an addition, never a precondition. A category with nothing written down
    must not silence the wall itself."""
    import contextlib
    import io

    from nucleo import nav_cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        nav_cli._print_state({"ok": True, "url": "https://x.example/y", "title": "t",
                              "wall": "el sitio bloqueó el acceso (te tomó por un robot)"})
    out = buf.getvalue()
    assert "⛔ MURO" in out and "→ prueba en" not in out


# ── V2-352: a walled CAR errand now has somewhere to go (measured escape route) ─────────────────────────────
# coches.net serves a 403 bot-block to this browser (live probe 2026-08-27) and `car_classifieds` had no alts:
# the walled worker got «prueba otro sitio» without a name — round 14, 7 navigations, 0 rows. Both
# alternatives are MEASURED delivering rows with listing urls (AutoScout24 in round 11 / V2-347; Wallapop
# since V2-324).


def test_a_walled_car_errand_is_sent_to_a_measured_alternative():
    from nucleo.flash import site_catalog as sc
    alts = sc.alternatives_for("busca un coche de segunda mano diésel por menos de 12.000", "coches.net", "es")
    names = [n for n, _ in alts]
    assert "AutoScout24" in names and "Wallapop" in names, alts
    assert not any("coches.net" in u for _, u in alts), alts


def test_and_the_trusted_site_is_offered_back_when_the_wall_came_from_elsewhere():
    from nucleo.flash import site_catalog as sc
    alts = sc.alternatives_for("busca un coche de segunda mano diésel", "autoscout24.es", "es")
    assert any("coches.net" in u for _, u in alts), alts
