"""nucleo/research.py — el BRIEF DE INVESTIGACIÓN: cómo se DIRIGE una búsqueda, no cómo se ejecuta.

EL PROBLEMA QUE RESUELVE (operador, 2026-08-09). Pedir «las mejores vacaciones en Baleares» y recibir tres
resultados es trivial: entrar en una web, poner dos filtros y copiar los tres primeros lo hace cualquiera. Lo que
el operador espera de un asistente es lo que haría una persona competente: mirar CUARENTA opciones, leer las
opiniones, comprobar en las FOTOS que la piscina es de verdad grande, y solo entonces proponer tres. La diferencia
entre esas dos cosas no está en las herramientas del worker —ya sabe navegar y extraer— sino en que NADIE le
estaba diciendo cuán ancho buscar ni con qué baremo juzgar. El worker recibía prosa libre y se autoimponía el
criterio, así que hacía lo mínimo que satisfacía la frase literal.

LA PIEZA. Entre «el operador pide» y «el worker arranca» se compone un BRIEF estructurado que fija:
  · criterios DUROS (lo que descalifica) y BLANDOS (lo que puntúa) separados — un blando tratado como duro deja
    la búsqueda sin resultados; un duro tratado como blando entrega algo que no sirve;
  · lo ASUMIDO cuando el operador no lo dijo, explícito para poder contárselo en vez de fingir que lo sabíamos;
  · ENRIQUECIMIENTOS: lo que un experto del dominio añade y el operador no pensó en pedir (van en coche → hace
    falta parking; niños de 9 y 11 → toboganes puntúan, piscina de bebés no);
  · AMPLITUD: cuántos candidatos hay que reunir ANTES de descartar, y por cuántos ÁNGULOS distintos buscar;
  · BARERO DE CALIDAD: qué hay que verificar de verdad para que un finalista cuente como verificado;
  · ENTREGABLE: la forma de la respuesta en pantalla (cuántas propuestas, de qué piezas se compone cada una).

POR QUÉ ES GENÉRICO Y NO UN BUSCADOR DE HOTELES. Nada aquí sabe de hoteles, ferries ni precios: el compositor
pregunta «¿qué añadiría un experto de ESTE dominio, cuán ancho hay que buscar, cómo se juzga la calidad?» y esa
pregunta tiene la misma forma para una tesis de física cuántica (¿cuántos papers hay que leer antes de concluir?
¿qué hace que una fuente sea sólida?), para escribir un libro o para elegir una librería de software. El dominio
lo nombra el propio brief; la ESTRUCTURA de dirigir una investigación es la misma.

DÓNDE CORRE. En el pre-vuelo ASÍNCRONO de la escalada (`nucleo/dispatch.py`), nunca en el turno de voz: por eso
puede permitirse un modelo que razone. Si el compositor no está disponible o dice que esto no es una
investigación (cancelar una cita no necesita amplitud ni baremo), se devuelve None y el worker sale como siempre
— fail-open, la escalada NUNCA se cae por no tener brief.

RONDAS. El brief se PERSISTE con la tarea, así que «no me convence, sigue buscando» no vuelve a empezar de cero:
`expand()` sube la amplitud y añade ángulos nuevos sobre los MISMOS criterios ya acordados.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

logger = logging.getLogger("zaelar.research")

# El compositor corre ANTES de que el worker arranque, así que su latencia la paga el arranque de la tarea (no la
# voz: el operador ya sabe que esto tarda, y la escalada es asíncrona). Aun así va con TECHO DURO: si el proveedor
# se atasca, más vale un worker sin dirigir —que es como salía antes— que una tarea que no arranca. Vencido el
# plazo se sigue sin brief, con aviso.
_COMPOSE_TIMEOUT = 30.0

# Suelo de amplitud. Existe porque el sesgo del modelo, si le dejas el número, es pedir "10 candidatos" — que es
# otra vez la búsqueda superficial con otro nombre. Una SELECCIÓN («la mejor», «las 3 mejores») solo significa
# algo si detrás hay un conjunto del que elegir.
_MIN_CANDIDATES_FLOOR = 25
_MIN_CANDIDATES_CAP = 200
# CUÁNTAS se entregan. El defecto es DIEZ por decisión del operador (2026-08-12): con tres, una selección honesta
# se queda sin sitio para enseñar el segundo pelotón —lo que casi entra— y él no puede juzgar si el corte fue
# bueno; con diez ve la horquilla entera y elige. Si el operador PIDE un número ("dame tres", "ponme veinte"), ese
# número manda y sustituye al defecto: el brief lo recoge del propio encargo, no de aquí.
_N_FINAL_DEFAULT = 10
_N_FINAL_CAP = 20       # el tope antes era 10 y hacía INEXPRESABLE un "ponme veinte" del operador
_MAX_LIST = 12          # criterios/enriquecimientos/baremo: una lista que el worker pueda de verdad respetar
_MAX_ITEM_CHARS = 220
# El ROL de una pieza se pinta como INSIGNIA en la tarjeta («Hotel», «Ferry»), así que tiene que caber en una. El
# modelo, si le dejas, devuelve la descripción del contenido en vez del nombre del rol («Tarifa del ferry para 4
# pasajeros detallando cargos por altura»), y eso en una insignia rompe la tarjeta. El prompt lo pide corto; esto lo
# GARANTIZA, porque un prompt es una petición y un cap es un contrato.
_MAX_ROLE_CHARS = 28
_KV = "research_brief"  # memoria KV: <_KV>:<task_id>


# ── el catálogo CERRADO de lo que un brief puede decir (mismo criterio que evaluator.py: validar, no confiar) ──
def _strlist(raw, cap: int = _MAX_LIST, chars: int = _MAX_ITEM_CHARS) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for x in raw:
        s = str(x).strip()
        if s:
            out.append(s[:chars])
        if len(out) >= cap:
            break
    return out


_MAX_ROLE_WORDS = 3


def _roles(raw) -> list[str]:
    """Roles de las piezas de una propuesta compuesta. Cortos por contrato (van en una insignia) y sin duplicados:
    dos piezas con el mismo rol («Hotel» y «Hotel») no son una propuesta compuesta, son una lista mal montada.

    Se corta por PALABRA, nunca a mitad: «Tarifa de ferry para 4 pasajeros (detallando…)» → «Tarifa de ferry», que
    es una insignia legible; cortar por caracteres daba «Tarifa de ferry para 4 pasaj», que es basura en pantalla."""
    seen, out = set(), []
    for raw_role in _strlist(raw, cap=6, chars=200):
        # una frase descriptiva colada como rol se queda en su primera cláusula, que es donde está el nombre real
        r = raw_role.split("(")[0].split(",")[0].split(":")[0].strip(" -–—")
        words = [w for w in (r or raw_role).split() if w]
        r = " ".join(words[:_MAX_ROLE_WORDS])[:_MAX_ROLE_CHARS].strip(" -–—")
        k = r.lower()
        if r and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def parse(raw: str) -> dict | None:
    """JSON del compositor → brief validado. None si no hay JSON usable o si dice que esto no es investigación."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        p = json.loads(s[i:j + 1])
    except Exception:
        return None
    if not isinstance(p, dict):
        return None
    if not p.get("research"):
        return None                      # el propio modelo dice que esto no pide amplitud ni baremo

    breadth = p.get("breadth") if isinstance(p.get("breadth"), dict) else {}
    try:
        minc = int(breadth.get("min_candidates") or 0)
    except (TypeError, ValueError):
        minc = 0
    minc = max(_MIN_CANDIDATES_FLOOR, min(_MIN_CANDIDATES_CAP, minc))

    deliv = p.get("deliverable") if isinstance(p.get("deliverable"), dict) else {}
    try:
        nfin = int(deliv.get("n_final") or _N_FINAL_DEFAULT)
    except (TypeError, ValueError):
        nfin = _N_FINAL_DEFAULT
    nfin = max(1, min(_N_FINAL_CAP, nfin))

    brief = {
        "goal": str(p.get("goal") or "").strip()[:400],
        "domain": str(p.get("domain") or "").strip()[:120],
        "hard": _strlist(p.get("hard")),
        "soft": _strlist(p.get("soft")),
        "assumed": _strlist(p.get("assumed")),
        "enrichments": _strlist(p.get("enrichments")),
        "breadth": {"min_candidates": minc, "angles": _strlist(breadth.get("angles"))},
        "quality_bar": _strlist(p.get("quality_bar")),
        "deliverable": {
            "widget": str(deliv.get("widget") or "results").strip()[:40] or "results",
            "n_final": nfin,
            "composite": bool(deliv.get("composite")),
            "parts": _roles(deliv.get("parts")),
        },
        "round": 1,
        "ts": time.time(),
    }
    if not brief["goal"]:
        return None                      # sin objetivo reformulado no hay brief que dirigir nada
    return brief



