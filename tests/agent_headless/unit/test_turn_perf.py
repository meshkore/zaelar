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


def test_provider_blip_with_a_normal_prompt():
    v = tp.verdict({"total_ms": 6000, "prompt_tokens": 2500, "tok_per_s": 3.1, "ttft_ms": 5800})
    assert v["cause"] == "proveedor"


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


def test_slow_with_nothing_to_blame_points_at_the_provider():
    v = tp.verdict({"total_ms": 5000, "prompt_tokens": 2000, "ttft_ms": 4800})
    assert v["cause"] == "proveedor"


def test_missing_metrics_degrade_instead_of_raising():
    v = tp.verdict({})
    assert v["cause"] == "ok" and v["slow"] is False
    assert tp.verdict({"total_ms": None, "prompt_tokens": "x"})["slow"] is False


def test_emit_verdict_never_raises_without_an_observer():
    assert tp.emit_verdict({"total_ms": 3000, "prompt_tokens": 9000})["cause"] == "prompt"
