"""The note is not the extraction, and judging one as the other invents a defect.

Measured 2026-08-20 on `cheapest-monitor`: the browser scraped three real 99 EUR monitors, the note carried
`items[:3]` in DOM order — three category links with no name — and zaelar told the user the page only
returned categories. That was TRUE of what it received. The instrument called it "found and did not
deliver", which is a behavioural accusation against a turn that behaved correctly.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, notes: list[str]):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (ts_ms INTEGER, topic TEXT, kind TEXT, payload TEXT)")
    for i, text in enumerate(notes):
        con.execute("INSERT INTO events VALUES (?,?,?,?)",
                    (1000 + i, "observer", "brain", json.dumps({"text": text})))
    con.commit()
    con.close()
    return str(p)


_TAIL = ". Nadie más lo sabe: no está en la conversación hasta que tú lo digas."
_HEAD = "[SISTEMA] El navegador ha SACADO esto de la página, trabajando en «Busca monitores»: "


def test_the_note_that_carried_no_name_offers_nothing(tmp_path):
    """The real note from that round: three category links, not one product name."""
    note = _HEAD + ("799€ — https://www.pccomponentes.com/categorias/portatiles/basicos-hasta-799; "
                    "200€ — https://www.pccomponentes.com/categorias/smartphone-moviles/menos-de-200; "
                    "200€ — https://www.pccomponentes.com/categorias/tablets?LGHVTFUY7TMax=200") + _TAIL
    got = verify.offered_to_brain(_db(tmp_path, [note]))
    assert got["notes"] == 1
    named = [t for t in got["titles"] if t and not t[0].isdigit()]
    assert named == [], f"nothing in that note had a name, got {got['titles']}"


def test_a_note_with_names_offers_them(tmp_path):
    note = _HEAD + ("Monitor Alurin CoreVision 24\" FHD — 99€ — https://x/a; "
                    "PcCom Elysium 27\" Fast IPS — 99€ — https://x/b") + _TAIL
    got = verify.offered_to_brain(_db(tmp_path, [note]))
    assert got["n_offered"] == 2
    assert got["titles"][0].startswith("Monitor Alurin")


def test_delivery_is_judged_on_what_was_offered_not_what_was_scraped(tmp_path):
    """The turn cannot deliver a row it was never handed — so it is not scored for one."""
    note = _HEAD + "799€ — https://x/categorias/portatiles" + _TAIL
    offered = verify.offered_to_brain(_db(tmp_path, [note]))
    said = [{"who": "zaelar", "text": "la página solo me da categorías, no monitores"}]
    verdict = verify.was_delivered([{"title": t} for t in offered["titles"]], said)
    assert verdict is not True
    # And the row the browser DID scrape must not be what delivery is measured against.
    scraped = [{"title": "Monitor Alurin CoreVision 24\" FHD"}]
    assert verify.was_delivered(scraped, said) is False, "measuring against the scrape accuses the turn"


def test_the_instruction_prose_is_not_read_as_a_finding(tmp_path):
    """The note's tail says «dáselo como resultado con nombre, precio y enlace» — that is an order, not a row."""
    note = _HEAD + "Monitor X — 99€ — https://x/a" + _TAIL + (
        " NÓMBRALO EN ESTE TURNO y di si sirve: si responde a lo que pidió, dáselo como resultado con "
        "nombre, precio y enlace.")
    got = verify.offered_to_brain(_db(tmp_path, [note]))
    assert got["titles"] == ["Monitor X"], got["titles"]


def test_a_bare_number_is_not_a_name(tmp_path):
    """Measured 2026-08-21: the extractor split «169,00 €» across the two fields, so the note read
    «169 — 00 € — <url>». Counting that as a named finding reports three results where there were three
    price fragments, and hides the extractor defect behind a healthy count."""
    note = _HEAD + ("169 — 00 € — https://www.amazon.es/LG-27US500-W/dp/B0DH51BPZD; "
                    "284 — 87 € — https://www.amazon.es/Dell-Plus-Monitor/dp/B0F29RH4RY") + _TAIL
    got = verify.offered_to_brain(_db(tmp_path, [note]))
    assert got["n_offered"] == 2, "the rows were offered — that part is true"
    assert got["n_named"] == 0, f"but none of them carried a name: {got['named']}"


def test_and_a_real_name_still_counts(tmp_path):
    """Sensitivity: if everything were filtered out the test above would pass and mean nothing."""
    note = _HEAD + "Monitor Alurin CoreVision 24\" FHD — 99€ — https://x/a" + _TAIL
    got = verify.offered_to_brain(_db(tmp_path, [note]))
    assert got["n_named"] == 1 and got["named"][0].startswith("Monitor Alurin")
