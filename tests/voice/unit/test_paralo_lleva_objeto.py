"""V2-393 — «páralo» habla de una COSA, y el barge-in se lo comía.

Un stop duro salta el gate de atención y **no genera respuesta**: es para callar a zaelar cuando está hablando
encima. El clítico entró en esa regla a propósito, con este razonamiento escrito: «con pronombre pegado ya NO es
la preposición para, así que es inequívoco». Cierto — y confunde *inequívoco COMO VERBO* con *inequívoco SOBRE
QUÉ*.

Medido en `watch-a-video-not-listen-to-it` (2026-08-27 14:04), que había pasado **5/5 dos horas antes**:

    tester  Pon el vídeo del tráiler de la última de Dune.
    zaelar  Ya lo tienes en pantalla: «Dune: Parte Tres | Tráiler Oficial».
    tester  Vale, se ve bien. Bájale un poco el volumen, porfa.
    zaelar  Hecho.
    tester  Ahora páralo, porfa.
    zaelar  Perdona, ¿me lo repites?

El turno entero desapareció. Y la prueba de que la orden era clara la dio el propio tester: la repitió con otras
palabras —«Que pares el vídeo, porfa»— y funcionó **a la primera**. El guarda era nuestro.

La regla que queda: un barge-in **no tiene objeto**, es callar. El reflexivo/dativo («párate», «detente») habla
de zaelar; el acusativo de tercera («páralo», «detenla») lleva objeto directo, o sea que va sobre una cosa — y
eso lo resuelve el router, que para eso tiene las data-ops del widget.
"""
from __future__ import annotations

import pytest

from voice import attention as A


# ── lo que va sobre una COSA ya NO calla el turno ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("frase", [
    "Ahora páralo, porfa",          # la frase REAL de la ronda
    "páralo",
    "párala",
    "páralos",
    "detenlo",
    "detenla",
])
def test_el_acusativo_lleva_OBJETO_y_no_es_un_barge_in(frase):
    assert A.hard_interrupt(frase) is None, "lleva objeto directo: es una orden sobre una cosa, no callarse"


# ── y lo que va sobre ZAELAR sigue callándolo ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("frase", [
    "para",                          # la preposición ambigua, resuelta por la regla BLANDA (turno corto)
    "párate",                        # reflexivo → es él
    "detente",
    "páreme",                        # dativo → es a mí a quien deja de hablar
    "cállate",
    "basta",
    "silencio",
    "para ya",
])
def test_lo_que_habla_de_ZAELAR_sigue_siendo_un_stop_duro(frase):
    assert A.hard_interrupt(frase) == "stop", "la otra dirección: sin esto, arreglar el vídeo deja al operador " \
                                              "sin poder callar al agente"


def test_pararlo_TODO_sigue_siendo_global():
    """«todo» no es una cosa concreta: ahí el objeto no acota, abarca."""
    assert A.hard_interrupt("páralo todo") == "stop"
    assert A.hard_interrupt("páralas todas") == "stop"


def test_cerrar_TODO_no_se_toca():
    """La otra mitad de la función, que este cambio no roza."""
    assert A.hard_interrupt("cierra todo") == "close"


# ── lo que este arreglo NO cierra, dicho en vez de descubierto ─────────────────────────────────────────────

def test_PREEXISTENTE_una_preposicion_en_turno_corto_sigue_callando_el_turno():
    """`_STOP_SOFT_RE` + «≤4 palabras» dispara con «para la cena» (3 palabras) — y su propio comentario dice que
    existe para evitarlo. Comprobado contra el código ANTERIOR a este cambio: ya era así, no lo introduce esto.

    No se toca aquí porque es OTRA regla (la blanda, la de la preposición ambigua) y su arreglo es mover un
    umbral que protege el barge-in de verdad: pide su propia medida, no ir de paso.
    """
    assert A.hard_interrupt("para la cena") == "stop"


def test_PREEXISTENTE_el_imperativo_plural_nunca_estuvo_en_la_lista():
    """«parad»/«paradme» no está entre los verbos del patrón, ni antes ni ahora. Hueco conocido, no regresión."""
    assert A.hard_interrupt("paradme") is None
