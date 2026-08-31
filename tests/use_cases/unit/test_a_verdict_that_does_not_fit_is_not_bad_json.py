"""The verdict did not fit, and the retry asked it for exactly what does not fit (V2-373).

`two-searches-two-sheets` lost its verdict FOUR times. The three calls from one of those
failures were instrumented, with `max_tokens=2000`:

    attempt 1 → 6558 chars, cut off mid-word
    attempt 2 → 6368 chars, cut off mid-word
    attempt 3 → 6487 chars, cut off mid-word

And the COMPLETE verdict for that case, measured by raising the ceiling: **7238 chars**. It was not bad luck or a
careless JSON — that case did not fit, so it **could never be judged**, and each attempt spent a call only to
not fit again. Ten and a half minutes of real browser time wasted, each time.

Two fixes, and the second matters as much as the first:

1. The ceiling. The loop's comment already pointed to multiflow and attributed the wrong cause to it —“more JSON
   to get wrong”—: there are not more opportunities for error, there is more SIZE (seven dimensions instead of
   five, each with its prose).
2. **CUT OFF is not INVALID.** The retry said “your response was not valid JSON, return EXACTLY the same
   verdict” — to someone who had written perfect JSON that we truncated. We asked it to repeat what does not fit,
   so all three attempts were the same attempt. It is the V2-171 family: a truncated response disguised as a
   formatting error.
"""
import pytest

from tests.use_cases.e2e.agent import judge as J


# ── distinguish CUT OFF from MALFORMED ──────────────────────────────────────────────────────────────────────

def test_los_tres_cortes_medidos_se_reconocen():
    """The (chars, failure position) pairs from the real failures."""
    for total, pos in ((6487, 6451), (6750, 6688)):
        assert J._parecia_cortada("x" * total, f"Expecting ',' delimiter: line 84 column 6 (char {pos})")


def test_un_fallo_de_FORMA_no_se_confunde_con_un_corte():
    """The 09:36 failure occurred at char 1159 in a much longer text: that is a comma or a
    quote, and asking for brevity there would tell it to shorten a verdict that fit perfectly."""
    assert not J._parecia_cortada("x" * 6750, "Expecting ',' delimiter: line 22 column 6 (char 1159)")


def test_sin_posicion_en_el_error_no_se_adivina():
    assert not J._parecia_cortada("x" * 6750, "Expecting value")
    assert not J._parecia_cortada("x" * 6750, None)


def test_sin_respuesta_no_hay_corte_que_detectar():
    assert not J._parecia_cortada("", "Expecting ',' delimiter: line 1 column 1 (char 0)")


def test_NO_se_usa_termina_en_llave_y_esta_es_la_razon():
    """It was the first attempt and is a measured false negative: a 7238-char response that DID parse
    successfully returned False with that criterion. A guard that gets the GOOD case wrong cannot decide
    about the bad one — this is fixed in place so it does not happen again."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text()
    i = src.index("def _parecia_cortada")
    cuerpo = src[i:src.index("\ndef ", i + 10)]
    assert 'endswith("}")' not in cuerpo


# ── the ceiling ─────────────────────────────────────────────────────────────────────────────────────────────

def test_el_techo_cabe_el_veredicto_medido():
    """7238 chars at ~3.3 chars per token (the same number the engine has measured for billing) are
    ~2200 tokens. 2000 was not enough; the ceiling must leave real headroom, not just scrape past it."""
    assert J.JUDGE_MAX_TOKENS * 3.3 > 7238 * 1.3


def test_el_juez_USA_ese_techo_y_no_un_literal():
    """The wiring: raising the constant while leaving `2000` in the call is the classic failure."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text()
    # V2-382 — the ceiling is no longer ONE: the first request uses `JUDGE_MAX_TOKENS`, and the retry for a
    # response that did not fit raises it to `JUDGE_MAX_TOKENS_AMPLIADO`. What this guard still enforces is the
    # same: that the number come from the constants and not from a literal written by hand in the call.
    assert "llm.judge_call(msgs, max_tokens=techo, out=corte)" in src
    assert "techo = JUDGE_MAX_TOKENS" in src
    assert "llm.judge_call(msgs, max_tokens=2000)" not in src


# ── el reintento dice la verdad ────────────────────────────────────────────────────────────────────────────

def _pedir(monkeypatch, raws, errs):
    """Run the real loop, capturing what is requested from the judge on each retry."""
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
    # V2-382 — and it is not merely requested: it is GIVEN room. Asking for the same thing more briefly with the
    # same ceiling is what lost the 11:00 round on 2026-08-27, with all three attempts cut off at the same char.
    assert "MÁS SITIO" in pedidos[0]


def test_una_respuesta_MAL_FORMADA_pide_el_mismo_veredicto(monkeypatch):
    """The sensitivity in the other direction: telling it to shorten a verdict that fit would make it lose notes
    because of an error in our diagnosis."""
    raws = ["x" * 6750] * 3
    errs = ["Expecting ',' delimiter: line 22 column 6 (char 1159)"] * 3
    pedidos = _pedir(monkeypatch, raws, errs)
    with pytest.raises(RuntimeError):
        J._judge_with_retry([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert "EXACTAMENTE el mismo veredicto" in pedidos[0]
    assert "MÁS BREVE" not in pedidos[0]
