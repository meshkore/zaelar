"""Turn latency verdict (`nucleo/flash/turn_perf.py`).

Operator premise (2026-08-02): “DeepSeek Flash is fast; if a turn takes more than 1–2 s, it is because the prompt is
too long or because the provider has failed sporadically.” These tests ensure that the verdict can
DISTINGUISH those two cases—and does not confuse either a cold start or a turn that does real work with them—,
because a diagnosis that always says "slow" is not useful for making decisions.
"""
from nucleo.flash import turn_perf as tp


def test_fast_turn_is_not_flagged():
    v = tp.verdict({"total_ms": 900, "prompt_tokens": 3000, "tok_per_s": 40})
    assert v["slow"] is False and v["cause"] == "ok"


def test_big_prompt_is_named_with_its_worst_block():
    """The REAL measured case: 12,892 tokens to say “hello,” with the tools catalog carrying the most weight (31 KB)."""
    v = tp.verdict({"total_ms": 4200, "prompt_tokens": 12892, "tools_chars": 31458,
                    "sz_resources": 8408, "sz_memory": 2569, "tok_per_s": 30})
    assert v["slow"] and v["cause"] == "prompt"
    assert v["top_block"] == "catálogo de tools"      # nombra al culpable, no solo "prompt grande"
    assert "12892" in v["label"]


def test_generacion_lenta_de_verdad_si_es_del_proveedor():
    """`proveedor` = WRITES slowly: low throughput with the time DISTRIBUTED (short TTFT). This is the case that
    distinguishes “the provider is malfunctioning” from “the model is thinking.”"""
    v = tp.verdict({"total_ms": 6000, "prompt_tokens": 2500, "tok_per_s": 3.1, "ttft_ms": 900})
    assert v["cause"] == "proveedor"


def test_casi_todo_antes_del_primer_token_es_pre_token_no_proveedor():
    """This case used to say `proveedor` by elimination. With 5,800 of 6,000 ms before the first token, there is nothing to
    eliminate: the time was spent THINKING (or queued), and tok/s measured over 200 ms means nothing."""
    v = tp.verdict({"total_ms": 6000, "prompt_tokens": 2500, "tok_per_s": 3.1, "ttft_ms": 5800})
    assert v["cause"] == "pre_token"
    assert "TTFT" in v["label"] and "96%" in v["label"]


def test_cold_start_is_not_blamed_on_the_provider():
    v = tp.verdict({"total_ms": 7000, "prompt_tokens": 2500, "gap_since_last_s": 300, "tok_per_s": 20})
    assert v["cause"] == "frio"


def test_cold_wins_over_a_big_prompt():
    """After 5 minutes of silence, the 1st call pays the handshake cost: blaming the prompt would lead us to optimize the wrong thing."""
    v = tp.verdict({"total_ms": 9000, "prompt_tokens": 12000, "gap_since_last_s": 300, "tok_per_s": 20})
    assert v["cause"] == "frio"


def test_a_turn_that_did_real_work_is_not_an_incident():
    v = tp.verdict({"total_ms": 3200, "prompt_tokens": 3000, "tok_per_s": 25, "escalated": True})
    assert v["cause"] == "trabajo" and "escalada" in v["label"]


def test_lento_y_sin_causa_dominante_lo_dice_en_vez_de_inventar_un_culpable():
    """Previously it was resolved by elimination (“points to a provider failure”). An invented culprit leads us to optimize
    the wrong thing; bare numbers do not."""
    v = tp.verdict({"total_ms": 5000, "prompt_tokens": 2000, "tok_per_s": 30, "ttft_ms": 2000})
    assert v["cause"] == "reparto"
    assert "sin causa dominante" in v["label"]


def test_missing_metrics_degrade_instead_of_raising():
    v = tp.verdict({})
    assert v["cause"] == "ok" and v["slow"] is False
    assert tp.verdict({"total_ms": None, "prompt_tokens": "x"})["slow"] is False


def test_emit_verdict_never_raises_without_an_observer():
    assert tp.emit_verdict({"total_ms": 3000, "prompt_tokens": 9000})["cause"] == "prompt"


