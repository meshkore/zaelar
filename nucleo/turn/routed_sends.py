"""A send the turn routed is never lost (V2-852 M2).

An act that leaves is never run inline by Flash: the turn routes his words as a task (`tool_executor_widget_calls.
_leaving_is_a_task`). The turn's commission (`escalate_req["v"]`) is one slot that many doors read and several clear
or fill — a close backstop cancels a «spurious» escalation, a turn that answers a waiting task opens no errand of its
own, a model call can claim the slot first with a narrower request. Guarding each of those writers one by one is a
list that grows; this is the one place a routed send is accounted for, at the launch itself:

  · `note` keeps every routed send in its own slot, `escalate_req["sends"]`, when it is routed;
  · `keep`, called by the launch before anything starts, makes sure each one leaves the turn as a commission:
      - the turn launches nothing else → the send becomes the commission (`v`);
      - the turn launches something else → the send is one more commission of the same turn (`more`), unless that
        commission already carries his same words;
      - the turn addressed a live worker (he answered its question, or his words were injected into it) and starts
        nothing → his words, send included, reached that worker: said on the timeline, nothing more;
      - the turn stopped a worker and starts nothing in its place → the send starts on its own row
        (`ask_outside_door.to_message_task`, the `message` playbook).
"""
from __future__ import annotations

from loguru import logger

#: The live-worker outcomes of a turn whose words reached that worker (`worker_acted["v"]`).
REACHED_A_WORKER = ("answer", "inject")


def note(escalate_req: dict, wid: str, action: str, text: str) -> None:
    """Keep a routed send in its own slot. Never raises."""
    try:
        said = " ".join(str(text or "").split())
        sends = escalate_req.setdefault("sends", [])
        if said and not any(s["text"] == said for s in sends):
            sends.append({"text": said, "widget": str(wid or ""), "action": str(action or "")})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"routed_sends: not noted ({e!r})")


def _carried(said: str, escalate_req: dict) -> bool:
    texts = [escalate_req.get("v"), *(escalate_req.get("more") or [])]
    return any(" ".join(str(t or "").split()) == said for t in texts if t)


def keep(escalate_req: dict, worker_acted: dict, replacing: bool, *, emit=None) -> list[str]:
    """Fold every routed send into what the turn launches; returns what each send became (for the timeline and the
    tests). Never raises: an unreadable slot leaves the turn as it was."""
    out: list[str] = []
    try:
        sends = list(escalate_req.get("sends") or [])
        if not sends:
            return out
        addressed = (worker_acted or {}).get("v")
        launches = escalate_req.get("v") is not None and (not addressed or replacing)
        for s in sends:
            said = s["text"]
            if launches and _carried(said, escalate_req):
                out.append("carried")
            elif launches:
                escalate_req.setdefault("more", []).append(said)
                out.append("more")
            elif not addressed or replacing:
                escalate_req["v"], launches = said, True
                out.append("commission")
            elif addressed in REACHED_A_WORKER:
                out.append("reached")
            else:
                from nucleo.request import ask_outside_door
                started = ask_outside_door.to_message_task(s["widget"], s["action"], said, src="routed", emit=emit)
                out.append("own-row" if started else "not-started")
        if emit is not None and any(o != "carried" for o in out):
            emit("brain", "📨 a routed send is kept — it leaves the turn as a commission", text=sends[0]["text"][:120],
                 role="system", extra={"cat": "flash", "sends": out})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"routed_sends: not folded ({e!r})")
    return out
