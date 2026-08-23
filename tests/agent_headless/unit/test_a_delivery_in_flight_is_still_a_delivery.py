"""Una entrega YA HECHA no deja de serlo porque la tarea siga corriendo (V2-222, segunda cara).

Medido en la ronda 7 de `cheapest-monitor` (2026-08-23). El worker escribió tres candidatos —Dell, LG y
MSI— en la hoja del encargo y reportó el paso

    «Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)»

y durante CINCO turnos el agente contestó «sigo pendiente», «sigo con ello», «en cuanto tenga algo te lo
pongo delante». El juez lo fichó como [alta]: «los resultados YA estaban disponibles cuando zaelar dijo
sigo pendiente». Pero el prompt no le daba otra salida, y por DOS caminos que se suman:

1. La nota se recortaba a 60 caracteres justos, partiendo la palabra: lo que llegaba era «…hoja de
   resultados con lo». Se cortaba exactamente donde decía que HABÍA resultados y cuántos. Un recorte que
   acaba limpio se lee como una frase entera, así que el modelo no tenía ni la pista de que faltaba algo.
2. El bloque tenía una prohibición («NO … digas que ya está») y una instrucción para el caso VACÍO
   («TODAVÍA NO LO SABES»), y NADA para el de en medio: algo ya entregado con el encargo todavía en curso.
   Sin una rama que lo autorizara, el modelo resolvió la colisión por el único lado que el bloque permitía.

Es la misma lección que `dispatch.recently_ended_sessions` dejó escrita para la primera cara: no era
desobediencia, era una contradicción — y ninguna redacción de una sola de las dos mitades la arregla.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.flash import prompt as P

_NOTA = "Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)"


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()


def _viva(note: str = _NOTA):
    r = dispatch.SessionRecord(task_id="w1", goal="Buscar un monitor bueno para trabajar", kind="generic")
    r.status = "running"
    r.note = note
    dispatch._SESSIONS["w1"] = r
    return r


# ── 1. la nota llega ENTERA ────────────────────────────────────────────────────────────────────────────
def test_la_nota_medida_llega_entera_al_prompt():
    _viva()
    assert "los 3 finalistas" in P.live_state(), "el prompt sigue sin decir que hay resultados"


def test_y_ese_era_el_agujero_el_recorte_viejo_se_comia_justo_esa_parte():
    """La sensibilidad del test de arriba: con el corte de 60 la frase moría en «con lo»."""
    assert _NOTA[:60] == "Comparativa entregada en pantalla (hoja de resultados con lo"
    assert "finalistas" not in _NOTA[:60]


def test_una_nota_larga_se_corta_por_PALABRA_y_lo_dice():
    largo = "Comparativa entregada en pantalla " + "con muchisimos detalles adicionales " * 6
    out = P._short_note(largo)
    assert out.endswith("…"), "un recorte que acaba limpio se lee como una frase entera"
    assert not out.rstrip("…").endswith(" ")
    # No parte una palabra por la mitad: el último trozo antes de los puntos es una palabra del original.
    assert out.rstrip("…").split()[-1] in largo.split()


def test_una_nota_corta_no_se_toca():
    assert P._short_note("Comparativa entregada") == "Comparativa entregada"
    assert not P._short_note("Comparativa entregada").endswith("…")


# ── 2. el bloque AUTORIZA contarlo ─────────────────────────────────────────────────────────────────────
def test_el_bloque_dice_que_una_entrega_en_curso_SE_CUENTA():
    _viva()
    st = P.live_state()
    low = st.lower()
    # La ORDEN, no una palabra suelta. La primera versión de este test buscaba «ya está entregado» y era
    # verde por el motivo equivocado: esa misma frase vuelve a salir en la cláusula que cierra la rama
    # («no lo que ya está entregado»), así que quitar la rama entera no ponía rojo nada. Lo cazó el desarme.
    assert "cuéntalo en este turno" in low, "el bloque no MANDA contarlo: describir el hecho no es una orden"
    assert "qué falta" in low, "sin «di qué falta» la rama invita al fallo contrario: darlo por acabado"
    # Y va DENTRO del imperativo del caso vacío, no en una frase suelta: dos órdenes en un párrafo salen a
    # cara o cruz, así que tiene que MATIZAR al «TODAVÍA NO LO SABES» y por tanto ir detrás.
    i_vacio, i_rama = low.find("todavía no lo sabes"), low.find("pero lee el paso")
    assert i_vacio != -1 and i_rama != -1
    assert i_rama > i_vacio, "la rama no matiza al imperativo que la necesita: queda como orden suelta"


def test_y_prohibe_explicitamente_el_sigo_con_ello_de_la_ronda_7():
    _viva()
    assert "sigo con ello" in P.live_state().lower()


def test_la_prohibicion_de_decir_que_ACABO_sigue_en_pie():
    """La rama nueva no puede abrir la puerta al fallo contrario: entregar algo no es haber terminado."""
    _viva()
    st = P.live_state()
    assert "NO reinicies ni digas que ya está" in st
    assert "no lo que ya está entregado" in st.lower() or "sigue EN CURSO es la tarea" in st


def test_sin_ninguna_tarea_viva_no_hay_bloque_que_contradecir():
    """Un aviso que sale siempre es ruido; y aquí además hablaría de una tarea inexistente."""
    assert "TAREAS DE FONDO EN CURSO" not in P.live_state()


# ── 3. TERCERA cara: la hoja tiene 35 candidatos y este bloque decía «en cola» ─────────────────────────
# Medido en `search-secondhand-monitor__es` (2026-08-23 23:24), leyendo el system prompt de los turnos 4 y
# 5 ENTEROS. El bloque del NAVEGADOR decía, en el mismo prompt:
#
#     «… YA TIENE RESULTADOS. «Buscar un monitor de segunda mano…» YA TRAJO ALGO: no está bloqueada ni
#      esperando, tiene resultados en la hoja. DÁSELOS en este turno»
#
# y ESTE bloque, unas líneas más arriba:
#
#     «TAREAS DE FONDO EN CURSO (… NO reinicies ni digas que ya está): «Buscar un monitor…» — en cola
#      (llevas 23s) … la respuesta es que TODAVÍA NO LO SABES»
#
# Dos registros describiendo UN encargo y contradiciéndose. El turno contestó «te aviso en cuanto tenga
# resultados» dos veces, con 35 anuncios reales con nombre y precio en la hoja, y la ronda se puntuó como
# desobediencia [alta] ×3. No lo era: un prompt que se discute a sí mismo no tiene respuesta obediente.
#
# El dato existía y viajaba: `pending_summaries()` publica `kept` (lo que el worker reporta con
# `hbnote considered --kept N`) y es la MISMA señal que el bloque del navegador lee desde V2-200. Este
# bloque nunca la miraba, así que se quedaba con la fase — que el worker no había actualizado desde que la
# tarea entró en cola.


def _con_candidatos(kept: int = 35):
    r = dispatch.SessionRecord(task_id="w2", goal="Buscar un monitor de segunda mano de al menos 27 pulgadas",
                               kind="web")
    r.status = "running"
    r.phase = "en cola"          # la fase MEDIDA: el worker nunca la actualizó
    r.note = ""
    r.kept = kept
    dispatch._SESSIONS["w2"] = r
    return r


def test_los_candidatos_de_la_hoja_llegan_a_ESTE_bloque():
    _con_candidatos()
    st = P.live_state()
    assert "35 candidato" in st, "el bloque sigue sin decir que el worker ya encontró algo"


def test_y_ese_era_el_agujero_la_fase_por_si_sola_dice_lo_contrario():
    """Sensibilidad: sin `kept` el bloque solo tiene la fase, y la fase medida decía «en cola».

    Se casa contra la MARCA del encargo («están en la hoja») y no contra la palabra «candidato» a secas:
    esa palabra sale también en la instrucción permanente, así que el test pasaría igual con el hecho
    borrado — el mismo verde-por-el-motivo-equivocado que ya coló dos veces en este fichero.
    """
    _con_candidatos(kept=0)
    st = P.live_state()
    assert "están en la hoja" not in st, "un encargo SIN candidatos no puede anunciar ninguno"
    assert "en cola" in st


def test_la_rama_que_autoriza_contarlo_cubre_tambien_los_candidatos():
    """La nota entregada y los candidatos encontrados son el MISMO caso: algo ya traído con la tarea viva.

    Va en la rama que YA existe y no en una segunda orden: dos imperativos en un párrafo salen a cara o
    cruz (V2-224), que es exactamente lo que esta iniciativa lleva tres caras arreglando.
    """
    _con_candidatos()
    low = P.live_state().lower()
    assert "ya ha encontrado candidatos" in low, "la rama no nombra el caso que acaba de aparecer en el bloque"
    i_vacio, i_rama = low.find("todavía no lo sabes"), low.find("pero lee el paso")
    assert i_vacio != -1 and i_rama != -1 and i_rama > i_vacio


def test_el_texto_del_bloque_y_el_de_la_rama_usan_las_MISMAS_palabras():
    """Si el bloque dice «YA HA ENCONTRADO» y la rama nombra otra cosa, el modelo no puede casarlas.

    Es la lección de V2-221: sin la frase dentro, el modelo no tiene con qué contrastarse.
    """
    _con_candidatos()
    st = P.live_state()
    assert "YA HA ENCONTRADO" in st
    assert "YA HA ENCONTRADO candidatos" in st or "ya ha encontrado candidatos" in st.lower()


def test_no_pisa_la_nota_entregada_las_dos_caras_conviven():
    """Un encargo puede tener las dos cosas: un paso que dice qué entregó Y candidatos contados."""
    r = _con_candidatos()
    r.note = _NOTA
    st = P.live_state()
    assert "los 3 finalistas" in st
    assert "35 candidato" in st
