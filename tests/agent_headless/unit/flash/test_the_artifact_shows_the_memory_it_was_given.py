"""El artefacto del turno tiene que enseñar la MEMORIA que se le enseñó al modelo (V2-255).

Sale de una propuesta del arnés para el problema que V2-254 dejó abierto —nada impide una CUARTA copia de la
regla de las píldoras de fondo—: **no vigiles a los ESCRITORES, vigila el ARTEFACTO.** Una lista de superficies
se ha demostrado incompleta tres veces porque hay que acordarse de ampliarla; pero todas, conocidas y por
conocer, terminan en el mismo sitio: un prompt que sale hacia un modelo. Y eso ya lo grabamos
(`observer.turn_detail`, que es **el único punto que cierran los DOS canales**, voz y probe).

La propiedad, dicha sobre la salida: *ningún prompt que se manda a un modelo contiene el texto de una píldora de
slot con namespace, salvo que la petición la nombre.*

Para que esa propiedad sea comprobable, el artefacto tiene que CONTENER la parte que se comprueba. Y no la
contenía. Medido el 2026-08-21 con la sesión vacía: el bloque de recall cae en el carácter **2.896** de un
prompt de 16.585, a 104 caracteres de la cabeza de 3.000 — y en un turno real van DELANTE el estado cacheado y
la conversación reciente, así que se cae SIEMPRE.

Un verificador leyendo ese artefacto diría «limpio» sobre un prompt sucio. Es la regla de esta misma noche
aplicada al registro: **un techo solo es peligroso si el lector acepta prefijos**.
"""
import pytest

from nucleo.flash import prompt as fp
from voice import observer as ob

MARCA = "PILDORA_DE_FONDO_MARCADOR"
RECALL = f"Puede que venga a cuento (de tu memoria):\n· {MARCA}"


# El ESTADO compartido se lee de la BASE, así que sin control el prompt mide una cosa distinta en cada máquina
# —y en la corrida completa del mapa, otra suite puede dejar apuntando una base con memoria de verdad—. Este
# caso mide el RECORTE, no cuánta memoria tenga quien lo corra: con el estado suelto salía verde en solitario y
# rojo en el mapa entero (2026-08-29), que es la forma exacta de un test que mide su entorno.
_ESTADO = ("── QUIÉN ERES ──\nEres zaelar.\n\n── QUIÉN TIENES DELANTE ──\nEl operador se llama Marc.")


def _prompt(recent: str = "", estado: str = _ESTADO) -> str:
    import unittest.mock as _mock
    from nucleo.flash import memory_cache
    with _mock.patch.object(memory_cache, "get", lambda: (estado, "Marc")):
        s, _ = fp.build_flash_system(recall_block=RECALL, recent_block=recent)
    return s


# ── el caso medido ───────────────────────────────────────────────────────────────────────────────────────────

def test_la_memoria_ENSEÑADA_sobrevive_al_recorte_en_un_turno_real():
    """Un turno real lleva estado cacheado y conversación reciente por delante del recall."""
    largo = "CONVERSACIÓN RECIENTE:\n" + ("· una línea de charla previa\n" * 60)
    assert MARCA in ob._prompt_excerpt(_prompt(largo)), \
        "el registro se comía justo la parte que decide conductas como la de V2-254"


def test_y_tambien_con_la_sesion_vacia():
    assert MARCA in ob._prompt_excerpt(_prompt())


# ── la otra dirección: sigue siendo un RECORTE, y dice cuánto se dejó fuera ──────────────────────────────────

def test_un_prompt_largo_SIGUE_recortandose():
    """Sensibilidad: «que quepa la memoria» no puede convertirse en guardar el prompt entero — este registro se
    persiste en cada turno."""
    enorme = "x" * 40000
    out = ob._prompt_excerpt(enorme)
    assert len(out) < len(enorme)


def test_y_el_hueco_se_NOMBRA_para_que_nadie_lo_lea_como_ausencia():
    """Es lo que permite a un verificador decir «no puedo certificar» en vez de «limpio» — la distinción
    INFRA/FAIL que el arnés ya usa. Sin esto, la propuesta de vigilar el artefacto miente en silencio."""
    out = ob._prompt_excerpt("x" * 40000)
    assert "OMITIDOS" in out and "caracteres" in out


def test_lo_que_cabe_entero_no_se_toca():
    assert ob._prompt_excerpt("corto") == "corto"


# ── el artefacto es el punto donde se juntan los dos canales ─────────────────────────────────────────────────

def test_turn_detail_es_el_UNICO_punto_que_cierran_los_dos_canales():
    """GUARDA DE FUENTE: si alguien le da a un canal su propia captura, la propuesta de vigilar el artefacto se
    queda sin artefacto único y volvemos a una lista de sitios que actualizar."""
    import inspect
    src = inspect.getsource(ob.turn_detail)
    assert "turn.completed" in src, "el bus es lo que permite consumirlo sin acoplarse a ningún canal"
    assert "system_prompt" in src and "_prompt_excerpt" in src


@pytest.mark.parametrize("cabeza,cola", [(ob._HEAD_CHARS, ob._TAIL_CHARS)])
def test_la_cola_sigue_cubriendo_el_estado_vivo(cabeza, cola):
    """El estado vivo («AHORA MISMO») va al FINAL y es lo que cambia cada turno — V2-195 lo puso ahí por un
    diagnóstico que casi sale mal. Ensanchar la cabeza no puede haberle comido la cola."""
    s = _prompt()
    ex = ob._prompt_excerpt(s + "y" * 20000)
    assert cola >= 7000
    assert ex.endswith("y" * 100)


# ── el margen, dicho como NÚMERO ─────────────────────────────────────────────────────────────────────────────
# El caso de arriba pasa o falla según cuánto ocupe lo que va DELANTE del recall, y eso crece solo: cada bloque
# nuevo del estado (V2-490 añadió uno) empuja la memoria hacia el centro recortado. Un booleano no avisa de que
# el margen se está agotando — avisa cuando ya se agotó, y entonces el artefacto lleva tiempo mintiendo.

def test_el_MARGEN_hasta_el_recorte_se_mide_y_no_se_agota():
    """Sensibilidad de la de arriba: no basta con que HOY quepa."""
    s = _prompt("CONVERSACIÓN RECIENTE:\n" + ("· una línea de charla previa\n" * 60))
    pos = s.find(MARCA)
    assert pos >= 0
    margen = ob._HEAD_CHARS - pos
    assert margen > 400, (
        f"la memoria enseñada queda a {margen} caracteres de caerse del artefacto. No ha fallado todavía, y por "
        f"eso hay que mirarlo ahora: cuando falle, un verificador dirá «limpio» sobre un prompt sucio.")


def test_un_ESTADO_grande_empuja_la_memoria_fuera_y_hay_que_saberlo():
    """La otra dirección, y es la que ocurre en producción: un operador con mucha memoria durable tiene un
    bloque de estado largo. Esto NO afirma que hoy pase — afirma que el recorte es por POSICIÓN, así que el
    riesgo existe y no depende de nada que se pueda arreglar con un techo más alto."""
    enorme = _ESTADO + "\n" + ("· un hecho durable más sobre la persona\n" * 300)
    s = _prompt(estado=enorme)
    assert MARCA in s, "el bloque de recall ya no viaja en el prompt: esto sería otro fallo"
    assert MARCA not in ob._prompt_excerpt(s), (
        "si esto pasa a ser verde, el recorte ha dejado de ser por posición y este aviso sobra")
