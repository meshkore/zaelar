"""Veredicto de latencia del turno (`nucleo/flash/turn_perf.py`).

Premisa del operador (2026-08-02): «DeepSeek Flash es rápido; si un turno pasa de 1-2 s es porque el prompt es
demasiado extenso o porque el proveedor ha fallado puntualmente». Estos tests fijan que el veredicto sepa
DISTINGUIR esos dos casos —y no confunda con ellos ni el arranque en frío ni un turno que hace trabajo de verdad—,
porque un diagnóstico que siempre dice "lento" no sirve para decidir nada.
"""
from nucleo.flash import turn_perf as tp


def test_fast_turn_is_not_flagged():
    v = tp.verdict({"total_ms": 900, "prompt_tokens": 3000, "tok_per_s": 40})
    assert v["slow"] is False and v["cause"] == "ok"


def test_big_prompt_is_named_with_its_worst_block():
    """El caso REAL medido: 12.892 tokens para decir «hola», y el que más pesa es el catálogo de tools (31 KB)."""
    v = tp.verdict({"total_ms": 4200, "prompt_tokens": 12892, "tools_chars": 31458,
                    "sz_resources": 8408, "sz_memory": 2569, "tok_per_s": 30})
    assert v["slow"] and v["cause"] == "prompt"
    assert v["top_block"] == "catálogo de tools"      # nombra al culpable, no solo "prompt grande"
    assert "12892" in v["label"]


def test_generacion_lenta_de_verdad_si_es_del_proveedor():
    """`proveedor` = ESCRIBE despacio: throughput bajo con el tiempo REPARTIDO (TTFT corto). Ese es el caso que
    distingue «el proveedor va mal» de «el modelo está pensando»."""
    v = tp.verdict({"total_ms": 6000, "prompt_tokens": 2500, "tok_per_s": 3.1, "ttft_ms": 900})
    assert v["cause"] == "proveedor"


def test_casi_todo_antes_del_primer_token_es_pre_token_no_proveedor():
    """Este caso decía `proveedor` por descarte. Con 5.800 de 6.000 ms antes del primer token no hay nada que
    descartar: el tiempo se fue PENSANDO (o encolado), y el tok/s medido sobre 200 ms no significa nada."""
    v = tp.verdict({"total_ms": 6000, "prompt_tokens": 2500, "tok_per_s": 3.1, "ttft_ms": 5800})
    assert v["cause"] == "pre_token"
    assert "TTFT" in v["label"] and "96%" in v["label"]


def test_cold_start_is_not_blamed_on_the_provider():
    v = tp.verdict({"total_ms": 7000, "prompt_tokens": 2500, "gap_since_last_s": 300, "tok_per_s": 20})
    assert v["cause"] == "frio"


def test_cold_wins_over_a_big_prompt():
    """Tras 5 min en silencio la 1ª llamada paga handshake: culpar al prompt mandaría a optimizar lo que no toca."""
    v = tp.verdict({"total_ms": 9000, "prompt_tokens": 12000, "gap_since_last_s": 300, "tok_per_s": 20})
    assert v["cause"] == "frio"


def test_a_turn_that_did_real_work_is_not_an_incident():
    v = tp.verdict({"total_ms": 3200, "prompt_tokens": 3000, "tok_per_s": 25, "escalated": True})
    assert v["cause"] == "trabajo" and "escalada" in v["label"]


def test_lento_y_sin_causa_dominante_lo_dice_en_vez_de_inventar_un_culpable():
    """Antes se resolvía por descarte («apunta a un fallo del proveedor»). Un culpable inventado manda a optimizar
    lo que no toca; los números desnudos, no."""
    v = tp.verdict({"total_ms": 5000, "prompt_tokens": 2000, "tok_per_s": 30, "ttft_ms": 2000})
    assert v["cause"] == "reparto"
    assert "sin causa dominante" in v["label"]


def test_missing_metrics_degrade_instead_of_raising():
    v = tp.verdict({})
    assert v["cause"] == "ok" and v["slow"] is False
    assert tp.verdict({"total_ms": None, "prompt_tokens": "x"})["slow"] is False


def test_emit_verdict_never_raises_without_an_observer():
    assert tp.emit_verdict({"total_ms": 3000, "prompt_tokens": 9000})["cause"] == "prompt"


# ── LA CEGUERA (2026-08-14): la rama `proveedor` era inalcanzable en el camino de VOZ ──────────────────────────
# El orden era frío → prompt → proveedor, y `prompt` gana con `prompt_tokens >= 6000`. El prompt de voz es SIEMPRE
# de 9-10k tokens, así que TODO turno lento se etiquetaba «PROMPT GRANDE» y nunca podía señalarse a nada más.
# Consecuencia real: en la sesión b70a45d0 los 10 turnos lentos culpaban al prompt mientras el prompt era CONSTANTE
# (9.363-10.314 tok, ±9%) y el TTFT iba de 0 a 25.703 ms. Un input plano no explica un factor 10 — y llevábamos
# semanas mirando al sitio equivocado por culpa de una precedencia.
#
# Los 11 turnos de esa sesión, con sus números REALES, son el caso de prueba.
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
    """Los dos peores de la sesión: 25.595 y 25.703 ms de TTFT, o sea el 89% y el 99% del turno. Eran los dos
    turnos con la decisión más difícil, que es la firma del razonamiento oculto — no del tamaño del prompt."""
    peores = [v for v in _verdicts_de_la_sesion() if v["total_ms"] > 25000]
    assert len(peores) == 2
    for v in peores:
        assert v["cause"] == "pre_token", v["label"]
        assert "no lo explica" in v["label"], "tiene que decir explícitamente que el prompt no es la causa"


def test_el_prompt_solo_se_culpa_si_el_tiempo_se_reparte():
    """Un prompt de 10k con el TTFT dominando NO es culpa del prompt; el mismo prompt con el tiempo repartido, sí.
    Es exactamente el sesgo que se ha quitado."""
    dom = tp.verdict({"total_ms": 10000, "ttft_ms": 9500, "prompt_tokens": 10000, "tok_per_s": 120})
    rep = tp.verdict({"total_ms": 10000, "ttft_ms": 1500, "prompt_tokens": 10000, "tok_per_s": 120})
    assert dom["cause"] == "pre_token" and rep["cause"] == "prompt"


def test_la_fraccion_de_ttft_viaja_en_el_veredicto():
    """`ttft_frac` es la serie que gobierna el circuito de latencia del failover y la que permite ver la VARIANZA
    del TTFT a prompt constante (2.492 → 25.703 ms con ±9% de input). Sin ella el disparo sería a ciegas."""
    v = tp.verdict({"total_ms": 10000, "ttft_ms": 9000, "prompt_tokens": 9500, "tok_per_s": 120})
    assert v["ttft_frac"] == 0.9
    assert tp.verdict({})["ttft_frac"] == 0.0, "sin datos no se afirma nada"
