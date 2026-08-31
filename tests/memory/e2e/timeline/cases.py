"""Deterministic six-month life timeline for the memory system.

Unlike the historical corpora, dates here alter the real memory clock. Every case
is one chronological operation and the runner always replays its required prefix.
"""
from __future__ import annotations

import random
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

# A meaningful but non-permanent episode every two weeks. V2-103: tagged with `concepts` (previously no
# write in this corpus carried it) — by day 180, ~6 remain current within the 90-day TTL, above
# `rem.MIN_GROUP=4`, so this is the group that REM synthesizes/demotes at the final checkpoints.
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
        # V2-103: after 180 sleeps with REM synthesis enabled (previously it was ALWAYS tested disabled here), the
        # "estudios" group (the ARQ-* episodes tagged above) should have produced a current insight, and the
        # raw pills that fed it should be demoted (never invalidated) — REM truly consolidating, rather than
        # merely piling on top.
        _add(day, "insight_exists", "Checkpoint final: REM sintetizó un insight de estudios",
             concept="estudios", marker="estudios", expected="slot=insight:estudios vigente")
        _add(day, "pills_demoted", "Checkpoint final: REM demotó las píldoras que resumió",
             minimum=4, expected="≥4 píldoras con meta.summarized_by, todas siguen valid=1")


# ── REAL segment, seed-reproducible (V2-105, 2026-08-17) ────────────────────────────────────────────────
# The segment above (180 days) is a 100% fixed script — perfect for regression, but blind to the NEXT class of
# bug: a real user corrects themselves after 20–30 days, repeats the same fact in other words weeks later,
# or says two nearly simultaneous things that compete for the same datum. None of the three patterns existed
# here. It is ADDED as a new segment after day 180 (it never replaces the fixed script — the runner's
# replay-prefix already reconstructs 0..N causally) using `random.Random(SEED)`: reproducible for a given seed
# (same run = same cases every time), genuine variety if the seed changes — not true randomness, CONTROLLED
# randomness.
# It reuses the vocabulary of the EXISTING `op` (write/slot/recall/active) — there is no need to teach any new
# branch to `runner.py::_execute()`, only to generate varied content with the pieces already available.
REAL_DAYS = 90              # days 181..270
TOTAL_DAYS = DAYS + REAL_DAYS
SEED = 20260817
_rng = random.Random(SEED)

# (slot, template, [values]) — each contradiction uses ONE synthetic slot with two different values.
_CONTRADICT_BANK = [
    ("goal.job", "Quiero dedicarme a {v}.", ["diseño de producto", "consultoría técnica", "docencia universitaria",
                                              "investigación aplicada"]),
    ("pref.transport", "Para moverme por la ciudad prefiero {v}.", ["la bicicleta", "el transporte público",
                                                                      "el coche eléctrico", "ir andando"]),
    ("pref.diet", "Ahora mismo estoy siguiendo una dieta {v}.", ["vegetariana", "mediterránea", "sin gluten",
                                                                    "flexitariana"]),
    ("goal.language", "Estoy aprendiendo {v} este año.", ["alemán", "portugués", "italiano", "japonés"]),
]

# Same fact, two ways of saying it — without a slot (the point is to test exact/semantic dedup, not supersede).
# `query`/`marker`: verification by RECALL after the repetition — whether dedup merges it is not assumed
# (it depends on the active embeddings backend and is uncertain in advance), only that the fact REMAINS
# retrievable.
_PARAPHRASE_BANK = [
    ("le encanta el senderismo de montaña los fines de semana", "los fines de semana disfruta caminando por la montaña",
     "¿qué le gusta hacer los fines de semana?", "montaña"),
    ("toca la guitarra española por las tardes", "por las tardes es cuando practica con su guitarra",
     "¿toca algún instrumento?", "guitarra"),
    ("colecciona vinilos de jazz de los años setenta", "tiene una colección de discos de jazz de esa década",
     "¿qué colecciona?", "jazz"),
    ("cocina platos de la cocina tailandesa casi cada semana", "casi todas las semanas prepara comida tailandesa",
     "¿qué tipo de comida cocina?", "tailandes"),
    ("está aprendiendo a programar en Python en su tiempo libre", "en los ratos libres estudia programación con Python",
     "¿qué está aprendiendo?", "python"),
]

# Two values for the SAME slot, written nearly simultaneously — supersede under real ambiguity, not a clean case.
_COMPETING_BANK = [
    ("event.next_trip", "El próximo viaje que tiene planeado es a {v}.", ["Lisboa", "Roma", "Ámsterdam"]),
    ("pref.weekend_plan", "Este fin de semana tiene pensado {v}.", ["visitar a sus padres", "quedarse en casa",
                                                                      "ir a la playa"]),
]


