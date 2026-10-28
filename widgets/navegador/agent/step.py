"""One model call of the automator (`_next_action`), the summary of a results page, and the module's self-description.
Moved out of `agent.py`; module names are read through the package (`_f.<name>`).
"""

import json

from loguru import logger

from widgets.navegador import agent as _f


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
    # V2-253 — UNREADABLE ARGUMENTS ARE NOT AN ACTION WITHOUT ARGUMENTS. This returned the action NAME
    # with `{}` when its JSON failed to parse, so the loop executed `click` without a ref, `type` without text, or
    # `navigate` without a URL — a plausible action with what the model said ERASED. It belongs to the V2-171 family
    # ("a truncated tool call is silently discarded"), and it is worse here because it is not discarded: it is acted on.
    #
    # The cluster adopted the rule governing this on 2026-08-21: **a limit is dangerous only if the reader accepts
    # PREFIXES**. The engine's other readers require the complete JSON and fall back to a safe default; this one
    # accepted the empty prefix as if it were what was requested.
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
            # V2-255 — AND THROUGH THE CHANNEL THAT ALREADY EXISTS. `tool_dropped` was created in V2-171 precisely
            # for this in FlashBrain ("the turn DECIDED on an action and the system could not read its arguments"),
            # and the harness already reads it (its node 10.6). The browser had the same event and counted it only
            # in its step list, so it did not occur for any external instrumentation. The event shape is deliberately
            # the same: consumers that already handle it need no changes to see it here too.
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