# `_SYSTEM` moved to research_prompts.py (2026-08-17 modularization pass) — re-exported here so `build_messages`
# below keeps working unchanged, and so `research._SYSTEM` still resolves for anyone reading it that way.
from nucleo.research_prompts import _SYSTEM  # noqa: F401 — re-export + used by build_messages below
def build_messages(request: str, context: str = "", today: str = "") -> list[dict]:
    user = []
    if today:
        user.append(today)
    if context:
        user.append("LO QUE EL ASISTENTE YA SABE DEL OPERADOR (úsalo para no preguntar lo que ya consta, y para "
                    "afinar los criterios):\n" + context[:1500])
    user.append("PETICIÓN DEL OPERADOR (literal):\n" + (request or "").strip()[:3000])
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "\n\n".join(user)}]


def _spec():
    """Modelo del compositor. Va por la CADENA de proveedores del tier de razonamiento (misma que el cerebro de
    cluster): esto no es la ruta de voz, así que puede pensar — y si el proveedor principal está sin cuota, releva
    en vez de morir. `config §research.model` lo fuerza si el operador quiere uno concreto."""
    try:
        from config import v2 as _v2
        cfg = _v2.get("research") or {}
    except Exception:
        cfg = {}
    model = str(cfg.get("model") or "").strip()
    base = str(cfg.get("base_url") or "").strip()
    if model and base:
        from nucleo.flash.fast_client import ModelSpec
        return ModelSpec(model=model, base_url=base, api_key=str(cfg.get("api_key") or ""))
    from nucleo.flash import provider_chain
    tier = provider_chain.pick()
    return provider_chain.spec_for(tier) if tier else None


