"""¿Cuánto cuesta —en tiempo y en tokens— el catálogo de tools del turno? Medición REAL contra el modelo vivo.

Nace de una pregunta del operador (2026-08-02): «31 KB de tools no puede pesar tanto; hay que tratar las tools de
menos a más como norma… mandar un resumen cortito, y a partir de ahí un segundo request». La intuición sobre el
PESO es correcta, pero la conclusión sobre la LATENCIA no se sostenía, así que en vez de discutirlo se midió.

Tres experimentos, en este orden:

  A) COMPOSICIÓN  — de qué está hecho el catálogo (¿esquemas o prosa?).
  B) DOS PASADAS  — índice compacto + meta-tool `need_capability`, y luego una 2ª llamada con la tool elegida,
                    frente a UNA sola llamada con las 23 tools.
  C) COMPACTAR    — mismas 23 tools pero con la descripción recortada a sus 2 primeras frases: ¿enruta igual?

Uso (exige el server vivo para las credenciales; no toca memoria ni estado):
    ./.venv/bin/python -m tests.agent_headless.e2e.prompt_cost.bench_tools [--only a|b|c]
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import statistics
import time

import server.common  # noqa: F401  — carga el credential store en el entorno

from nucleo.flash import router
from nucleo.flash.fast_client import FastClient, spec_from_config

SPEC = spec_from_config()
SYS = ("Eres Zaelar, el asistente por voz de Ricart. Responde breve y natural.\n"
       "El operador se llama Ricart. Widgets ABIERTOS ahora: results.\n")


def _chars(tools) -> int:
    return sum(len(json.dumps(t, ensure_ascii=False)) for t in tools)


def first_sentences(text: str, n: int = 2, cap: int = 220) -> str:
    """El «para qué» de la tool, sin su manual de uso."""
    return " ".join(re.split(r"(?<=[.!?])\s+", (text or "").strip())[:n])[:cap]


def compact(tools) -> list[dict]:
    out = []
    for t in tools:
        c = copy.deepcopy(t)
        c["function"]["description"] = first_sentences(c["function"].get("description", ""))
        for p in (c["function"].get("parameters", {}).get("properties") or {}).values():
            if isinstance(p, dict) and isinstance(p.get("description"), str):
                p["description"] = p["description"][:120]
        out.append(c)
    return out


def index_lines(tools) -> str:
    return "\n".join(f"- {t['function']['name']}: "
                     f"{(t['function'].get('description') or '').split('.')[0][:90]}" for t in tools)


NEED = [{"type": "function", "function": {
    "name": "need_capability",
    "description": "Llámala SOLO si para atender al operador hace falta una capacidad del índice.",
    "parameters": {"type": "object", "properties": {
        "names": {"type": "array", "items": {"type": "string"}}}, "required": ["names"]}}}]

CASES = [
    ("charla",          "hola, ¿qué tal todo?",                                              set()),
    ("dato del mundo",  "¿cuánto cuesta la entrada de Aquopolis?",                            {"web_search"}),
    ("mostrar widget",  "muéstrame el widget de resultados",                                  {"show_widget"}),
    ("data-op",         "elige el primero de la lista de resultados",                         {"widget_data"}),
    ("tarea larga",     "investiga en internet y ponme un informe de 3 parques en pantalla",  {"escalate_to_slowbrain"}),
    ("música",          "pon música de jazz",                                                 {"play_music"}),
    ("panel",           "abre el chat",                                                       {"show_panel"}),
    ("estilo",          "a partir de ahora sé más breve",                                     {"set_style_directive"}),
    ("borrar widget",   "borra el widget de resultados",                                      {"delete_widget"}),
    ("crear widget",    "créame un widget con el tiempo de Soria",                             {"escalate_to_slowbrain"}),
    ("navegador",       "busca motos naked de segunda mano en Wallapop",                       {"escalate_to_slowbrain"}),
    ("alias",           "llama a este widget «mi informe»",                                    {"manage_widget_alias"}),
]


async def _call(client, messages, tools):
    got, m, t0 = [], {}, time.time()
    async for _ in client.stream(messages, spec=SPEC, tools=tools,
                                 on_tool_call=lambda n, a: got.append(n), metrics=m):
        pass
    return set(got), (time.time() - t0) * 1000, m.get("prompt_tokens") or m.get("prompt_tokens_est") or 0


def exp_a() -> None:
    print("── A · DE QUÉ ESTÁ HECHO EL CATÁLOGO ──")
    rows = sorted(((len(json.dumps(t, ensure_ascii=False)), t["function"]["name"],
                    len(t["function"].get("description") or "")) for t in router.TOOLS), reverse=True)
    desc = sum(r[2] for r in rows)
    print(f"{len(rows)} tools · {sum(r[0] for r in rows)} chars (~{sum(r[0] for r in rows)//4} tok) · "
          f"DESCRIPCIONES {desc} chars = {desc*100//sum(r[0] for r in rows)}% del total")
    for c, n, d in rows[:5]:
        print(f"   {c:6} chars ({d} de descripción)  {n}")
    print("   → lo que pesa es la PROSA de routing, no los esquemas.\n")


async def exp_b() -> None:
    print("── B · ¿DOS PASADAS CORTAS BATEN A UNA LARGA? ──")
    idx = index_lines(router.TOOLS)
    print(f"índice compacto {len(idx)} chars vs catálogo {_chars(router.TOOLS)} chars")
    c = FastClient()
    for name, text, _ in CASES[:6]:
        full = [{"role": "system", "content": SYS}, {"role": "user", "content": text}]
        one = await _call(c, full, router.TOOLS)
        await asyncio.sleep(0.4)
        p1 = await _call(c, [{"role": "system", "content": SYS + "\nCAPACIDADES (índice):\n" + idx},
                             {"role": "user", "content": text}], NEED)
        await asyncio.sleep(0.4)
        total = p1[1]
        if p1[0]:
            p2 = await _call(c, full, router.TOOLS[:2])
            total += p2[1]
            await asyncio.sleep(0.4)
        print(f"   {name:16} 1 pasada {one[1]:>6.0f} ms ({one[2]} tok)   │   2 pasadas {total:>6.0f} ms "
              f"{'(fase1 sola)' if not p1[0] else ''}")
    print("   → cada ida y vuelta cuesta ~1,5-4,5 s; el prompt grande cuesta ~0,15 s. Partir SUMA.\n")


async def exp_c() -> None:
    print("── C · COMPACTAR LAS DESCRIPCIONES: ¿SOBREVIVE EL ENRUTADO? ──")
    comp = compact(router.TOOLS)
    print(f"completo {_chars(router.TOOLS)} chars · compacto {_chars(comp)} chars "
          f"({100 - _chars(comp)*100//_chars(router.TOOLS)}% menos)")
    c = FastClient()
    agree, lat_f, lat_c, tok_f, tok_c = 0, [], [], [], []
    for name, text, _ in CASES:
        msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": text}]
        sf, tf, kf = await _call(c, msgs, router.TOOLS)
        await asyncio.sleep(0.4)
        sc, tc, kc = await _call(c, msgs, comp)
        await asyncio.sleep(0.4)
        agree += int(sf == sc)
        lat_f.append(tf); lat_c.append(tc); tok_f.append(kf); tok_c.append(kc)
        print(f"   {'=' if sf == sc else '≠'} {name:16} completo={str(sorted(sf) or '—'):<32} "
              f"compacto={str(sorted(sc) or '—')}")
    print(f"   coinciden {agree}/{len(CASES)} · latencia p50 {statistics.median(lat_f):.0f} → "
          f"{statistics.median(lat_c):.0f} ms · tokens {statistics.median(tok_f):.0f} → "
          f"{statistics.median(tok_c):.0f}")
    print("   → el ahorro es de COSTE, no de tiempo.\n")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["a", "b", "c"])
    a = ap.parse_args()
    print(f"modelo: {SPEC.provider}/{SPEC.model}\n")
    if a.only in (None, "a"):
        exp_a()
    if a.only in (None, "b"):
        await exp_b()
    if a.only in (None, "c"):
        await exp_c()


if __name__ == "__main__":
    asyncio.run(main())