# ── THE BLIND SPOT (2026-08-14): the `proveedor` branch was unreachable in the VOICE path ─────────────────────
# The order was cold → prompt → provider, and `prompt` wins with `prompt_tokens >= 6000`. The voice prompt is ALWAYS
# 9–10k tokens, so EVERY slow turn was labeled “LARGE PROMPT” and could never be attributed to anything else.
# Real consequence: in session b70a45d0, all 10 slow turns blamed the prompt even though the prompt was CONSTANT
# (9,363–10,314 tok, ±9%) and TTFT ranged from 0 to 25,703 ms. A flat input does not explain a factor of 10—and we spent
# weeks looking in the wrong place because of a precedence rule.
#
# The 11 turns from that session, with their REAL numbers, are the test case.
_SESION_B70A45D0 = [
    # (total_ms, ttft_ms, gen_ms, prompt_tokens, tok_per_s)
    (2982, 2630, 2661, 9710, 77.4), (28624, 25595, 28212, 10271, 119.9), (16326, 13704, 16010, 10167, 134.4),
    (12869, 12869, 12486, 10182, 140.4), (7613, 7612, 7240, 9397, 154.8), (11030, 9128, 10677, 9394, 139.0),
    (9202, 6771, 8879, 9490, 142.8), (25704, 25703, 25253, 10314, 109.0), (8069, 5096, 7726, 9395, 97.1),
    (2284, 0, 1970, 9937, 79.2), (2617, 2492, 2268, 9363, 70.5),
]


def _verdicts_de_la_sesion():
    out = []
    for total, ttft, gen, ptok, tps in _SESION_B70A45D0:
        out.append(tp.verdict({"total_ms": total, "ttft_ms": ttft, "gen_ms": gen, "prompt_tokens": ptok,
                               "tok_per_s": tps, "tools_chars": 17335, "sz_resources": 9232,
                               "gap_since_last_s": 5}))
    return out


def test_los_turnos_reales_ya_no_culpan_todos_al_prompt():
    causes = [v["cause"] for v in _verdicts_de_la_sesion()]
    assert causes.count("prompt") <= 1, f"sigue culpando al prompt de casi todo: {causes}"
    assert causes.count("pre_token") >= 6, f"no reconoce el TTFT como el culpable dominante: {causes}"


def test_los_dos_turnos_de_25_segundos_son_pre_token():
    """The two worst in the session: 25,595 and 25,703 ms of TTFT, or 89% and 99% of the turn. They were the two
    turns with the hardest decision, which is the signature of hidden reasoning—not of prompt size."""
    peores = [v for v in _verdicts_de_la_sesion() if v["total_ms"] > 25000]
    assert len(peores) == 2
    for v in peores:
        assert v["cause"] == "pre_token", v["label"]
        assert "no lo explica" in v["label"], "tiene que decir explícitamente que el prompt no es la causa"


def test_el_prompt_solo_se_culpa_si_el_tiempo_se_reparte():
    """A 10k prompt with TTFT dominating is NOT the prompt's fault; the same prompt with the time distributed is.
    This is exactly the bias that has been removed."""
    dom = tp.verdict({"total_ms": 10000, "ttft_ms": 9500, "prompt_tokens": 10000, "tok_per_s": 120})
    rep = tp.verdict({"total_ms": 10000, "ttft_ms": 1500, "prompt_tokens": 10000, "tok_per_s": 120})
    assert dom["cause"] == "pre_token" and rep["cause"] == "prompt"


def test_la_fraccion_de_ttft_viaja_en_el_veredicto():
    """`ttft_frac` is the series that governs the failover latency circuit and makes it possible to see the VARIANCE
    of TTFT with a constant prompt (2,492 → 25,703 ms with ±9% input). Without it, the trigger would be blind."""
    v = tp.verdict({"total_ms": 10000, "ttft_ms": 9000, "prompt_tokens": 9500, "tok_per_s": 120})
    assert v["ttft_frac"] == 0.9
    assert tp.verdict({})["ttft_frac"] == 0.0, "sin datos no se afirma nada"
