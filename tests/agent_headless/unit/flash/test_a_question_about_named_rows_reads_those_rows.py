"""A question about rows he NAMES is answered from those rows, clause by clause — never the criteria block (node 2.606).

cheapest-monitor ES (2026-10-14, sandbox 010117-es, turn 4): «El portátil no me sirve, eso es para otra cosa. El curvo
de 27 me llama un poco, ¿sabes si es 4K o qué resolución tiene? Y el Blackview no me suena de nada, ¿tiene buenas
reseñas?» got «Blackview…: Precio dentro de un presupuesto…, sin verificar; Blackview…: Resolución mínima…; Blackview…:
Disponible para compra…; AOC Monitor para ju…» — every hard criterion of three rows. `row_check` matched his WHOLE
sentence against each criterion by any 4-letter stem («para», «otra», «cosa»), and «para» named the AOC row. He
answered «me has soltado el cuadro de criterios sin confirmar la resolución del Nilox ni las reseñas del Blackview».
"""
from __future__ import annotations

import pytest

from nucleo.flash import row_check

HARD = ["Precio dentro de un presupuesto contenido: orientativamente no superar 300 € por unidad, salvo que el "
        "operador confirme otra cosa", "Resolución mínima Full HD (1920x1080); idealmente superior",
        "Disponible para compra en el mercado del operador (asumido: España, webs con envío nacional)",
        "Tamaño de pantalla entre 24 y 32 pulgadas (uso de escritorio)"]
HEARD = ("El portátil no me sirve, eso es para otra cosa. El curvo de 27 me llama un poco, ¿sabes si es 4K o qué "
         "resolución tiene? Y el Blackview no me suena de nada, ¿tiene buenas reseñas?")


def _row(title, price, **facts):
    return {"title": title, "price": price,
            "facts": [{"label": h, "value": "?"} for h in HARD] + [{"label": k, "value": v} for k, v in facts.items()]}


def _sheet(*extra):
    return {"criteria": {"hard": list(HARD)}, "items": [
        _row('Blackview Table 10 23.8" FHD…', "159", **dict(extra)),
        _row("Extensor de pantalla portátil…", "290.09"),
        _row('Monitor 27" Curvo Dp Hdmi Nilox…', "190.97"),
        _row("AOC Monitor para juegos 24G2…", "149")]}


@pytest.fixture(autouse=True)
def spanish(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))


def test_each_named_row_is_read_for_what_its_clause_asks():
    out = row_check.line(HEARD, _sheet(), reply="Déjame mirar la ficha del Nilox y las reseñas del Blackview.")
    assert "Nilox" in out and "Resolución mínima" in out, out
    for dump in ("Precio dentro", "Disponible para compra", "Tamaño de pantalla", "AOC", "Extensor"):
        assert dump not in out, f"{dump!r} is the criteria block, not his question: {out}"


def test_a_row_the_reply_left_unsaid_is_said_not_verified():
    out = row_check.line(HEARD, _sheet(), reply="Lo miro ahora mismo.")
    assert "Blackview" in out and "no lo tengo verificado" in out, out
    assert "Precio dentro" not in out


def test_the_unverified_row_is_said_in_the_sessions_language(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    out = row_check.line("And the Blackview, does it have good reviews?", _sheet(), reply="On it.")
    assert "I don't have that verified yet" in out, out


def test_a_fact_the_worker_wrote_is_the_answer():
    heard = "Y el Blackview, ¿tiene buenas valoraciones?"
    out = row_check.line(heard, _sheet(("Valoración", "4,7 sobre 5 (16 opiniones, PcComponentes)")), reply="Vale.")
    assert "4,7 sobre 5" in out, out


def test_a_question_that_names_no_row_and_only_leads_on_the_sheet_owes_nothing():
    lead = {"title": 'Monitor Nilox NXM27CV28001 27"…', "facts": [{"label": "origen", "value": "búsqueda web"}]}
    data = {"criteria": {"hard": list(HARD)}, "items": [lead]}
    heard = ("Pues si el Nilox es Full HD no me vale, yo iba a por 4K. ¿Hay algo de 27 pulgadas 4K por debajo de 300? "
             "El Blackview al ser 23.8 y FHD tampoco me sirve.")
    assert row_check.line(heard, data, reply="Voy a mirarlo.") == ""


def test_a_clause_without_a_question_names_nothing_for_the_next_one():
    heard = "El curvo no me vale. ¿Hay algo de 27 pulgadas por debajo de 300?"
    out = row_check.line(heard, _sheet(), reply="Lo busco.")
    assert "Nilox" not in out, out
