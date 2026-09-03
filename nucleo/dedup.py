#
# dedup.py — «is this a NEW errand, or the one already running?», with the evidence it decided on.
#
# Carved out of `dispatch.py` (V2-507) when the architecture ratchet went red: the file was 1922 lines
# against a 1865 cap, and this is a self-contained question — two judges over text, no session lifecycle,
# no pool, no bus. Same precedent as `sheets.py`, `errand_kind.py` and `engine_url.py` before it.
#
# PURE over the live errands it is HANDED: `dispatch` owns `_SESSIONS` and resolves which of them are alive;
# this module never reaches into it. That is what lets the rule be tested without a pool, a backend or a loop.
#
import re

from nucleo import matching


def target_widget(request: str) -> str:
    """The EXISTING widget the request references ('' if none) — the dedup key for widget tasks."""
    try:
        from nucleo.agentes import code as _code
        return _code._referenced_widget(request) or ""
    except Exception:
        return ""


def scan(request: str, kind: str, live: list[tuple[str, str]]) -> tuple[str | None, dict]:
    """The dedup's verdict AND the evidence it decided on, over the LIVE errands it is handed.

    TWO signals: (1) SAME target widget (code tasks over the same widget) → strong dedup; (2) CONTAINMENT of
    content words against a live session's goal. The dedup lives here and not in the voice provider's
    turn-start snapshot (which failed the 2026-07-15 session: the re-escalation arrived in an ambient turn
    through window contamination and `_similar_pending` never saw it).

    F4 (2026-08-23) — the yardstick is `matching.containment`, not Jaccard, and the why is measured: the
    brain REFORMULATES the errand on every escalation (668/437/342/298 chars for the same case), Jaccard
    divides by the UNION and a longer rewording looks different *by being longer* — four workers for one
    errand on 2026-08-21, pairwise Jaccard 0.319-0.450, all under the 0.60 bar of the time. Containment
    divides by the SMALL set, which is the real question («is the short version inside the long one?»), and
    separates without overlap (same errand 0.571-0.893 · different 0.062-0.227). As a bonus it neutralizes
    the `goal=request[:200]` trim: the truncated side is the `min` it divides by, so trimming the stored goal
    barely moves the measure — Jaccard sank it every time.

    WHY THE EVIDENCE TRAVELS WITH THE VERDICT (V2-507). A negative answer used to be mute: None came back,
    and «no live session matched» reads exactly like «there was no live session to match against». They call
    for OPPOSITE fixes —a broken yardstick, or a session that died at birth— so a report that cannot tell
    them apart sends you to the wrong file.

    Measured 2026-08-30, `cheapest-monitor__us` round 20260830-114302: two sheets open (`results::101c0f-1`
    at 11:34:03, `-2` at 11:34:22), ONE worker started (`task/start` of id=2; all 209 task events in the
    window carry id=2) and no `task/dedup` anywhere. Re-reading the sandbox's event log still could not
    settle which of the two had happened. The harness had papered over the gap with a number of its own —the
    containment between the two goals IT saw—, but that is a DIFFERENT pair from the one this function
    compares (the incoming request against a live session's truncated goal), so its 1.0 could not falsify the
    engine's decision either. An accusation that cannot be falsified is worse than the defect it names.

    The evidence is produced by the loop that DECIDES, never recomputed beside it: a second copy of a rule
    drifts, and then the row reports a number the code did not use — precisely the confusion this removes."""
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
        # `or not ev["against"]`: a containment of exactly 0.0 is still a comparison that HAPPENED, and
        # leaving `against` empty there would say «I matched nobody» when the truth is «I matched this one
        # and it scored zero» — the same silence this row exists to break, one field further in.
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
    """The tid of the live errand this request is ABOUT, or "" when it is a genuinely NEW one.

    THE SECOND HALF OF THE DEDUP, and the one `find_duplicate` structurally cannot do. That one answers «is
    this a reformulation of the same request», by containment over content words, and it is right to: it was
    built for a brain that rewrites the errand every time it escalates. What it cannot see is a turn that is
    not a request at all. Measured 2026-08-24, goals straight out of the lab's durable log — ONE guitar
    search:

        16:14:30  web       «Busca en marketplaces de segunda mano … una guitarra acústica…»   <- the errand
        16:15:48  research  «¿Alguna novedad ya?»                                              <- a worker
        16:16:20  research  «Perfecto, dale. ¿Tienes algo ya?»                                 <- another

    Four cards on the operator's screen for one errand, three workers competing for the same turn, and a
    fourth-case worker reporting on «the four searches» because its own errand WAS a follow-up question.
    Containment reads 0 between «¿alguna novedad?» and «busca una guitarra» — correctly. There is no word
    list that fixes this either: the ways of asking how something is going are unbounded, and a list would
    be the hardcoding this codebase keeps paying for. So a MODEL judges it, exactly like V2-075's
    conversational-health criterion, and for the same reason.

    Runs ONLY with something already live, which is what keeps it cheap: the first errand of a conversation —
    the common case — never pays for it. It is off the voice turn (the dispatcher already answered) though
    still in front of a worker the operator is waiting on, hence the direct reasoning-OFF endpoint.

    FAIL-OPEN, and the direction is deliberate: anything unreadable answers "" and the errand spawns, which is
    exactly today's conduct. Refusing to spawn on a failed model call would silently swallow real errands —
    an operator whose request vanished has no way to even see what happened, while a spurious extra worker is
    visible on screen, which is how this defect got found in the first place.
    """
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


def continues_ended(request: str, kind: str, ended: list[dict]) -> tuple[str, dict]:
    """The sheet a NEW errand inherits because it continues a JUST-ENDED one — ("", {}) when it continues none.

    V2-566. The live dedup cannot see an errand that just delivered its report and died, so the operator's
    follow-up three minutes later («coge otro, no pares hasta que tengas una reserva», measured 2026-09-03)
    opened a SECOND results sheet beside the first for the same reservation. The relay already established the
    principle in `sheets.py` — «a relay is not a new errand», it inherits its predecessor's box — and this is
    the same principle one notch out: a follow-up is not a new errand either.

    Same strict matcher as the live scan (`scan`), deliberately: two yardsticks of similarity is the failure
    `test_one_yardstick_of_similarity` exists to prevent. PURE over the snapshots it is handed
    (`{id, goal, sheet}`, from `dispatch._ENDED_SESSIONS`): only snapshots that carry a sheet participate —
    an errand that never wrote to a box has no box to inherit."""
    rows = [e for e in (ended or []) if str(e.get("sheet") or "") and str(e.get("goal") or "").strip()]
    if not rows:
        return "", {}
    prev, ev = scan(request, kind, [(str(e.get("id") or ""), str(e.get("goal") or "")) for e in rows])
    if not prev:
        return "", ev
    sheet = next((str(e.get("sheet") or "") for e in rows if str(e.get("id") or "") == prev), "")
    ev = dict(ev)
    ev["from"] = prev
    return sheet, ev
