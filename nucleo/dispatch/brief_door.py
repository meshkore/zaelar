"""The ONE door every research brief is composed through (V2-837 G9: moved out of `prepare.py` to record it).

A worker is held to its brief — the hard criteria, how many finalists, how wide to look — and the brief went only to
the process log, so a search that brought the wrong cars could not be checked against what it had been told. The
door now emits one `brief composed` event per errand with those declared fields, whatever path produced it.
Module names are read through the dispatcher (`_d.<name>`), so a patch on `nucleo.dispatch` still governs it.
"""
from __future__ import annotations

from nucleo import dispatch as _d


async def _compose_brief(request: str, context: str, trusted: bool, resume: dict | None = None,
                         task_id: str = "") -> dict | None:
    """The one door every research brief is composed through — and so the one place it is RECORDED (V2-837 G9): one
    `brief composed` event per errand with the fields the worker will be held to, whatever path produced it."""
    t0 = _d.time.monotonic()
    how, brief = "none", None
    try:
        how, brief = await _compose_brief_how(request, context, trusted, resume)
        return brief
    except _d.research.ComposerUnavailable:
        how = "unavailable"
        raise
    except _d.asyncio.CancelledError:
        how = "cancelled"
        raise
    except Exception:
        how = "error"
        raise
    finally:
        _emit_brief(brief, how=how, ms=(_d.time.monotonic() - t0) * 1000, task_id=task_id, trusted=trusted)


def _emit_brief(brief: dict | None, *, how: str, ms: float, task_id: str, trusted: bool) -> None:
    """`how`: composed · reused (a resumed round keeps its criteria) · next_round · none (the composer said this is
    not research) · unavailable · cancelled · error. The fields are the ones a worker is judged against; lists are capped, never cut
    mid-item. Fail-soft: recording a brief never stops one."""
    if not trusted:
        return                                   # no tools, no research to direct: nothing was composed
    try:
        from voice.observer import emit
        b = brief or {}
        deliv, breadth = b.get("deliverable") or {}, b.get("breadth") or {}
        ex = {"how": how, "brief_ms": round(ms), "round": b.get("round"), "domain": b.get("domain") or None,
              "n_final": deliv.get("n_final"), "widget": deliv.get("widget") or None,
              "min_candidates": breadth.get("min_candidates"),
              "hard": list(b.get("hard") or [])[:8] or None, "soft": list(b.get("soft") or [])[:8] or None,
              "subjects": list(b.get("subjects") or [])[:6] or None,
              "quality_bar": list(b.get("quality_bar") or [])[:6] or None}
        if task_id:
            ex.update({"id": task_id, "span": f"worker:{task_id}"})
        emit("task", "🧭 brief composed", text=str(b.get("goal") or "")[:240], role="system",
             extra={k: v for k, v in ex.items() if v is not None})
    except Exception as e:  # noqa: BLE001
        _d.logger.debug(f"dispatch: brief event not emitted: {e!r}")


async def _compose_brief_how(request: str, context: str, trusted: bool,
                             resume: dict | None = None) -> tuple[str, dict | None]:
    """PRE-VUELO of a research: convierte the request cruda in a BRIEF dirigido (nucleo/workers/brief.py).

    Por what esta AQUÍ and no in the turn of voice: dirigir bien a search —separar criterios duros of blandos,
    add it that a experto sabe that hara missing, fijar cuan wide there is that buscar and with what baremo juzgar— es a
    work of razonamiento, and the FlashBrain of voice has that contestar in milisegundos. Aqui already estamos outside of
    ese reloj: the escalada es asincrona, the operator already sabe that esto tarda, so that this es the only point of the
    sistema donde is can pensar before of empezar a trabajar.

    If es a REANUDACIÓN, the brief of the ronda anterior is reuses tal cual: the criterios already estaban acordados
    and recomponerlos podria cambiarlos a mitad of a search that the operator cree that continues the same guion."""
    if not trusted:
        return "none", None               # perfil sin tools: no hay investigación que dirigir
    prev_tid = str((resume or {}).get("brief_task") or "")
    if prev_tid:
        prev = _d.research.load(prev_tid)
        if prev:
            return "reused", prev
    # ¿Ya investigamos esto and the operator vuelve a the load? Entonces es the RONDA SIGUIENTE of the same search:
    # hereda the criterios acordados and sube the amplitud, with su frase of ahora como reason of the rechazo. Sin esto,
    # «esos no me valen, busca mas» recomponia the brief from cero and repetia the same search with the same
    # amplitud — the operator habria visto arrive the same results and concluido, with razon, that no le escuchamos.
    gk = _d._goal_key(request)
    prev = _d.research.previous_round(gk)
    if prev:
        nxt = _d.research.expand(prev, note=request)
        _d.logger.info(f"dispatch: RONDA {nxt.get('round')} de una investigación ya conocida "
                    f"(≥{(nxt.get('breadth') or {}).get('min_candidates')} candidatos): {request[:60]}")
        return "next_round", nxt
    b = await _d.research.compose(request, context)
    return ("composed" if b else "none"), b
