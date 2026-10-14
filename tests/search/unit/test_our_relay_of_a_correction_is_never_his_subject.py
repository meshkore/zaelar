"""A correction in the MODEL's words reaches the sheet as context, never as his ask: its names are no subject (node 2.631).

hotel-under-15-days ES (2026-10-14, sandbox 023118-es). His «no hostales ni albergues» was relayed to the worker as
«DESCARTAR todos los albergues, hostales y pensiones encontrados hasta ahora (Hostel Trotamundos, bambu hostel
capsules, Arc House…)», and `dispatch.inject` appended that to the sheet's `asked`. The capitalised names became
SUBJECTS every row had to name, so «AC Hotel Sevilla Fórum by Marriott», «Bellavista Sevilla», «Exe Isla Cartuja»,
«Hotel San Gil» — real four-star hotels inside his criteria — went to the Rejected tab «does not name «hostel
trotamundos»», twice, while the hostels he ruled out stayed and were offered. search-buy-guitar ES (sandbox
015003-es): a folded escalation's «(Wallapop, Milanuncios y similares)» rejected eight guitars the same way.
"""
from __future__ import annotations

import asyncio
import inspect

from widgets.results import category_gate
from widgets.results import data as sheet

HOTEL_ASK = ("Sevilla, o cerca, lo que encuentres bien. Entramos el miércoles 21 de octubre y salimos el domingo 25, "
             "cuatro noches.")
RELAY = ("DESCARTAR todos los albergues, hostales y pensiones encontrados hasta ahora (Hostel Trotamundos, bambu hostel "
         "capsules, Arc House Sevilla Only Adults, The Nomad Hostel&Pension). Filtra SOLO hoteles de 4 estrellas.")
HOTELS = [{"title": "AC Hotel Sevilla Fórum by Marriott", "price": "763 € total"},
          {"title": "Bellavista Sevilla", "price": "779 € total"},
          {"title": "Exe Isla Cartuja", "price": "1.003 € total"},
          {"title": "Hotel San Gil", "price": "1.088 € total"}]
GUITAR_ASK = "Encuéntrame una guitarra acústica de segunda mano para empezar, por menos de 150€."
GUITAR_RELAY = ("Buscar guitarras acústicas de segunda mano, para principiante, con precio máximo de 150 euros. Buscar "
                "anuncios reales en mercados de segunda mano (Wallapop, Milanuncios y similares), recopilando los "
                "mejores candidatos disponibles con precio, estado y enlace.")
GUITARS = [{"title": "FENDER FA-100 Salón Guitarra Acústica", "price": "95 €"},
           {"title": "Guitarra acústica Columbus", "price": "60 €"},
           {"title": "Guitarra Antigua Höfner Vintage", "price": "140 €"}]


def _seed(sid: str, ask: str, title: str) -> None:
    sheet.store.save(sheet.sheet_key(sid), {"title": title, "asked": ask, "items": []})


def test_the_measured_relay_leaves_the_four_star_hotels_on_the_sheet():
    _seed("t2631a", HOTEL_ASK, "Hoteles 4 estrellas en Sevilla · 21-25 oct 2026")
    category_gate.recheck("t2631a", RELAY, relayed=True)
    sheet.apply_action("present", {"sheet": "t2631a", "items": HOTELS})
    assert len(sheet.view_data("t2631a")["items"]) == 4, sheet.view_data("t2631a").get("rejected")
    assert category_gate.asked_of("t2631a") == HOTEL_ASK, "our relay never joins his ask"


def test_the_folded_escalation_leaves_the_guitars():
    _seed("t2631b", GUITAR_ASK, "Guitarra acústica de segunda mano · hasta 150 €")
    category_gate.recheck("t2631b", GUITAR_RELAY, relayed=True)
    sheet.apply_action("append", {"sheet": "t2631b", "items": GUITARS})
    assert len(sheet.view_data("t2631b")["items"]) == 3, sheet.view_data("t2631b").get("rejected")


def test_what_the_relay_rules_out_still_reaches_the_door():
    _seed("t2631c", "busco un coche de segunda mano", "Coches de segunda mano")
    category_gate.recheck("t2631c", "nada de maquetas ni recambios, solo coches", relayed=True)
    sheet.apply_action("append", {"sheet": "t2631c", "items": [{"title": "Maqueta Seat 600", "price": "35 €"},
                                                                {"title": "Seat Ibiza 1.4 TDI 2015", "price": "7.750 €"}]})
    assert [i["title"] for i in sheet.view_data("t2631c")["items"]] == ["Seat Ibiza 1.4 TDI 2015"]


def test_a_present_keeps_the_relayed_context():
    _seed("t2631d", "busco un coche de segunda mano", "Coches de segunda mano")
    category_gate.recheck("t2631d", "nada de maquetas", relayed=True)
    sheet.apply_action("present", {"sheet": "t2631d", "items": [{"title": "Maqueta Seat 600", "price": "35 €"}]})
    assert sheet.view_data("t2631d")["items"] == []


def test_the_injection_relays_never_asks():
    from nucleo import dispatch
    src = inspect.getsource(dispatch.inject)
    assert "relayed=True" in src
    assert asyncio.iscoroutinefunction(dispatch.inject)
