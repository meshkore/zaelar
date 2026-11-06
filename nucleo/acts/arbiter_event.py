"""The `arbiter` event: what the canvas door decided (or, in shadow, would have decided) about one show, close or
data act, with the brief's verdict it judged by — the observability half of the door, kept out of the door itself."""
from __future__ import annotations

from nucleo.acts.canvas_arbiter import Verdict


def emit_verdict(op: str, wid: str, src: str, action: str, verdict: Verdict, *, shadow: bool,
                 brief: dict | None = None) -> None:
    try:
        from voice.observer import emit
        face = ("✅ permitiría" if verdict.allow else "⛔ vetaría") if shadow else \
               ("✅ permitida" if verdict.allow else "⛔ vetada")
        emit("arbiter", f"{face} · {verdict.rule}",
             text=f"{op} {wid}" + (f":{action}" if action else ""),
             role="system",
             extra={"op": op, "id": wid, "action": action, "src": src, "allow": verdict.allow,
                    "rule": verdict.rule, "shadow": shadow, "source": src,
                    "verdict": {k: {"choice": c, "confidence": round(f, 2)} for k, (c, f) in (brief or {}).items()},
                    **({"ev": verdict.evidence} if verdict.evidence else {})})
    except Exception:  # noqa: BLE001
        pass