def enabled() -> bool:
    """Kill-switch de 1ª clase: env ZAELAR_RESEARCH (0 apaga) + config §research.enabled (UI). Mismo patrón que el
    Susurro. Apagado = las escaladas salen sin dirigir, exactamente como antes de que esto existiera."""
    if (os.getenv("ZAELAR_RESEARCH", "1") or "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        from config import v2 as _v2
        v = (_v2.get("research") or {}).get("enabled", True)
    except Exception:
        return True
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off")
    return bool(v)


class ComposerUnavailable(Exception):
    """El compositor NO PUDO contestar (timeout, sin proveedor, respuesta ilegible) — distinto de que contestara
    «esto no es una investigación».

    Existen como dos cosas separadas porque `None` para ambas costó una tarea entera (banco del 2026-08-13). El
    fail-open es correcto —mejor arrancar sin dirigir que no arrancar— pero tenía un coste OCULTO: `dispatch`
    promociona el kind a `research` (1200 s) solo cuando HAY brief, así que un compositor caído dejaba además la
    tarea en `generic` = 600 s. El worker murió conminado a «entrega ya» a los 704 s con el navegador a medias,
    que es EXACTAMENTE el síntoma que la promoción de kind existe para cerrar. Perder el brief tiene que costar
    DIRECCIÓN, nunca TIEMPO: que la petición sea una investigación no depende de que el compositor esté vivo."""


def _declined(raw: str) -> bool:
    """¿El compositor CONTESTÓ que esto no es una investigación? (frente a no haber podido contestar). Solo cuenta
    como decisión suya si su JSON llegó entero y legible con `research` en falso."""
    s = (raw or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return False
    try:
        p = json.loads(s[i:j + 1])
    except Exception:
        return False
    return isinstance(p, dict) and not p.get("research")


async def compose(request: str, context: str = "", *, timeout: float = _COMPOSE_TIMEOUT) -> dict | None:
    """Petición cruda → brief estructurado. `None` = el compositor dijo que **no es una investigación**;
    `ComposerUnavailable` = no pudo contestar (ver esa clase: la diferencia vale medio presupuesto).

    FAIL-OPEN Y RUIDOSO: sin brief el worker sale exactamente como salía antes (no se pierde la escalada), pero se
    registra el motivo — un fail-open silencioso aquí escondería que TODAS las búsquedas volvieron a ser
    superficiales, que es justo el fallo que este módulo existe para cerrar."""
    req = (request or "").strip()
    if not req or not enabled():
        return None
    try:
        from nucleo.flash.fast_client import FastClient
        spec = _spec()
        if spec is None:
            logger.warning("research: sin proveedor disponible para el compositor — el worker sale SIN brief")
            raise ComposerUnavailable("sin proveedor")
        from nucleo.dispatch_prompts import _today_block  # V2-098: canonical home, moved out of dispatch.py
        out = await asyncio.wait_for(
            FastClient().complete(build_messages(req, context, _today_block()), spec=spec, max_tokens=1600),
            timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"research: el compositor no contestó en {timeout:.0f}s — el worker arranca SIN brief "
                       "(búsqueda sin dirigir); mejor eso que dejar la tarea sin salir")
        raise ComposerUnavailable("timeout") from None
    except ComposerUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"research: el compositor falló ({e}) — el worker sale SIN brief (búsqueda sin dirigir)")
        raise ComposerUnavailable(str(e)) from None
    brief = parse(out)
    if brief is None:
        if _declined(out):
            return None                   # decisión SUYA: no pide amplitud ni baremo → presupuesto normal
        logger.warning("research: el compositor contestó algo ilegible — el worker sale SIN brief")
        raise ComposerUnavailable("respuesta ilegible")
    brief["request"] = req[:600]
    return brief


def expand(brief: dict, *, note: str = "") -> dict:
    """Siguiente RONDA sobre el MISMO brief: «no me convence, sigue buscando». Sube la amplitud (el conjunto
    anterior ya se demostró insuficiente) y deja constancia de qué pidió el operador al rechazarlo, sin tocar los
    criterios ya acordados — reabrir los criterios sería empezar otra búsqueda, no continuar esta."""
    nxt = json.loads(json.dumps(brief))          # copia honda: la ronda anterior queda intacta en su registro
    nxt["round"] = int(brief.get("round") or 1) + 1
    b = nxt.setdefault("breadth", {})
    try:
        cur = int(b.get("min_candidates") or _MIN_CANDIDATES_FLOOR)
    except (TypeError, ValueError):
        cur = _MIN_CANDIDATES_FLOOR
    b["min_candidates"] = min(_MIN_CANDIDATES_CAP, max(cur * 2, cur + 20))
    if note.strip():
        nxt.setdefault("feedback", []).append(note.strip()[:_MAX_ITEM_CHARS])
    nxt["ts"] = time.time()
    return nxt


def to_criteria(brief: dict) -> dict:
    """El brief traducido al payload de la pestaña CRITERIOS de la hoja de resultados.

    Por qué existe: los criterios con los que se está buscando eran, hasta hoy, algo que solo se podía PREGUNTAR
    («¿qué has entendido?») y por tanto no se podía comprobar de un vistazo. Se siembran desde AQUÍ, en el
    pre-vuelo, y no desde el worker: si dependieran de que el ejecutor se acuerde de escribirlos, faltarían justo
    en las búsquedas que peor van. `goal` hace además de firma del encargo — un objetivo distinto vacía la hoja de
    la búsqueda anterior, y una ronda 2 (que conserva el objetivo) no borra nada."""
    if not isinstance(brief, dict) or not brief.get("goal"):
        return {}
    b = brief.get("breadth") or {}
    d = brief.get("deliverable") or {}
    out = {"goal": brief["goal"], "round": int(brief.get("round") or 1)}
    if brief.get("domain"):
        out["domain"] = brief["domain"]
    for k in ("hard", "soft", "assumed", "enrichments", "quality_bar"):
        if brief.get(k):
            out[k] = list(brief[k])
    if brief.get("feedback"):
        out["changes"] = list(brief["feedback"])     # lo que el operador corrigió al rechazar la ronda anterior
    if b.get("min_candidates"):
        out["min_candidates"] = b["min_candidates"]
    if d.get("n_final"):
        out["n_final"] = d["n_final"]
    return out




# `to_prompt_block`'s actual formatting logic moved to research_prompts.py (same split as `_SYSTEM` above) — this
# thin wrapper keeps `_MIN_CANDIDATES_FLOOR` single-sourced here (the constant `parse()`/`expand()` above also
# use) while research_prompts.py stays a leaf module with zero import of this file, avoiding a circular import.
def to_prompt_block(brief: dict) -> str:
    from nucleo.research_prompts import to_prompt_block as _to_prompt_block_impl
    return _to_prompt_block_impl(brief, _MIN_CANDIDATES_FLOOR)
def save(task_id, brief: dict) -> None:
    if not brief:
        return
    try:
        from memory import api as memory
        memory.kv_set(f"{_KV}:{task_id}", brief)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"research: no pude persistir el brief de {task_id} ({e})")


