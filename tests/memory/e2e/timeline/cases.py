"""Deterministic six-month life timeline for the memory system.

Unlike the historical corpora, dates here alter the real memory clock. Every case
is one chronological operation and the runner always replays its required prefix.
"""
from __future__ import annotations

from typing import Any


DAYS = 180
CASES: list[dict[str, Any]] = []


def _add(day: int, op: str, title: str, **fields: Any) -> None:
    CASES.append({"day": day, "op": op, "title": title, **fields})


# Stable human facts and goals. They must remain through six months of noise.
_add(0, "write", "Objetivo vital: estudiar arquitectura", text="Quiero estudiar arquitectura en profundidad.",
     level="long", kind="pref", importance=0.92, weight=0.72, slot="goal.study_architecture",
     expected="permanece activo durante seis meses")
_add(0, "write", "Objetivo vital: comprar casa en Valencia", text="Mi objetivo es comprar una casa en Valencia.",
     level="long", kind="pref", importance=0.96, weight=0.75, slot="goal.house",
     expected="permanece activo y se fortalece con el uso")
_add(0, "write", "Biografía inicial: infancia en Sevilla", text="Cuando era pequeño vivía en Sevilla.",
     level="long", kind="profile", importance=0.82, weight=0.65, slot="bio.childhood_city",
     expected="queda vigente hasta una corrección explícita")
_add(0, "write", "Dato médico crítico", text="Soy alérgico a la penicilina.", level="long", kind="pref",
     importance=0.99, weight=0.9, pinned=True, expected="nunca caduca ni se evicta")


