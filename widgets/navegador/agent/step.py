"""One model call of the automator (`_next_action`), the summary of a results page, and the module's
self-description. Names are read through the package (`_f.<name>`).
"""

import json

from loguru import logger
from openai import AsyncOpenAI

from widgets.navegador import agent as _f

_client: AsyncOpenAI | None = None


def _c() -> AsyncOpenAI:
    global _client
    # Asked on EVERY step, not only when the client is built: the client is cached for the life of the process,
    # so the egress gate in `llm_egress.route` below would otherwise see the first call and none of the rest.
    from nucleo import energy_lease, llm_egress
    if not llm_egress.is_local_endpoint(_f._base_url()):
        energy_lease.admit("llm")
    if _client is None:
        key = _f._api_key()
        if not key:
            raise RuntimeError("no NAVEGADOR_AGENT_API_KEY/AIMLAPI_KEY para el automatizador del navegador")
        # EGRESS (T304): the system's most frequent caller (one per navigation step) goes through mediated keys.
        from nucleo import llm_egress
        base, key, extra = llm_egress.route(_f._base_url(), key)
        if not key:
            raise RuntimeError("sin credencial para el automatizador del navegador")
        headers = dict(extra)
        # Browser UA is for Cloudflare in front of AIMLAPI. With mediated egress, the far end talks to AIMLAPI, so
        # it is unnecessary here.
        if not extra and "aimlapi" in base.lower():
            headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        _client = AsyncOpenAI(api_key=key, base_url=base, default_headers=headers or None)
    return _client


def _meter(resp, model: str) -> None:
    """Report to Energy the cost of one call in this loop — the system's most frequent caller (one per navigation
    step). Best-effort: metering must never bring down a running task."""
    try:
        from nucleo import energy_meter as _energy
        u = getattr(resp, "usage", None)
        _energy.report_llm_usage(
            base_url=_f._base_url(), model=model,
            prompt_tokens=getattr(u, "prompt_tokens", None),
            completion_tokens=getattr(u, "completion_tokens", None),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"navegador agent: metering failed (non-fatal): {e}")


async def _next_action(messages: list[dict], tools: list[dict], strong: bool = False) -> tuple[str | None, dict]:
    """One model call -> one action (function call). Bounded message window to avoid growth.
    `tools` = _TOOLS (DOM, by refs) or _VISION_TOOLS (vision, by coordinates). `strong`=True uses the ADVANCED model
    (third anti-stuck rung) if configured; if the advanced model fails (invalid id/provider), fall back to cheap."""
    head = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    trimmed = head + rest[-10:]
    model = _f._model_strong() if (strong and _f._model_strong()) else _f._model()

    async def _call(mdl):
        r = await _f._c().chat.completions.create(
            model=mdl, messages=trimmed, tools=tools, tool_choice="required", max_tokens=400, temperature=0)
        _f._meter(r, mdl)                                      # actual model for this call, not the requested one
        return r
    try:
        resp = await _call(model)
    except Exception as e:
        if model != _f._model():                              # advanced failed -> degrade to cheap for this step
            logger.warning(f"advanced model ({model}) failed: {e}; using cheap model")
            resp = await _call(_f._model())
        else:
            raise
    choice = resp.choices[0].message
    # V2-253 — UNREADABLE ARGUMENTS ARE NOT AN ACTION WITHOUT ARGUMENTS: acting on `{}` clicks without a ref or
    # navigates without a URL. A limit is dangerous only if the reader accepts PREFIXES; this one needs the full JSON.
    _cortado = str(getattr(resp.choices[0], "finish_reason", "") or "") == "length"
    for tc in (choice.tool_calls or []):
        _crudo = tc.function.arguments or "{}"
        try:
            return tc.function.name, json.loads(_crudo)
        except Exception:  # noqa: BLE001
            # Distinguish what caused the failure: the limit is OURS and is fixed by raising it; invalid arguments
            # are the model's and are fixed by retrying. Saying "emitted no action" obscures both cases.
            _por = ("se cortó por el tope de tokens" if _cortado else "devolvió argumentos ilegibles")
            logger.warning(f"navegador agent: «{tc.function.name}» {_por} ({len(_crudo)} chars) — no se ejecuta")
            # V2-255 — reported through the channel that already exists: the same `tool_dropped` event shape
            # FlashBrain emits (V2-171), so consumers that already handle it see it here too.
            try:
                from voice.observer import emit as _emit_obs
                _emit_obs("tool_dropped", "⚠️ acción descartada",
                          text=f"{tc.function.name}: {_por}",
                          extra={"tool": tc.function.name, "reason": _por, "where": "navegador",
                                 "finish_reason": "length" if _cortado else "",
                                 "chars": len(_crudo)})
            except Exception:  # noqa: BLE001
                pass
            return None, {"_error": f"«{tc.function.name}» {_por}; no la ejecuto con los argumentos a medias"}
    return None, {"_error": "el modelo no emitió ninguna acción"
                            + (" (cortada por el tope de tokens)" if _cortado else "")}


