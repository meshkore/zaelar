"""nucleo/workers/brief.py — the RESEARCH BRIEF: how a search is DIRECTED, not how it is executed.

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

WHERE IT RUNS. In the errand's ASYNCHRONOUS pre-flight (`nucleo/dispatch/`), never in the voice turn, so it may use a
reasoning model. No composer, or «this is not research» → None, and the worker starts as always (fail-open).

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

# V2-301 changed what this ceiling protects. Measured 2026-08-24 (guitar search): the composer (reasoning tier,
# 1600 tokens) missed 30 s in 3 of 7 rounds — the two failed rounds ran without a brief. It now composes IN PARALLEL
# with the worker (a late brief is injected), so the ceiling only bounds how long we persist; a hard cap remains.
# ⚠️ With the serial kill-switch (ZAELAR_BRIEF_HEAD_START_S=0) this wait is paid at startup again.
_COMPOSE_TIMEOUT = float(os.environ.get("ZAELAR_COMPOSE_TIMEOUT_S", "90") or 90)

_KV = "research_brief"  # memoria KV: <_KV>:<task_id>


_MAX_ROLE_WORDS = 3


# `_SYSTEM` moved to research_prompts.py (2026-08-17 modularization pass) — re-exported here so `build_messages`
# below keeps working unchanged, and so `research._SYSTEM` still resolves for anyone reading it that way.
from nucleo.workers.prompts.research import _SYSTEM  # noqa: F401 — re-export + used by build_messages below


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
        from nucleo.llm.fast_client import ModelSpec
        # Pinned by the operator: NOT a chain pick, so a failure here must not put a chain tier on cooldown.
        return ModelSpec(model=model, base_url=base, api_key=str(cfg.get("api_key") or "")), None
    from nucleo.llm import provider_chain
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
        from nucleo.llm import provider_chain
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


# V2-488 · a model that CANNOT disable reasoning silently broke ALL directed searches. Measured 2026-08-29 (US set,
# hotel rounds 20:03:02 and 20:40:36): `400 code 1210 «always engages in thinking and cannot be disabled»`, no relay
# (a parameter 400 is not an outage), so the worker went out WITHOUT a brief. A capability is MEASURED, not read.
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
        from nucleo.llm.fast_client import FastClient
        spec, tier = _spec()
        if spec is None:
            logger.warning("research: sin proveedor disponible para el compositor — el worker sale SIN brief")
            raise ComposerUnavailable("sin proveedor")
        from nucleo.workers.prompts.context import _today_block  # V2-098: canonical home, moved out of dispatch.py
        _msgs = build_messages(req, context, _today_block())
        # `no_thinking`: the composer wants the BRIEF, not the deliberation. Measured 2026-08-27 (Z.AI GLM): with
        # thinking, 1.600 `max_tokens` came back truncated («respuesta ilegible»); a bigger budget costs 67,7 s and
        # 2.517 tokens, thinking off gives the same brief in 22,3 s / 681 tokens. The worker waits on this.
        async def _pedir(_spec_, *, pensando: bool = False):
            """One gateway for both calls (the normal one and the relay): the fix below had to apply to both,
            and a rule written twice is liable to leave its second copy behind."""
            if pensando:
                # V2-488: a model that CANNOT turn reasoning off needs the budget to fit it (2.517 output tokens
                # measured above); 1.600 comes back truncated.
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
                # Not a provider failure: we asked for something that model does not support. Marking the tier down
                # would quarantine it for OUR fault and relay away from a model that works.
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
            from nucleo.llm import provider_chain as _pc_retry
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
    brief = parse(out, request=req)
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


from nucleo.workers.brief_parse import (  # noqa: E402,F401
    _MIN_CANDIDATES_FLOOR, _MIN_CANDIDATES_CAP, _N_FINAL_DEFAULT, _N_FINAL_CAP, _MAX_LIST, _MAX_ITEM_CHARS,
    _MAX_ROLE_CHARS, _strlist, _roles, parse, _said_breadth, build_messages)
from nucleo.workers.brief_store import (  # noqa: E402,F401
    to_criteria, seed_criteria, to_prompt_block, save, load, _KV_ROUND, _ROUND_TTL, _ROUND_MATCH, _ROUND_MAX,
    _rounds, remember_round, previous_round)