def load(task_id) -> dict | None:
    try:
        from memory import api as memory
        out = memory.kv_get(f"{_KV}:{task_id}")
        return out if isinstance(out, dict) and out.get("goal") else None
    except Exception:
        return None


# ── RONDAS por OBJETIVO: «no me convence, sigue buscando» continúa, no reempieza ───────────────────────────────
# Indexado por la firma del objetivo (no por task_id) porque quien pide la continuación es el OPERADOR hablando,
# y su segunda frase es una tarea nueva sin ninguna referencia a la primera. Casando por objetivo, «busca más
# hoteles, esos no me valen» hereda los criterios YA acordados y solo sube la amplitud — el operador no tiene que
# repetir las fechas, los niños ni el tamaño del coche.
#
# DELIBERADO: si el operador vuelve a pedir lo MISMO dentro del TTL, se trata como continuación (ronda 2), no como
# búsqueda nueva. Pedir dos veces lo mismo significa que la primera respuesta no sirvió, así que buscar MÁS ancho
# es la lectura correcta; y el TTL acota el efecto para que dentro de una semana sea otra búsqueda desde cero.
_KV_ROUND = "research_rounds"     # UN registro con todas las rondas vivas (el casado es difuso, no por clave)
_ROUND_TTL = 6 * 3600
_ROUND_MATCH = 0.5                # mismo umbral de solape que la reanudación web (`dispatch._find_resume`)
_ROUND_MAX = 40                   # cota del registro: investigaciones vivas, no un histórico