def _real_tramo() -> None:
    # Each day bank leaves enough margin so that start_day plus its deferred resolution (gap/offset) NEVER
    # falls outside range(DAYS+1, DAYS+REAL_DAYS+1) — a resolution scheduled for a day the loop does not
    # iterate would be silently lost (the write would have no verification). Margins: contradict gap≤35,
    # paraphrase gap≤55, competing offset+check≤6.
    contradict_days = sorted(_rng.sample(range(DAYS + 3, DAYS + REAL_DAYS - 40), 8))
    paraphrase_days = sorted(_rng.sample(range(DAYS + 3, DAYS + REAL_DAYS - 60), 5))
    competing_days = sorted(_rng.sample(range(DAYS + 3, DAYS + REAL_DAYS - 10), 5))

    contradictions = {}
    for i, start_day in enumerate(contradict_days):
        slot, template, values = _CONTRADICT_BANK[i % len(_CONTRADICT_BANK)]
        slot = f"{slot}.{i}"  # a separate instance per case; they do not share state
        a, b = _rng.sample(values, 2)  # a = first value written; b = the alternative, never written if "confirms"
        gap = _rng.randint(5, 35)
        agrees = _rng.random() < 0.3  # 30% of the time "confirms" (same value), 70% corrects (different value)
        contradictions[start_day] = (slot, template, a, b, gap, agrees)

    paraphrases = {}
    for i, start_day in enumerate(paraphrase_days):
        base, repeat, query, marker = _PARAPHRASE_BANK[i % len(_PARAPHRASE_BANK)]
        gap = _rng.randint(14, 55)
        paraphrases[start_day] = (base, repeat, gap, query, marker)

    competing = {}
    for i, start_day in enumerate(competing_days):
        slot, template, values = _COMPETING_BANK[i % len(_COMPETING_BANK)]
        slot = f"{slot}.{i}"
        a, b = _rng.sample(values, 2)
        offset = _rng.randint(0, 2)  # 0–2 days apart: "nearly simultaneous," not the same instant
        competing[start_day] = (slot, template, a, b, offset)

    resolve_at: dict[int, list[Any]] = {}  # day → list of deferred checkpoints to schedule on that day

    for day in range(DAYS + 1, DAYS + REAL_DAYS + 1):
        _add(day, "advance", f"Día {day}: avanzar reloj (tramo real)", expected=f"reloj de memoria = día {day}")

        if day in contradictions:
            slot, template, first_val, _alt_val, gap, agrees = contradictions[day]
            _add(day, "write", f"Día {day}: hecho inicial ({slot})", text=template.format(v=first_val),
                 level="long", kind="pref", importance=0.75, weight=0.6, slot=slot,
                 expected="vigente hasta que llegue (o no) una corrección diferida")
            resolve_at.setdefault(day + gap, []).append(("contradict", slot, template, contradictions[day]))

        if day in paraphrases:
            base, _repeat, gap, _query, _marker = paraphrases[day]
            _add(day, "write", f"Día {day}: hecho reformulable", text=base.strip().capitalize() + ".",
                 level="mid", kind="fact", importance=0.5, weight=0.5,
                 expected="sigue vigente; en unas semanas llega la misma idea con otras palabras")
            resolve_at.setdefault(day + gap, []).append(("paraphrase", paraphrases[day]))

        if day in competing:
            slot, template, a, b, offset = competing[day]
            _add(day, "write", f"Día {day}: primer valor en competencia ({slot})", text=template.format(v=a),
                 level="mid", kind="fact", importance=0.6, weight=0.55, slot=slot,
                 expected="puede quedar superado por un valor casi-simultáneo")
            resolve_at.setdefault(day + offset, []).append(("competing", slot, template, b))
            resolve_at.setdefault(day + offset + 4, []).append(("competing_check", slot, b, a))

        for item in resolve_at.get(day, []):
            kind = item[0]
            if kind == "contradict":
                _, slot, template, (_slot2, _tmpl2, first_val, alt_val, _gap, agrees) = item
                # confirms → rewrite the SAME value (first_val); corrects → write the ALTERNATIVE (alt_val).
                # `not_marker` is ALWAYS required here: `_execute()`'s `slot` check treats a missing
                # `not_marker` as an empty string, and `"" in text` is ALWAYS true in Python — without it the
                # checkpoint would ALWAYS fail regardless of the outcome (found in the first real run of this).
                second_val = first_val if agrees else alt_val
                excluded_val = alt_val if agrees else first_val
                verb = "confirma" if agrees else "corrige"
                _add(day, "write", f"Día {day}: {verb} el hecho de «{slot}»", text=template.format(v=second_val),
                     level="long", kind="pref", importance=0.78, weight=0.62, slot=slot,
                     expected="supersede: solo esta versión queda vigente")
                _add(day, "slot", f"Día {day}: comprobar «{slot}» tras {verb}", slot=slot,
                     marker=second_val.lower(), not_marker=excluded_val.lower(),
                     expected="una sola versión vigente, la más reciente")
            elif kind == "paraphrase":
                _, (base, repeat, _gap, query, marker) = item
                _add(day, "write", f"Día {day}: la misma idea, reformulada", text=repeat.strip().capitalize() + ".",
                     level="mid", kind="fact", importance=0.5, weight=0.5,
                     expected="dedup exacto/semántico decide si colapsa con el original")
                _add(day, "recall", f"Día {day}: recall tras la repetición reformulada", query=query,
                     marker=marker, expected="el hecho sigue siendo recuperable, fusionado o no")
            elif kind == "competing":
                _, slot, template, b_val = item
                _add(day, "write", f"Día {day}: segundo valor casi-simultáneo ({slot})", text=template.format(v=b_val),
                     level="mid", kind="fact", importance=0.6, weight=0.55, slot=slot,
                     expected="el más reciente manda, aunque la ventana sea de días, no segundos")
            elif kind == "competing_check":
                _, slot, b_val, a_val = item
                _add(day, "slot", f"Día {day}: comprobar «{slot}» tras la competencia", slot=slot,
                     marker=b_val.lower(), not_marker=a_val.lower(),
                     expected="gana el valor escrito en último lugar")

        if day % 15 == 0:
            _add(day, "consolidate", f"Noche {day}: sueño ligero (tramo real)", limit=180,
                 expected="promoción, dedup, decay, TTL, pruning y eviction por valor")
        _add(day, "rem", f"Noche {day}: fase REM (tramo real)", expected="reparación, dedup semántico, síntesis")

    last_day = DAYS + REAL_DAYS
    _add(last_day, "valid_count", "Checkpoint tramo real: memoria activa sigue acotada", maximum=400,
         expected="90 días adicionales de variedad no revientan el techo de working memory")


_real_tramo()


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