for day in range(DAYS + 1):
    _add(day, "advance", f"Día {day}: avanzar reloj", expected=f"reloj de memoria = día {day}")

    # Daily low-value activity: useful in recent context, irrelevant months later.
    _add(day, "write", f"Día {day}: café cotidiano",
         text=f"El día {day} tomé un café rutinario en la cafetería COTIDIANO-{day:03d}.",
         level="short", kind="event", importance=0.12, weight=0.18, ttl_days=20,
         expected="visible durante 20 días; después expira")
    _add(day, "write", f"Día {day}: proceso efímero de widget",
         text=f"El día {day} ajusté el widget temporal WIDGET-{day:03d}.",
         level="short", kind="conv", importance=0.08, weight=0.12, ttl_days=2,
         expected="buffer operativo; expira en 2 días y nunca se promociona")

    # A meaningful but non-permanent episode every two weeks. V2-103: etiquetado con `concepts` (antes no lo
    # llevaba ninguna escritura de este corpus) — a día 180 quedan ~6 vigentes dentro del TTL de 90 días, por
    # encima de `rem.MIN_GROUP=4`, así que este es el grupo que REM sintetiza/demota en los checkpoints finales.
    if day and day % 15 == 0:
        _add(day, "write", f"Día {day}: episodio relevante temporal",
             text=f"El día {day} terminé el capítulo {day // 15} del curso de estructuras ARQ-{day:03d}.",
             level="mid", kind="event", importance=0.55, weight=0.48, ttl_days=90, concepts=["estudios"],
             expected="permanece un trimestre y luego caduca")

    # Repeated access strengthens the house goal. Architecture is deliberately
    # accessed less often so the final test can compare their trajectories.
    if day % 7 == 0:
        _add(day, "recall", f"Día {day}: usar objetivo de vivienda", query="¿Cuál es mi objetivo de vivienda?",
             marker="casa en valencia", reinforce=True, expected="recall correcto + aumento de peso/accesos")
    if day in {0, 60, 120, 180}:
        _add(day, "recall", f"Día {day}: usar objetivo de estudios", query="¿Qué quiero estudiar?",
             marker="arquitectura", reinforce=True, expected="recall correcto + refuerzo ocasional")

    # Correction after enough intervening activity: the old fact becomes history
    # and must not leak as the current answer.
    if day == 45:
        _add(day, "write", "Corrección biográfica: era Segovia, no Sevilla",
             text="Cuando era pequeño vivía en Segovia.",
             level="long", kind="profile", importance=0.88, weight=0.7, slot="bio.childhood_city",
             expected="Segovia supersede Sevilla en el mismo slot")
        _add(day, "slot", "Comprobar corrección biográfica", slot="bio.childhood_city",
             marker="segovia", not_marker="sevilla", expected="una sola versión vigente: Segovia")

    # One light sleep per simulated day, same production consolidator.
    _add(day, "consolidate", f"Noche {day}: sueño ligero", limit=180,
         expected="promoción, dedup, decay, TTL, pruning y eviction por valor")

    # Production REM is due every 24h. Day 0 seeds the persistent marker and the
    # first deep sleep happens after the first complete simulated day. The
    # deterministic simulation runs repair/dedup/hygiene; semantic insight
    # generation is intentionally omitted (no external LLM).
    if day:
        _add(day, "rem", f"Noche {day}: fase REM", expected="reparación, dedup semántico e higiene")

    if day == 10:
        _add(day, "active", "Checkpoint 10 días: el café reciente sigue activo", marker="COTIDIANO-000",
             expected="activo antes de cumplir TTL 20")
    if day == 21:
        _add(day, "inactive", "Checkpoint 21 días: el primer café ya expiró", marker="COTIDIANO-000",
             expected="fuera de memoria activa tras TTL")
    if day in {30, 90, 180}:
        _add(day, "active", f"Checkpoint día {day}: objetivos y salud sobreviven", marker="casa en Valencia",
             expected="objetivo vital activo")
        _add(day, "active", f"Checkpoint día {day}: arquitectura sobrevive", marker="arquitectura",
             expected="objetivo de estudio activo")
        _add(day, "active", f"Checkpoint día {day}: alergia sobrevive", marker="penicilina",
             expected="dato crítico activo")
    if day == 180:
        _add(day, "slot", "Checkpoint final: biografía corregida", slot="bio.childhood_city",
             marker="segovia", not_marker="sevilla", expected="Segovia vigente; Sevilla solo histórico")
        _add(day, "weight_compare", "Checkpoint final: lo usado se fortalece más",
             stronger="goal.house", weaker="goal.study_architecture",
             expected="peso/accesos de vivienda > estudios por mayor uso")
        _add(day, "valid_count", "Checkpoint final: memoria activa acotada", maximum=182,
             expected="la vida de seis meses no deja crecer sin límite el working memory")
        # V2-103: tras 180 sueños con síntesis REM activada (antes se probaba SIEMPRE apagada aquí), el grupo
        # "estudios" (episodios ARQ-* etiquetados arriba) debe haber producido un insight vigente, y las
        # píldoras crudas que lo alimentaron deben estar demotadas (nunca invalidadas) — REM consolidando de
        # verdad, no solo apilando encima.
        _add(day, "insight_exists", "Checkpoint final: REM sintetizó un insight de estudios",
             concept="estudios", marker="estudios", expected="slot=insight:estudios vigente")
        _add(day, "pills_demoted", "Checkpoint final: REM demotó las píldoras que resumió",
             minimum=4, expected="≥4 píldoras con meta.summarized_by, todas siguen valid=1")


def case_id(index: int) -> str:
    return f"memory::timeline::{index:04d}"


def platform_group() -> dict[str, Any]:
    cases = []
    for index, raw in enumerate(CASES):
        op = raw["op"]
        cases.append({
            "id": case_id(index), "ordinal": index + 1, "title": raw["title"], "type": op,
            "dimension": f"día {raw['day']}", "input": {k: v for k, v in raw.items() if k != "expected"},
            "expected": {"outcome": raw.get("expected", "operación correcta")},
            "verification": "reproducir todos los pasos anteriores sobre una única BD y comprobar el estado resultante",
            "execution_path": ["reloj simulado", "BD cronológica única", "memory API / writer",
                               "consolidación/REM cuando corresponde", "assertion del estado temporal"],
            "source": "tests/memory/e2e/timeline/cases.py", "raw": raw,
            "execution": {"kind": "command",
                          "argv": ["{python}", "-m", "tests.memory.e2e.timeline.runner", "--target", str(index)],
                          "nested_events": True, "stateful": True, "replay_prefix": True},
        })
    return {
        "id": "timeline-6m", "label": "Vida cronológica · 180 días", "mode": "una BD · orden causal obligatorio",
        "count": len(cases), "cases": cases,
        "execution": {"kind": "command",
                      "argv": ["{python}", "-m", "tests.memory.e2e.timeline.runner", "--all"],
                      "nested_events": True, "stateful": True},
    }
