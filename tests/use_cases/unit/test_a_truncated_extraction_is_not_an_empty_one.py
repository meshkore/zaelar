"""A browser extraction cut off mid-flight still counts as what the browser found.

Measured on 2026-08-20: the observer caps an event's text at 1500 characters, so an extraction with
several hits arrived as a valid JSON prefix and a severed tail. `json.loads` on the whole string raised,
the item list was dropped, and the report said the browser had found nothing but an ad for a flamenco
show — while the round had in fact surfaced «Bécquer, 100 €», the 4-star hotel the case is about, with a
live URL. The judge then graded a delivery that had happened as a delivery that had not. Same shape as
the truncated tool call of V2-171: salvage the complete objects, never drop the payload.
"""
from tests.use_cases.e2e.agent import verify

_TRUNCATED = (
    '[ { "title": "", "price": "73 €", "url": "https://www.google.com/travel/search?q=hoteles", '
    '"image": "" }, { "title": "Bécquer", "price": "100 €", "url": '
    '"https://www.google.com/travel/lodging/clk?pc=AA80Osxkarg", "image": "" }, { "title": "Sevilla '
    'Center", "price": "9')


def test_the_hotel_after_the_cut_point_is_still_found():
    items = verify._items_in(_TRUNCATED)
    titles = [i.get("title") for i in items]
    assert "Bécquer" in titles, titles


def test_the_severed_object_is_salvaged_alongside_the_complete_ones():
    """Two complete objects plus the one the cut landed in — the last is where the answer tends to be."""
    items = verify._items_in(_TRUNCATED)
    assert len(items) == 3
    assert items[-1]["title"] == "Sevilla Center" and items[-1]["partial"] is True


def test_a_complete_array_still_works():
    items = verify._items_in('[{"title": "Exe Sevilla Macarena", "price": "65 €"}]')
    assert [i["title"] for i in items] == ["Exe Sevilla Macarena"]


def test_a_brace_inside_a_string_does_not_confuse_the_scan():
    items = verify._items_in('[{"title": "Hotel {Centro}", "price": "80 €"}]')
    assert items and items[0]["title"] == "Hotel {Centro}"


def test_prose_before_the_array_is_not_a_reason_to_lose_it():
    items = verify._items_in('el navegador sacó esto: [{"title": "ibis Budget", "price": "45 €"}]')
    assert items and items[0]["title"] == "ibis Budget"


def test_no_objects_means_empty_not_an_exception():
    assert verify._items_in("") == [] and verify._items_in("sin resultados") == []


def test_the_cap_keeps_DISTINCT_titles_not_the_earliest_rows(tmp_path):
    """The junk arrives first and repeats; a cap on rows reports the noise and hides the answer."""
    import json as _json
    import sqlite3
    db = tmp_path / "sandbox.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, ts_ms INT, kind TEXT, label TEXT, payload TEXT)")
    ad = '[{"title": "Experiencia Premium en el Teatro Flamenco Sevilla", "price": "€ 25"}]'
    hotel = '[{"title": "Bécquer", "price": "100 €"}]'
    rows = [("observer", 1000 + i, "navegador", "\U0001f9ed resultados", _json.dumps({"text": ad}))
            for i in range(5)]
    rows.append(("observer", 2000, "navegador", "\U0001f9ed navegador ↩", _json.dumps({"text": hotel})))
    con.executemany("INSERT INTO events VALUES (?,?,?,?,?)", rows)
    con.commit()
    con.close()

    wo = verify.worker_outcome(str(db))
    titles = [f["title"] for f in wo["found"]]
    assert "Bécquer" in titles, titles
    assert titles.count("Experiencia Premium en el Teatro Flamenco Sevilla") == 1
    assert wo["n_found"] == 6          # every hit still counted, the list is just deduplicated


def test_the_object_the_cut_landed_in_is_salvaged_by_title_and_price():
    """The severed object is where the useful hit tends to be: junk first, answer last."""
    cut = ('[{"title": "", "price": "73 €", "url": "https://g/1"}, {"title": "Bécquer", "price": "100 €", '
           '"url": "https://www.google.com/travel/lodging/clk?pc=AA80OsxkargZK24wWZXsj6Cf-HXQXldqTN3R0BOIJ')
    items = verify._items_in(cut)
    becquer = [i for i in items if i.get("title") == "Bécquer"]
    assert becquer and becquer[0]["price"] == "100 €"
    assert becquer[0].get("partial") is True


def test_a_severed_object_with_no_title_yet_is_not_invented():
    items = verify._items_in('[{"title": "ibis", "price": "45 €"}, {"pri')
    assert [i["title"] for i in items] == ["ibis"]
