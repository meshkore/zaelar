"""El veredicto no cabía, y el reintento le pedía justo lo que no cabe (V2-373).

`two-searches-two-sheets` perdió su veredicto CUATRO veces. Instrumentadas las tres llamadas de una de esas
pérdidas, con `max_tokens=2000`:

    intento 1 → 6558 chars, cortado a mitad de palabra
    intento 2 → 6368 chars, cortado a mitad de palabra
    intento 3 → 6487 chars, cortado a mitad de palabra

Y el veredicto COMPLETO de ese caso, medido subiendo el techo: **7238 chars**. No era mala suerte ni un JSON
descuidado — ese caso no cabía, así que **no podía juzgarse nunca**, y cada intento gastaba una llamada para
volver a no caber. Diez minutos y medio de navegador real a la basura, cada vez.

Dos correcciones, y la segunda importa tanto como la primera:

1. El techo. El comentario del bucle ya apuntaba a multiflow y le atribuía la causa equivocada —«más JSON
   donde equivocarse»—: no son más oportunidades de error, es más TAMAÑO (siete dimensiones en vez de cinco,
   cada una con su prosa).
2. **CORTADO no es INVÁLIDO.** El reintento decía «tu respuesta no era JSON válido, devuelve EXACTAMENTE el
   mismo veredicto» — a quien había escrito un JSON perfecto que nosotros truncamos. Le pedíamos que repitiera
   lo que no cabe, así que los tres intentos eran el mismo intento. Es la familia de V2-171: una respuesta
   cortada disfrazada de error de formato.
"""
import pytest

from tests.use_cases.e2e.agent import judge as J


# ── distinguir CORTADA de MAL FORMADA ──────────────────────────────────────────────────────────────────────

def test_los_tres_cortes_medidos_se_reconocen():
    """Los pares (chars, posición del fallo) de las pérdidas reales."""
    for total, pos in ((6487, 6451), (6750, 6688)):
        assert J._parecia_cortada("x" * total, f"Expecting ',' delimiter: line 84 column 6 (char {pos})")


def test_un_fallo_de_FORMA_no_se_confunde_con_un_corte():
    """La pérdida de las 09:36 falló en el char 1159 de un texto mucho más largo: eso es una coma o una
    comilla, y pedirle brevedad ahí sería mandarle recortar un veredicto que cabía perfectamente."""
    assert not J._parecia_cortada("x" * 6750, "Expecting ',' delimiter: line 22 column 6 (char 1159)")


def test_sin_posicion_en_el_error_no_se_adivina():
    assert not J._parecia_cortada("x" * 6750, "Expecting value")
    assert not J._parecia_cortada("x" * 6750, None)


def test_sin_respuesta_no_hay_corte_que_detectar():
    assert not J._parecia_cortada("", "Expecting ',' delimiter: line 1 column 1 (char 0)")


def test_NO_se_usa_termina_en_llave_y_esta_es_la_razon():
    """Fue el primer intento y es un falso negativo medido: una respuesta de 7238 chars que SÍ se parseaba
    bien daba False con ese criterio. Un guarda que se equivoca sobre el caso BUENO no sirve para decidir
    sobre el malo — se deja fijado para que no vuelva."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text()
    i = src.index("def _parecia_cortada")
    cuerpo = src[i:src.index("\ndef ", i + 10)]
    assert 'endswith("}")' not in cuerpo


# ── el techo ───────────────────────────────────────────────────────────────────────────────────────────────

def test_el_techo_cabe_el_veredicto_medido():
    """7238 chars a ~3,3 chars por token (el mismo número que el motor tiene medido para su facturación) son
    ~2200 tokens. 2000 no llegaba; el techo tiene que dejar margen real, no rozarlo."""
    assert J.JUDGE_MAX_TOKENS * 3.3 > 7238 * 1.3


def test_el_juez_USA_ese_techo_y_no_un_literal():
    """El cableado: subir la constante y dejar el `2000` en la llamada es el fallo clásico."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text()
    # V2-382 — el techo ya no es UNO: la primera petición va con `JUDGE_MAX_TOKENS` y el reintento de una
    # respuesta que no cupo sube a `JUDGE_MAX_TOKENS_AMPLIADO`. Lo que este guarda sostiene sigue siendo lo
    # mismo: que el número salga de las constantes y no de un literal escrito a mano en la llamada.
    assert "llm.judge_call(msgs, max_tokens=techo, out=corte)" in src
    assert "techo = JUDGE_MAX_TOKENS" in src
    assert "llm.judge_call(msgs, max_tokens=2000)" not in src


# ── el reintento dice la verdad ────────────────────────────────────────────────────────────────────────────

def _pedir(monkeypatch, raws, errs):
    """Corre el bucle real capturando lo que se le pide al juez en cada reintento."""
    pedidos = []
    estado = {"i": 0}

    def _call(msgs, **kw):
        for m in msgs[2:]:
            if m.get("role") == "user":
                pedidos.append(m["content"])
        i = estado["i"]; estado["i"] += 1
        return raws[min(i, len(raws) - 1)], "modelo-de-prueba"

    monkeypatch.setattr(J.llm, "judge_call", _call)
    monkeypatch.setattr(J.llm, "parse_json",
                        lambda raw: (_ for _ in ()).throw(ValueError(errs[min(estado["i"] - 1, len(errs) - 1)])))
    return pedidos


def test_una_respuesta_CORTADA_pide_brevedad(monkeypatch):
    raws = ["x" * 6487] * 3
    errs = ["Expecting ',' delimiter: line 84 column 6 (char 6451)"] * 3
    pedidos = _pedir(monkeypatch, raws, errs)
    with pytest.raises(RuntimeError):
        J._judge_with_retry([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert pedidos, "el bucle no llegó a reintentar"
    assert "se CORTÓ por longitud" in pedidos[0]
    assert "recorta la prosa" in pedidos[0]
    # V2-382 — y no solo se le pide: se le DA sitio. Pedir lo mismo más corto con el mismo techo fue lo que
    # perdió la ronda de las 11:00 del 2026-08-27 con los tres intentos cortados en el mismo carácter.
    assert "MÁS SITIO" in pedidos[0]


def test_una_respuesta_MAL_FORMADA_pide_el_mismo_veredicto(monkeypatch):
    """La sensibilidad por el otro lado: mandarle recortar un veredicto que cabía le haría perder notas por
    un error nuestro de diagnóstico."""
    raws = ["x" * 6750] * 3
    errs = ["Expecting ',' delimiter: line 22 column 6 (char 1159)"] * 3
    pedidos = _pedir(monkeypatch, raws, errs)
    with pytest.raises(RuntimeError):
        J._judge_with_retry([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert "EXACTAMENTE el mismo veredicto" in pedidos[0]
    assert "MÁS BREVE" not in pedidos[0]
