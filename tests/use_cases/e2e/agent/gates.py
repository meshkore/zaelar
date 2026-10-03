"""Deterministic gates over the judge's verdict (V2-781 T514, 2026-10-03).

The judge reads prose and misses facts a line of code can check. Measured on `remember-and-remind-deadline`:
5/5 for an ES round with `scheduled_jobs.created == []` (an all-day agenda line titled «Aviso: …» fires
nothing), and 5/5 for an EN round the agent answered in Spanish. A gate only ever LOWERS a score and names
itself in the findings (`gate: <name>`), so a reader sees which number came from code and which from the judge.

  · `notice_on` — the case names the weekday its notice must ring on; no scheduled job on that date ⇒
    resultado/mecanismo/overall ≤ 2, whatever the judge scored.
  · `reply_language` — a zaelar line clearly in the other language ⇒ naturalidad ≤ 2, overall ≤ 3.
"""
from __future__ import annotations

import datetime as _dt
import re

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}

# Function words only: a product name or a number says nothing about the language a sentence is in.
_ES = frozenset("el la los las de del que y en un una por para con te tu se lo le es está ya muy pero "
                "como qué cuando hoy mañana aviso cita apuntado hecho vale gracias".split())
_EN = frozenset("the a an of to and in on for with you your it is are i i'll i've it's that this "
                "what when today tomorrow reminder done thanks okay sure will".split())


def round_day(transcript: list[dict]) -> _dt.date:
    """The day the round ran, from its first timestamped line (falls back to today)."""
    at = next((t.get("at") for t in transcript or [] if isinstance(t.get("at"), (int, float))), None)
    return _dt.datetime.fromtimestamp(at).date() if at else _dt.date.today()


def notice_day(weekday: str, ref: _dt.date) -> str:
    """The first `weekday` strictly after `ref` — «el miércoles» said on a Saturday is the coming one."""
    wd = _WEEKDAYS[weekday.strip().lower()]
    return (ref + _dt.timedelta(days=(wd - ref.weekday()) % 7 or 7)).isoformat()


def reply_language(line: str, locale: str) -> str:
    """'es' / 'en' when the line is clearly one of them, '' when it is too short or mixed to tell."""
    words = re.findall(r"[a-záéíóúñü']+", (line or "").lower())
    if len(words) < 4:
        return ""
    es, en = sum(w in _ES for w in words), sum(w in _EN for w in words)
    if max(es, en) < 2 or es == en:
        return ""
    return "es" if es > en else "en"


def _cap(verdict: dict, caps: dict, overall: int) -> None:
    scores = verdict.setdefault("scores", {})
    for k, n in caps.items():
        if isinstance(scores.get(k), (int, float)):
            scores[k] = min(scores[k], n)
    if isinstance(verdict.get("overall"), (int, float)):
        verdict["overall"] = min(verdict["overall"], overall)


def _notice_gate(scenario, run: dict, verdict: dict) -> dict | None:
    weekday = getattr(scenario, "notice_on", "") or ""
    if not weekday:
        return None
    day = notice_day(weekday, round_day(run.get("transcript") or []))
    jobs = ((run.get("mechanism_report") or {}).get("scheduled_jobs") or {}).get("created") or []
    rings = [j for j in jobs if str(j.get("schedule") or "").startswith(day)]
    out = {"day": day, "jobs": [str(j.get("schedule")) for j in jobs], "ok": bool(rings)}
    if not rings:
        _cap(verdict, {"resultado": 2, "mecanismo": 2}, 2)
        verdict.setdefault("findings", []).append({
            "turno": "zaelar", "gravedad": "alta", "gate": "notice_on",
            "problema": f"[gate] the case asks for a notice on {weekday} ({day}) and no scheduled job rings that "
                        f"day (created: {out['jobs'] or 'none'}). A calendar line is not a notice."})
    return out


def _language_gate(scenario, run: dict, verdict: dict) -> dict | None:
    want = "es" if str(getattr(scenario, "locale", "")).lower().startswith("es") else "en"
    wrong = []
    # `zaelar@turnN` is the line's index in the transcript, the numbering the judge's findings already use
    for turn, t in enumerate(run.get("transcript") or []):
        if t.get("who") != "zaelar":
            continue
        got = reply_language(t.get("text") or "", want)
        if got and got != want:
            wrong.append((turn, (t.get("text") or "")[:120]))
    if not wrong:
        return {"want": want, "ok": True}
    _cap(verdict, {"naturalidad": 2}, 3)
    verdict.setdefault("findings", []).append({
        "turno": ", ".join(f"zaelar@turn{n}" for n, _ in wrong), "gravedad": "alta", "gate": "reply_language",
        "problema": f"[gate] the session language is {want} and {len(wrong)} reply(ies) came in the other one: "
                    + " | ".join(f"«{s}»" for _, s in wrong[:3])})
    return {"want": want, "ok": False, "turns": [n for n, _ in wrong]}


def apply(scenario, run: dict, verdict: dict) -> dict:
    """Run every gate over `verdict` (mutated and returned). Records what each gate saw under `gates`."""
    seen = {}
    for name, gate in (("notice_on", _notice_gate), ("reply_language", _language_gate)):
        try:
            got = gate(scenario, run or {}, verdict)
        except Exception as e:  # noqa: BLE001 — a broken gate is reported, never silently passes or fails a round
            got = {"error": str(e)}
        if got is not None:
            seen[name] = got
    verdict["gates"] = seen
    return verdict
