#
# translated implementation note
#
# Carved out of `dispatch.py` (V2-507) when the architecture ratchet went red: the file was 1922 lines
# translated implementation note
# no pool, no bus. Same precedent as `sheets.py`, `errand_kind.py` and `engine_url.py` before it.
#
# PURE over the live errands it is HANDED: `dispatch` owns `_SESSIONS` and resolves which of them are alive;
# this module never reaches into it. That is what lets the rule be tested without a pool, a backend or a loop.
#
import re

from nucleo import matching


def target_widget(request: str) -> str:
    """Documentation translated to English."""
    try:
        from nucleo.agentes import code as _code
        return _code._referenced_widget(request) or ""
    except Exception:
        return ""


def scan(request: str, kind: str, live: list[tuple[str, str]]) -> tuple[str | None, dict]:
    """Documentation translated to English."""
    ev: dict = {"live": len(live), "best": 0.0, "against": "", "bar": float(matching.SAME_ERRAND), "by": ""}
    req_w = matching.content_words(request)
    if not req_w:
        return None, ev
    tgt = target_widget(request) if kind in ("code", "generic") else ""
    for k, goal in live:
        if tgt and target_widget(goal) == tgt:
            ev.update(best=1.0, against=k, by="widget")
            return k, ev
        c = matching.containment(req_w, matching.content_words(goal))
        # translated implementation note
        # translated implementation note
        # translated implementation note
        if c > ev["best"] or not ev["against"]:
            ev.update(best=round(c, 3), against=k)
        if c >= matching.SAME_ERRAND:
            ev["by"] = "containment"
            return k, ev
    return None, ev


SCOPE_SYSTEM = (
    "Decides ONE thing about an assistant's background work: the operator has errands ALREADY RUNNING, and a "
    "new request just arrived. Is it a SEPARATE errand, or is it ABOUT one of the running ones?\n\n"
    "ABOUT a running one (answer its number): asking how it is going, whether there is anything yet, telling it "
    "to hurry, thanking, acknowledging, adding a detail or a correction to it, narrowing or widening it, asking "
    "it to try another site — anything the running errand's own worker could act on.\n"
    "SEPARATE (answer 0): a different thing to find, book, build or investigate — even in the same domain. "
    "Looking for a guitar and looking for a camera are two errands.\n\n"
    'Reply ONLY with JSON: {"about": <number of the running errand, or 0>}. Nothing else.\n'
    "If you cannot tell, answer 0."
)


def about_a_live_errand(request: str, live: list[tuple[str, str]]) -> str:
    """Documentation translated to English."""
    if not request.strip() or not live:
        return ""
    menu = "\n".join(f"{i + 1}. {str(goal or '')[:160]}" for i, (_tid, goal) in enumerate(live))
    try:
        from nucleo import memllm
        raw = memllm.chat_sync("errand_scope", SCOPE_SYSTEM,
                               f"RUNNING ERRANDS:\n{menu}\n\nNEW REQUEST:\n{request[:400]}",
                               max_tokens=32, temperature=0.0, timeout=12.0)
    except Exception:  # noqa: BLE001
        return ""
    if not raw:
        return ""
    m = re.search(r'"about"\s*:\s*(\d+)', raw)
    if not m:
        return ""
    n = int(m.group(1))
    # Out of range is NOT "the last one": a number nobody offered is a model that did not answer the question,
    # and picking a neighbour would attach the operator's request to an errand chosen at random.
    return live[n - 1][0] if 1 <= n <= len(live) else ""