async def summarize_results(goal: str, items: list) -> dict | None:
    """Filter by relevance + choose best items + conclusion. A capable judge model (default DeepSeek) reviews each
    listing against the goal and its EXACT CATEGORY: discard non-matches with a reason, and only among matching
    items choose the best. `items` = [{title,price,url,image}]. Returns {conclusion, items:[best matches],
    discarded:[{title,reason}]} or None. Fail-open: no model/errors -> do not filter, return first items, never
    break the task."""
    items = [it for it in (items or []) if it.get("title") or it.get("price")]
    if not items:
        return None
    if not _f.available():
        return {"conclusion": f"{len(items)} resultados encontrados.", "items": items[:3], "discarded": []}
    lst = "\n".join(f"{i}. {it.get('title', '')[:80]} — {it.get('price', '') or '¿precio?'}"
                    for i, it in enumerate(items[:24]))
    prompt = (
        f"OBJETIVO DEL USUARIO (respétalo al pie de la letra): {goal}\n\n"
        f"ANUNCIOS ENCONTRADOS (índice. título — precio):\n{lst}\n\n"
        "Tarea EN DOS PASOS:\n"
        "1) FILTRA por RELEVANCIA. Para CADA anuncio decide si CASA con el objetivo, mirando su CATEGORÍA EXACTA: "
        "las categorías son EXCLUYENTES (una moto de ENDURO no es de trial, ni de cross, ni de carretera/naked; un "
        "piso no es un local; etc.) y también deben cumplir precio/zona/estado si se pidieron. DESCARTA sin piedad "
        "lo que no casa, aunque el buscador lo devolviera.\n"
        "2) Entre los que SÍ casan, elige los MEJORES (máx 3) por relación calidad/precio y encaje.\n"
        "Responde SOLO JSON: {\"keep\":[índices que CASAN], \"best\":[índices de los mejores, subconjunto de keep, "
        "en orden], \"discarded\":[{\"i\":índice, \"reason\":\"por qué no casa, muy breve\"}], "
        "\"conclusion\":\"1-2 frases para el usuario sobre lo que SÍ encaja\"}")
    try:
        resp = await _f._c().chat.completions.create(
            model=_f._judge_model(), messages=[{"role": "user", "content": prompt}], max_tokens=600, temperature=0)
        _f._meter(resp, _f._judge_model())
        txt = (resp.choices[0].message.content or "").strip()
        txt = txt[txt.find("{"):txt.rfind("}") + 1] if "{" in txt else txt
        data = json.loads(txt)
        keep = [i for i in (data.get("keep") or []) if isinstance(i, int) and 0 <= i < len(items)]
        best = [i for i in (data.get("best") or []) if isinstance(i, int) and i in keep][:5]
        chosen = [items[i] for i in best] or ([items[i] for i in keep[:3]] if keep else items[:3])
        discarded = []
        for d in (data.get("discarded") or []):
            try:
                di = d.get("i")
                if isinstance(di, int) and 0 <= di < len(items):
                    discarded.append({"title": (items[di].get("title") or "")[:70],
                                      "reason": str(d.get("reason") or "")[:80]})
            except Exception:
                continue
        return {"conclusion": str(data.get("conclusion") or "").strip() or f"{len(chosen)} resultados que encajan.",
                "items": chosen, "discarded": discarded}
    except Exception as e:
        logger.warning(f"summarize_results: {e}")
        return {"conclusion": f"{len(items)} resultados encontrados.", "items": items[:3], "discarded": []}


def describe() -> str:
    return f"{_f._model()} @ {_f._base_url()}"
