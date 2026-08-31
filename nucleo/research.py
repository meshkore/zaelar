"""nucleo/research.py — the RESEARCH BRIEF: how a search is DIRECTED, not how it is executed.

THE PROBLEM IT SOLVES (operator, 2026-08-09). Asking for “the best holiday options in the Balearic Islands” and
receiving three results is trivial: anyone can enter a website, set two filters, and copy the first three. What the
operator expects from an assistant is what a competent person would do: inspect FORTY options, read the reviews,
check in the PHOTOS that the pool is genuinely large, and only then propose three. The difference is not in the
worker’s tools — it already knows how to browse and extract — but in the fact that NOBODY was telling it how broadly
to search or by what standard to judge. The worker received free-form prose and imposed its own criterion, so it did
the minimum that satisfied the literal wording.

THE COMPONENT. Between “the operator asks” and “the worker starts”, a structured BRIEF is composed that fixes:
  · criterios DUROS (lo que descalifica) y BLANDOS (lo que puntúa) separados — un blando tratado como duro deja
    la búsqueda sin resultados; un duro tratado como blando entrega algo que no sirve;
  · lo ASUMIDO cuando el operador no lo dijo, explícito para poder contárselo en vez de fingir que lo sabíamos;
  · ENRIQUECIMIENTOS: lo que un experto del dominio añade y el operador no pensó en pedir (van en coche → hace
    falta parking; niños de 9 y 11 → toboganes puntúan, piscina de bebés no);
  · AMPLITUD: cuántos candidatos hay que reunir ANTES de descartar, y por cuántos ÁNGULOS distintos buscar;
  · BARERO DE CALIDAD: qué hay que verificar de verdad para que un finalista cuente como verificado;
  · ENTREGABLE: la forma de la respuesta en pantalla (cuántas propuestas, de qué piezas se compone cada una).

WHY IT IS GENERIC AND NOT A HOTEL SEARCHER. Nothing here knows about hotels, ferries, or prices: the composer
pregunta «¿qué añadiría un experto de ESTE dominio, cuán ancho hay que buscar, cómo se juzga la calidad?» y esa
pregunta tiene la misma forma para una tesis de física cuántica (¿cuántos papers hay que leer antes de concluir?
¿qué hace que una fuente sea sólida?), para escribir un libro o para elegir una librería de software. El dominio
lo nombra el propio brief; la ESTRUCTURA de dirigir una investigación es la misma.

WHERE IT RUNS. In the ASYNCHRONOUS pre-flight of the escalation (`nucleo/dispatch.py`), never during the voice turn: therefore
puede permitirse un modelo que razone. Si el compositor no está disponible o dice que esto no es una
investigación (cancelar una cita no necesita amplitud ni baremo), se devuelve None y el worker sale como siempre
— fail-open, la escalada NUNCA se cae por no tener brief.

ROUNDS. The brief is PERSISTED with the task, so “I’m not convinced, keep searching” does not start from zero:
`expand()` sube la amplitud y añade ángulos nuevos sobre los MISMOS criterios ya acordados.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

logger = logging.getLogger("zaelar.research")

# V2-301 changed what this ceiling protects. The composer ran BEFORE the spawn, so its latency delayed
# task startup and 30 s was the tolerable maximum — and it was NOT enough: measured on 2026-08-24 during the guitar
# la guitarra, el compositor (tier razonador, 1600 tokens) venció ese plazo en 3 de 7 rondas, y LAS DOS rondas
# que fallaron son exactamente las que corrieron sin brief. Desde V2-301 compone EN PARALELO con el worker (el
# spawn ya no espera; el brief tardío llega inyectado), así que el plazo ya no compra arranque — solo decide
# cuánto se persiste en conseguir dirección para una búsqueda que sigue en marcha. Un brief a los 60-90 s
# todavía llega ANTES de que el worker evalúe candidatos, que es donde la dirección importa. El techo duro se
# conserva (un proveedor colgado no puede retener la referencia para siempre); solo cambia el número.
# ⚠️ Con el kill-switch serial (ZAELAR_BRIEF_HEAD_START_S=0) este plazo vuelve a pagarse en el arranque.
_COMPOSE_TIMEOUT = float(os.environ.get("ZAELAR_COMPOSE_TIMEOUT_S", "90") or 90)

# Breadth floor. It exists because the model’s bias, if allowed to choose the number, is to ask for “10 candidates” — which is
# superficial search under another name. A SELECTION (“the best”, “the 3 best”) only means
# algo si detrás hay un conjunto del que elegir.
_MIN_CANDIDATES_FLOOR = 25
_MIN_CANDIDATES_CAP = 200
# HOW MANY are delivered. The default is TEN by operator decision (2026-08-12): with three, an honest selection
# se queda sin sitio para enseñar el segundo pelotón —lo que casi entra— y él no puede juzgar si el corte fue
# bueno; con diez ve la horquilla entera y elige. Si el operador PIDE un número ("dame tres", "ponme veinte"), ese
# número manda y sustituye al defecto: el brief lo recoge del propio encargo, no de aquí.
_N_FINAL_DEFAULT = 10
_N_FINAL_CAP = 20       # el tope antes era 10 y hacía INEXPRESABLE un "ponme veinte" del operador
_MAX_LIST = 12          # criterios/enriquecimientos/baremo: una lista que el worker pueda de verdad respetar
_MAX_ITEM_CHARS = 220
# El ROL de una pieza se pinta como INSIGNIA en la tarjeta («Hotel», «Ferry»), así que tiene que caber en una. El
# modelo, si le dejas, devuelve la descripción del contenido en vez del nombre del rol («Tarifa del ferry para 4
# passengers detailing charges by height”), which breaks the card as a badge. The prompt asks for it to be short; this
# GARANTIZA, porque un prompt es una petición y un cap es un contrato.
_MAX_ROLE_CHARS = 28
_KV = "research_brief"  # memoria KV: <_KV>:<task_id>


# ── the CLOSED catalog of what a brief may say (same principle as evaluator.py: validate, do not trust) ──
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
    """Roles of the parts of a composite proposal. Short by contract (they appear on a badge) and without duplicates:
    two parts with the same role (“Hotel” and “Hotel”) are not a composite proposal; they are a malformed list.

    It is cut by WORD, never midway: “Ferry fare for 4 passengers (detailing…)” → “Ferry fare”, which is a readable
    badge; cutting by characters would produce “Ferry fare for 4 passe”, which is unusable on screen."""
    seen, out = set(), []
    for raw_role in _strlist(raw, cap=6, chars=200):
        # A descriptive phrase masquerading as a role is reduced to its first clause, where the real name is.
        r = raw_role.split("(")[0].split(",")[0].split(":")[0].strip(" -–—")
        words = [w for w in (r or raw_role).split() if w]
        r = " ".join(words[:_MAX_ROLE_WORDS])[:_MAX_ROLE_CHARS].strip(" -–—")
        k = r.lower()
        if r and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def parse(raw: str) -> dict | None:
    """Composer JSON → validated brief. None if there is no usable JSON or it says this is not research."""
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
        return None                      # the model itself says this requires neither breadth nor a quality bar

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
        return None                      # without a restated objective there is no brief to direct anything
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
    """Composer model. It uses the reasoning-tier provider CHAIN (the same one as the cluster brain):
    this is not the voice path, so it can think — and if the primary provider is out of quota, it relays instead of
    dying. `config §research.model` forces it when the operator wants a specific one."""
    try:
        from config import v2 as _v2
        cfg = _v2.get("research") or {}
    except Exception:
        cfg = {}
    model = str(cfg.get("model") or "").strip()
    base = str(cfg.get("base_url") or "").strip()
    if model and base:
        from nucleo.flash.fast_client import ModelSpec
        # Pinned by the operator: NOT a chain pick, so a failure here must not put a chain tier on cooldown.
        return ModelSpec(model=model, base_url=base, api_key=str(cfg.get("api_key") or "")), None
    from nucleo.flash import provider_chain
    tier = provider_chain.pick()
    return (provider_chain.spec_for(tier) if tier else None), tier


def _note_provider_failure(exc: Exception, tier):
    """Tell the CHAIN that this tier just died, and return the relay tier (or None to give up).

    V2-225 — the composer read the chain (`_spec` → `pick()`) and never wrote to it. `note_failure()` had exactly
    ONE production caller in the whole tree (`connectors/meshkore/brain.py`), so the cooldown that makes the relay
    fire was only ever set when the CLUSTER brain happened to fail through the same provider first. The composer
    lived off that coincidence, and when it ran out it just re-picked the dead tier forever.

    Measured by the harness over two rounds of `hotel-under-15-days` (2026-08-20): at 20:01, 20:07 and 20:10 the
    same exhausted provider was chosen all three times, two FastClient retries each, and the worker went out
    blind after each one —

        research: el compositor falló (429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at
        2026-08-25 01:39:02]) — el worker sale SIN brief (búsqueda sin dirigir)

    That message is precisely the shape `classify_failure` reads as `exhausted` WITH a reset date, which is the
    case that puts a cooldown on and returns a relay. Nothing was missing from the mechanism; nobody was calling
    it. Until 2026-08-25 that meant EVERY research escalation went out undirected — which is why a round's best
    «result» was a €25 flamenco show.

    A pinned model (`tier is None`) is never reported: the operator chose it, and a cooldown on a chain tier the
    composer did not use would relay the cluster brain for someone else's fault.

    The FAIL-OPEN stays exactly as it was: if there is no relay, the exception travels and the worker leaves
    without a brief. This only adds the line that marks the provider before giving up.
    """
    if tier is None:
        return None
    try:
        from nucleo.flash import provider_chain
        nxt = provider_chain.note_failure(str(exc), tier=tier)
        return nxt if (nxt or {}).get("base_url") and nxt.get("name") != tier.get("name") else None
    except Exception:  # noqa: BLE001
        return None


def enabled() -> bool:
    """First-class kill switch: env ZAELAR_RESEARCH (0 disables) + config §research.enabled (UI). Same pattern as
    Whisper. Disabled = escalations run without direction, exactly as before this existed."""
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
    """The composer COULD NOT answer (timeout, no provider, unreadable response) — distinct from answering
    “this is not research”.

    Existen como dos cosas separadas porque `None` para ambas costó una tarea entera (banco del 2026-08-13). El
    fail-open es correcto —mejor arrancar sin dirigir que no arrancar— pero tenía un coste OCULTO: `dispatch`
    promociona el kind a `research` (1200 s) solo cuando HAY brief, así que un compositor caído dejaba además la
    tarea en `generic` = 600 s. El worker murió conminado a «entrega ya» a los 704 s con el navegador a medias,
    que es EXACTAMENTE el síntoma que la promoción de kind existe para cerrar. Perder el brief tiene que costar
    DIRECTION, never TIME: whether the request is research must not depend on the composer being alive."""


def _declined(raw: str) -> bool:
    """Did the composer ANSWER that this is not research? (as opposed to being unable to answer). It only counts as
    its decision if its JSON arrived complete and readable with `research` false."""
    s = (raw or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return False
    try:
        p = json.loads(s[i:j + 1])
    except Exception:
        return False
    return isinstance(p, dict) and not p.get("research")


# V2-488 · a model that CANNOT disable reasoning silently broke ALL directed searches.
#
# Medido en el plató US el 2026-08-29, en las dos rondas del hotel (20:03:02 y 20:40:36), idéntico:
#
#     research: el compositor falló (Error code: 400 - {'error': {'code': '1210', 'message': 'This model
#     always engages in thinking and cannot be disabled; please use low, high, or max'}})
#     — el worker sale SIN brief (búsqueda sin dirigir)
#
# Y no relevaba: un 400 de parámetro no es una caída de proveedor, así que `classify_failure` no da tier de
# relevo y la excepción viaja hasta el fail-open. O sea que el motor DEGRADABA a búsqueda ciega —justo lo que
# este módulo existe para cerrar— cada vez que la cadena elegía un razonador puro, y lo hacía por una línea
# nuestra, no por el proveedor.
#
# Es la tercera cara de la misma lección ya escrita en el reparto de modelos: **la capacidad se MIDE, no se
# lee**. `no_thinking` se envía como si todo modelo pudiera; el que no puede lo dice con un 400 clarísimo y
# hasta con la lista de valores que admite.
def _no_puede_dejar_de_pensar(exc: Exception) -> bool:
    """Has the provider rejected the REQUEST not to reason (as opposed to having failed)?

    It is read from the message because that is where it appears: the client wraps the 400 body in the
    exception text. The conjunction is required —mentioning reasoning AND that it cannot be disabled— to avoid
    confusing it with another 400; proprietary code `1210` is sufficient on its own.
    """
    t = str(exc or "").lower()
    if "1210" in t:
        return True
    habla_de_razonar = ("thinking" in t) or ("reasoning" in t) or ("razona" in t)
    no_se_puede = ("cannot be disabled" in t) or ("can not be disabled" in t) or ("cannot disable" in t)
    return habla_de_razonar and no_se_puede


async def compose(request: str, context: str = "", *, timeout: float = _COMPOSE_TIMEOUT) -> dict | None:
    """Raw request → structured brief. `None` = the composer said **this is not research**;
    `ComposerUnavailable` = it could not answer (see that class: the distinction is worth half the budget).

    FAIL-OPEN AND LOUD: without a brief the worker exits exactly as it did before (the escalation is not lost), but
    the reason is recorded — a silent fail-open here would hide that ALL searches had become superficial again,
    precisely the failure this module exists to prevent."""
    req = (request or "").strip()
    if not req or not enabled():
        return None
    try:
        from nucleo.flash.fast_client import FastClient
        spec, tier = _spec()
        if spec is None:
            logger.warning("research: sin proveedor disponible para el compositor — el worker sale SIN brief")
            raise ComposerUnavailable("sin proveedor")
        from nucleo.dispatch_prompts import _today_block  # V2-098: canonical home, moved out of dispatch.py
        _msgs = build_messages(req, context, _today_block())
        # `no_thinking`: the composer wants the BRIEF, not the deliberation. Measured 2026-08-27 against the
        # reasoning tier (Z.AI GLM): with thinking on, the block is charged against `max_tokens`, so 1.600
        # came back truncated and unparseable — logged as «respuesta ilegible», which reads like a broken
        # model and was really a budget that never fit. Raising the budget works but costs 67,7 s and 2.517
        # output tokens; switching thinking off produces the same parseable brief in 22,3 s and 681 tokens.
        # The worker cannot start until this returns, so the seconds are the person's, not ours.
        async def _pedir(_spec_, *, pensando: bool = False):
            """One gateway for both calls (the normal one and the relay): the fix below had to apply to both,
            and a rule written twice is liable to leave its second copy behind."""
            if pensando:
                # V2-488: si el modelo NO PUEDE apagar el razonamiento, apagarlo no es una opción — y entonces
                # el presupuesto tiene que caber la deliberación, que es exactamente lo que midió el comentario
                # de arriba (2.517 tokens de salida con thinking puesto). Con 1.600 vuelve truncado.
                return await asyncio.wait_for(
                    FastClient().complete(_msgs, spec=_spec_, max_tokens=3200), timeout=timeout)
            return await asyncio.wait_for(
                FastClient().complete(_msgs, spec=_spec_, max_tokens=1600, no_thinking=True), timeout=timeout)

        try:
            try:
                out = await _pedir(spec)
            except Exception as e:  # noqa: BLE001
                if not _no_puede_dejar_de_pensar(e):
                    raise
                # This is not a provider failure: we asked for something that model does not support. Marking the tier
                # como caído aquí lo pondría en cuarentena por culpa NUESTRA, y el relevo iría a otro modelo
                # cuando el que hay sirve perfectamente.
                logger.warning("research: el modelo del compositor no puede apagar el razonamiento — "
                               "reintento CON razonamiento y presupuesto para él")
                out = await _pedir(spec, pensando=True)
        except asyncio.TimeoutError:
            raise
        except Exception as e:  # noqa: BLE001
            # V2-225 — the composer READ the chain and never WROTE to it, so its relay could not trigger.
            _relay = _note_provider_failure(e, tier)
            if _relay is None:
                raise
            logger.warning(f"research: el compositor releva a {_relay.get('name')} tras «{str(e)[:80]}»")
            from nucleo.flash import provider_chain as _pc_retry
            _spec_relay = _pc_retry.spec_for(_relay)
            try:
                out = await _pedir(_spec_relay)
            except Exception as e2:  # noqa: BLE001
                if not _no_puede_dejar_de_pensar(e2):
                    raise
                out = await _pedir(_spec_relay, pensando=True)
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
    """Next ROUND on the SAME brief: “I’m not convinced, keep searching”. It increases breadth (the previous set
    has already proved insufficient) and records what the operator requested when rejecting it, without touching the
    agreed criteria — reopening the criteria would start another search, not continue this one."""
    nxt = json.loads(json.dumps(brief))          # deep copy: the previous round remains intact in its record
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
    """The brief translated into the payload for the CRITERIA tab of the results sheet.

    Why it exists: until now, the criteria being used for the search were something that could only be ASKED
    («¿qué has entendido?») y por tanto no se podía comprobar de un vistazo. Se siembran desde AQUÍ, en el
    pre-vuelo, y no desde el worker: si dependieran de que el ejecutor se acuerde de escribirlos, faltarían justo
    en las búsquedas que peor van. `goal` hace además de firma del encargo — un objetivo distinto vacía la hoja de
    the previous search, and round 2 (which preserves the objective) deletes nothing."""
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
        out["changes"] = list(brief["feedback"])     # what the operator corrected when rejecting the previous round
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


# ── ROUNDS by OBJECTIVE: “I’m not convinced, keep searching” continues; it does not restart ───────────────────
# Indexado por la firma del objetivo (no por task_id) porque quien pide la continuación es el OPERADOR hablando,
# y su segunda frase es una tarea nueva sin ninguna referencia a la primera. Casando por objetivo, «busca más
# hoteles, esos no me valen» hereda los criterios YA acordados y solo sube la amplitud — el operador no tiene que
# repetir las fechas, los niños ni el tamaño del coche.
#
# DELIBERATE: if the operator asks for the SAME thing again within the TTL, it is treated as a continuation (round 2), not as a
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
        if len(reg) > _ROUND_MAX:                     # oldest first
            reg = dict(sorted(reg.items(), key=lambda kv: -float(kv[1].get("ts") or 0))[:_ROUND_MAX])
        memory.kv_set(_KV_ROUND, reg)
    except Exception:
        pass


def previous_round(goal_key: str) -> dict | None:
    """Brief of the live investigation that BEST matches this objective, or None if this is a new search.

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