def _rounds() -> dict:
    try:
        from memory import api as memory
        out = memory.kv_get(_KV_ROUND)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def remember_round(goal_key: str, brief: dict) -> None:
    if not goal_key or not brief:
        return
    try:
        from memory import api as memory
        now = time.time()
        reg = {k: v for k, v in _rounds().items()
               if isinstance(v, dict) and now - float(v.get("ts") or 0) <= _ROUND_TTL}
        reg[goal_key] = {"brief": brief, "ts": now}
        if len(reg) > _ROUND_MAX:                     # las más viejas primero
            reg = dict(sorted(reg.items(), key=lambda kv: -float(kv[1].get("ts") or 0))[:_ROUND_MAX])
        memory.kv_set(_KV_ROUND, reg)
    except Exception:
        pass


def previous_round(goal_key: str) -> dict | None:
    """Brief de la investigación viva que MEJOR casa con este objetivo, o None si es una búsqueda nueva.

    El casado es DIFUSO (solape de palabras de contenido ≥0.5) y no exacto, porque la frase con la que el operador
    pide continuar nunca es la misma que la inicial: «busca vacaciones en Baleares…» y luego «esos no me valen,
    sigue buscando» comparten el objetivo pero no el texto. Con casado exacto la continuación se leía como búsqueda
    nueva y repetía la ronda 1 con la misma amplitud — es decir, le devolvía al operador lo mismo que acababa de
    rechazar."""
    want = set((goal_key or "").split())
    if not want:
        return None
    now = time.time()
    best, best_score = None, 0.0
    for key, ent in _rounds().items():
        if not isinstance(ent, dict) or now - float(ent.get("ts") or 0) > _ROUND_TTL:
            continue
        other = set(str(key).split())
        union = len(want | other)
        score = (len(want & other) / union) if union else 0.0
        if score >= _ROUND_MATCH and score > best_score:
            b = ent.get("brief")
            if isinstance(b, dict) and b.get("goal"):
                best, best_score = b, score
    return best
