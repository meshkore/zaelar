"""V2-395 — lo que está SONANDO se le dice al juez en PALABRAS.

V2-392 metió `widgets_producing` en el informe de mecanismo y ahí se quedó. La sección que traduce el
mecanismo a palabras —la que sí nombra `widget_ops`, los disparadores durables y la auditoría— no lo
mencionaba, así que el dato viajaba en el JSON crudo y el juez no lo veía enunciado. Es la lección de V2-346:
«una lista VACÍA no dice nada en voz alta».

Medido en `play-music-and-build-playlist` (2026-08-27 14:31), con la música SONANDO de verdad —comprobado a
mano contra el plató: `yt.videoId = 0iLF_rtUbq0`, `paused: false`— y el veredicto en **2/5**: «ni sonó la
música ni se guardó la canción, solo hubo una promesa vacía en el transcript».

Y la mitad que lo explica: el juez citó **`n_evidence: 0`** como prueba. La EVIDENCIA es, por definición, lo
que trae el MUNDO EXTERIOR, y un reproductor local no trae nada de fuera — así que en un caso de música o de
vídeo ese contador es CERO POR CONSTRUCCIÓN. Un lector que mira donde no está no falla: RESPONDE, y responde
una ausencia, que es la respuesta más creíble y más dañina.
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
    """La otra dirección: un silencio en el informe se lee como «no miramos», no como «no sonaba»."""
    txt = _palabras({"widgets_producing": []})
    assert "NADA" in txt and "sonando" in txt


def test_no_haber_podido_PREGUNTAR_no_es_lo_mismo_que_no_sonar():
    """Nombrar el hueco (V2-127/V2-133): sin el campo, la ausencia de reproducción NO está probada.

    ⚠️ La entrada NO es `{}` — un informe totalmente vacío tiene su propia salida honesta desde antes («la
    verificación no se pudo hacer»). El caso real es un informe que SÍ existe y no trae este campo: una ronda
    APARCADA que se juzga después, construida por código anterior a V2-392.
    """
    txt = _palabras({"families_observed": ["flash"]})
    assert "NO se pudo preguntar" in txt
    assert "no está probada" in txt


def test_se_le_AVISA_de_que_la_evidencia_no_mide_esto():
    """El error concreto del veredicto: `n_evidence: 0` citado como prueba de que no sonó."""
    txt = _palabras({"widgets_producing": ["musica"]})
    assert "n_evidence" in txt and "NORMAL" in txt


def test_los_tres_casos_son_DISTINTOS_entre_si():
    """Si dos de los tres dijeran lo mismo, el juez no podría separarlos — y separarlos es todo el punto."""
    a = _palabras({"widgets_producing": ["musica"]})
    b = _palabras({"widgets_producing": []})
    c = _palabras({"families_observed": ["flash"]})
    assert len({a, b, c}) == 3


def test_lo_que_ya_decia_sigue_diciendose():
    """La sección tiene más inquilinos: partirla es como se pierde una regla por el camino."""
    txt = _palabras({"widget_ops": {"agenda": {"data": 1}}, "widgets_producing": []})
    assert "agenda" in txt and "Operaciones de WIDGET" in txt
