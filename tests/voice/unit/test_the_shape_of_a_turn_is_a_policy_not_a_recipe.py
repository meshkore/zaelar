"""V2-713 R5 · La FORMA del turno es una política del operador, no una receta escrita en el prompt.

## Qué decía la auditoría y qué se ha hecho con ello

`nucleo/flash/prompt.py:277-287` conservaba «Respondes SIEMPRE al instante en 1-2 frases habladas […] UNA
ACCIÓN por turno». `principles.md` nombra esa clase sin ambigüedad — *«Rail on JUDGEMENT — a LIMIT, remove
it»*, con ejemplos que son literalmente de esta forma — y desde V2-633 hay dónde ponerla: `genesis.json`
como defecto de fábrica, `<workspace>/config/style.json` como lo que el operador diga, leído por uso.

No se ha vaciado el bloque `ops` entero: se han movido las DOS que ya tenían forma de política. Las demás
irán cuando cada una tenga la suya, no antes.

## La contabilidad honesta, dicha y no redondeada

Mover las dos frases quitó **110 bytes** de `prompt.py` y añadió **198** en `shape_line()`: lo que el modelo
lee **creció 88 bytes**. No se vende como una reducción. Lo que compra es que dos constantes que fijaba quien
estuviera trabajando ese día son ahora dato que él cambia hablando.

Y al contarlas apareció una tercera fuente que el trinquete de prosa no veía: los **402 bytes** de
`prompt_line()` viajan en cada turno desde V2-633 sin haber aparecido nunca en ningún número.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from nucleo import style_policy as sp

ENGINE = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Workspace de usar y tirar: el fichero de override nunca puede ser el real del operador."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    sp._reset_for_tests()
    yield
    sp._reset_for_tests()


# ── 1 · los defaults son los que ya se comportaban así ──────────────────────────────────────────────────

def test_de_fabrica_el_turno_se_comporta_exactamente_como_antes():
    """Mover una preferencia no puede cambiar lo que hace el sistema el primer día."""
    assert sp.max_sentences() == 2
    assert sp.one_action_per_turn() is True
    linea = sp.shape_line()
    assert "2 frases" in linea and "UNA ACCIÓN por turno" in linea


def test_los_defaults_viven_en_el_GENESIS_que_es_dato_commiteado():
    g = json.loads((ENGINE / "nucleo" / "genesis.json").read_text(encoding="utf-8"))["style"]
    assert g["max_sentences"] == 2 and g["one_action_per_turn"] is True


def test_la_frase_ya_NO_esta_en_el_prompt():
    src = (ENGINE / "nucleo" / "flash" / "prompt.py").read_text(encoding="utf-8")
    assert "en 1-2 frases habladas" not in src
    assert "UNA \"\n        \"ACCIÓN por turno" not in src


def test_lo_que_SI_es_del_medio_se_queda_en_el_prompt():
    """El contrapeso, y la línea que separa una preferencia de un mecanismo: la voz no puede leer markdown ni
    emojis, y quedarse mudo rompe el turno. Eso no es gusto del operador, es cómo funciona el canal."""
    src = (ENGINE / "nucleo" / "flash" / "prompt.py").read_text(encoding="utf-8")
    assert "sin markdown, emojis ni símbolos que leer" in src
    assert "nunca te quedas mudo" in src


# ── 2 · es una política: él la cambia y el turno siguiente la obedece ────────────────────────────────────

def test_subir_el_limite_de_frases_cambia_la_linea():
    sp._write_overrides({"max_sentences": 5})
    assert sp.max_sentences() == 5
    assert "5 frases" in sp.shape_line()


def test_quitar_el_limite_RETIRA_media_frase_en_vez_de_contradecirla():
    """La diferencia de verdad entre una política y una receta: apagada, desaparece. Una frase en el prompt
    se paga aunque el operador no la quiera, y además contradice a la política que dice lo contrario — que
    es el defecto V2-222 («el prompt se contradecía y el turno elegía la mitad cierta»)."""
    sp._write_overrides({"max_sentences": 0})
    linea = sp.shape_line()
    assert "frases" not in linea and "UNA ACCIÓN por turno" in linea


def test_con_las_dos_apagadas_no_queda_ni_una_palabra():
    sp._write_overrides({"max_sentences": 0, "one_action_per_turn": False})
    assert sp.shape_line() == ""


def test_una_sola_frase_se_dice_en_SINGULAR():
    """Detalle pequeño y de los que delatan una plantilla: «en 1 frases» se lee como una máquina."""
    sp._write_overrides({"max_sentences": 1})
    linea = sp.shape_line()
    assert "1 frase hablada " in linea, f"el plural no acompaña al sustantivo: {linea!r}"
    assert "habladas" not in linea


def test_un_valor_roto_cae_al_defecto_en_vez_de_tumbar_el_turno():
    sp._write_overrides({"max_sentences": "muchas"})
    assert sp.max_sentences() == 2


# ── 3 · llega al turno de verdad ────────────────────────────────────────────────────────────────────────

def test_la_linea_compuesta_viaja_con_las_lineas_del_turno():
    """Si no se engancha, esto es un módulo que se ejecuta y se tira — la clase que V2-711 fue a buscar."""
    from nucleo.flash import style_directive as sd
    lineas = sd.prompt_lines({})
    assert any("UNA ACCIÓN por turno" in l for l in lineas)


def test_apagarla_la_retira_TAMBIEN_del_turno():
    from nucleo.flash import style_directive as sd
    sp._write_overrides({"max_sentences": 0, "one_action_per_turn": False})
    assert not any("UNA ACCIÓN por turno" in l for l in sd.prompt_lines({}))


# ── 4 · lo que NO se hizo, afirmado ─────────────────────────────────────────────────────────────────────

def test_el_bloque_ops_NO_se_ha_vaciado_de_golpe():
    """Las otras frases siguen ahí y eso es deliberado: cada una sale cuando tenga su política, no antes.
    Un vaciado en una tanda cambiaría treinta comportamientos medidos a la vez y sin forma de atribuir nada."""
    src = (ENGINE / "nucleo" / "flash" / "prompt.py").read_text(encoding="utf-8")
    assert "CÓMO OPERAS" in src
    assert "te disculpes en bucle" in src, "esta aún no tiene política; sigue siendo prosa, y se dice"
