"""A notice asked for about something to be FOUND OUT carries the answer, never the cut question (V2-781 pair 3).

`find-a-future-release-and-remind-me` (ES, 2026-10-10 21:20): «¿Te enteras de cuándo se estrena y me avisas?» →
the search said «Dexter: Resurrection… se estrena el 30 de octubre de 2026» → the prose backstop scheduled the
30th with the prompt «AVISA al operador…: Oye, me gusta mucho la serie Dexter… ¿Te enteras de cuándo se estrena».
On the 30th the agent would have been handed his question, cut mid-sentence, naming neither show nor date. And
the worker, which then verified the date and asked for the same instant with the fact, was answered by that job.
"""
from __future__ import annotations

import pytest

from nucleo.pulse import scheduler as S
from nucleo.flash import reminder_fact as F
from nucleo.flash import reminder_guards as R

NOW = 1791659532.0          # 2026-10-10 21:12, the run's own clock

ES_TURNS = [
    ("Oye, me gusta mucho la serie Dexter y creo que este otoño sacan temporada nueva. ¿Te enteras de cuándo se "
     "estrena y me avisas?",
     "¡Buena noticia! Dexter: Resurrection, con Michael C. Hall de nuevo, se estrena el 30 de octubre de 2026, así "
     "que sí, cae en otoño. Te aviso cuando se acerque la fecha."),
    ("¿El 30 de octubre? ¿De dónde lo sacaste? Compruébalo bien, y si de verdad es esa, déjame el aviso puesto "
     "para ese día, porfa.",
     "Tienes razón en desconfiar: esa fecha la di sin comprobarla, y no puedo dártela por buena. Déjame verificarlo."),
    ("Vale, gracias. Míralo bien y me dices, porfa.",
     "Voy a comprobarlo a fondo y te dejo el aviso solo cuando confirme la fecha oficial."),
]
ES_ASK = "Ah, perfecto. Pues déjame el aviso para el 30 de octubre y me recuerdas cuando llegue."
ES_REPLY = ("Ahora mismo no puedo dejarte ese aviso, porque todavía no he confirmado que el estreno sea de verdad el "
            "30 de octubre, y no quiero recordarte una fecha que no es. En cuanto lo compruebe, si sale esa, te lo "
            "programo para ese día.")


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(S.time, "time", lambda: NOW)


def _window(turns):
    out = []
    for u, a in turns:
        out += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    return out


@pytest.mark.parametrize("lang, clause, want", [
    ("es", "Oye, ¿te enteras de cuándo se estrena", "comprueba primero lo que te pidió averiguar y díselo: "
                                                     "«Oye, ¿te enteras de cuándo se estrena?»"),
    ("en", "Can you find out when the new Dexter season premieres and",
     "first check what he asked you to find out and tell him: «Can you find out when the new Dexter season "
     "premieres»"),
])
def test_without_an_answer_the_lookup_is_said_whole_in_his_language(monkeypatch, lang, clause, want):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    assert F.reminder_body(clause, [], "Te aviso el 30 de octubre.", "2026-10-30 09:00") == want


def test_a_refusal_or_a_question_is_not_the_fact():
    window = _window([("¿Te enteras de cuándo se estrena Dexter y me avisas?",
                       "No puedo confirmar que Dexter se estrene el 30 de octubre. ¿Seguro que Dexter sale el 30 de "
                       "octubre?")])
    assert F.fact_for("¿Te enteras de cuándo se estrena Dexter", window, "", "2026-10-30 09:00") == ""


def test_the_clause_cut_drops_a_conjunction_not_a_letter():
    assert R.commitment_clause("Tengo que llamar a mamá hoy, recuérdamelo") == "Tengo que llamar a mamá hoy"
    assert R.commitment_clause("Note the vet on Friday and remind me Thursday") == "Note the vet on Friday"
    assert R.commitment_clause("el jueves renuevo el seguro, y recuérdamelo el miércoles") == "el jueves renuevo el seguro"


def test_the_worker_fact_replaces_the_loose_notice_at_that_instant():
    loose = S.create("AVISA al operador, es el recordatorio que te pidió: ¿Te enteras de cuándo se estrena",
                     "2026-11-17 09:13", name="aviso")
    fact = "AVISA al operador: hoy se estrena Dexter: Resurrection T2 (Paramount+, 30 oct 2026)"
    again = S.create_unless_ringing(fact, "2026-11-17 09:13", "Dexter [worker:7]")
    assert again["id"] == loose["id"]
    jobs = [j for j in S.list_jobs() if j["schedule"] == "2026-11-17 09:13"]
    assert len(jobs) == 1 and jobs[0]["prompt"] == fact and jobs[0]["name"] == "aviso", jobs


def test_a_notice_he_named_is_not_rewritten():
    mine = S.create("Dile que hoy es el cumpleaños de Ana", "2026-11-18 09:13", name="cumple Ana")
    S.create_unless_ringing("otra cosa", "2026-11-18 09:13", "x [worker:7]")
    assert [j["prompt"] for j in S.list_jobs() if j["id"] == mine["id"]] == ["Dile que hoy es el cumpleaños de Ana"]
