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


def _prompt(recent: str = "") -> str:
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
