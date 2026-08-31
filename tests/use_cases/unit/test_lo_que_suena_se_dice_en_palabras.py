"""V2-395 — what is PLAYING is told to the judge in WORDS.

V2-392 added `widgets_producing` to the mechanism report, and it stayed there. The section that translates the
mechanism into words —the one that does name `widget_ops`, durable triggers, and the audit— did not mention it,
so the data traveled in the raw JSON and the judge did not see it stated. That is the lesson of V2-346:
“an EMPTY list says nothing out loud.”

Measured in `play-music-and-build-playlist` (2026-08-27 14:31), with the music genuinely PLAYING —checked by
hand against the set: `yt.videoId = 0iLF_rtUbq0`, `paused: false`— and the verdict at **2/5**: “neither did the
music play nor was the song saved; there was only an empty promise in the transcript.”

And the part that explains it: the judge cited **`n_evidence: 0`** as evidence. EVIDENCE is, by definition, what
comes from the OUTSIDE WORLD, and a local player brings nothing from outside — so in a music or video case that
counter is ZERO BY CONSTRUCTION. A reader who looks where something is not does not fail: it ANSWERS, and it
answers with an absence, which is the most credible and most damaging answer.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import judge as J


def _palabras(mech: dict) -> str:
    return J.mechanism_facts(mech)


def test_si_algo_SUENA_se_dice_y_se_nombra():
    txt = _palabras({"widgets_producing": ["musica"]})
    assert "musica" in txt
    assert "SONANDO" in txt or "REPRODUCIENDO" in txt


def test_que_NO_suene_nada_tambien_se_dice():
    """The other direction: silence in the report is read as “we did not look,” not as “it was not playing.”"""
    txt = _palabras({"widgets_producing": []})
    assert "NADA" in txt and "sonando" in txt


def test_no_haber_podido_PREGUNTAR_no_es_lo_mismo_que_no_sonar():
    """Name the gap (V2-127/V2-133): without the field, the absence of playback is NOT proven.

    ⚠️ The input is NOT `{}` — a completely empty report has had its own honest output from the beginning (“the
    verification could not be performed”). The real case is a report that DOES exist and does not contain this
    field: a PARKED round judged later, built by code predating V2-392.
    """
    txt = _palabras({"families_observed": ["flash"]})
    assert "NO se pudo preguntar" in txt
    assert "no está probada" in txt


def test_se_le_AVISA_de_que_la_evidencia_no_mide_esto():
    """The verdict’s specific error: `n_evidence: 0` cited as proof that it did not play."""
    txt = _palabras({"widgets_producing": ["musica"]})
    assert "n_evidence" in txt and "NORMAL" in txt


def test_los_tres_casos_son_DISTINTOS_entre_si():
    """If two of the three said the same thing, the judge could not distinguish them — and distinguishing them is the whole point."""
    a = _palabras({"widgets_producing": ["musica"]})
    b = _palabras({"widgets_producing": []})
    c = _palabras({"families_observed": ["flash"]})
    assert len({a, b, c}) == 3


def test_lo_que_ya_decia_sigue_diciendose():
    """The section has more tenants: splitting it is how a rule gets lost along the way."""
    txt = _palabras({"widget_ops": {"agenda": {"data": 1}}, "widgets_producing": []})
    assert "agenda" in txt and "Operaciones de WIDGET" in txt
