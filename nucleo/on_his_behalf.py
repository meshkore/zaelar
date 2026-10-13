"""nucleo/on_his_behalf.py — an act in the operator's NAME runs only when HE asked for it (worker doors).

## What was measured (`best-plumber-same-day__es`, 2026-10-14, sandbox 20261014-010939-es)

He asked to FIND a well-rated plumber who can come today. The turn's model wrote the brief «Buscar y
CONTACTAR fontaneros…», and the worker, on its own, ran `contactos.add_contact` ×2 and
`mensajeria.send_to` ×2 («Hola, ¿fontaneros de urgencia? Tengo una fuga…») to two real businesses. Both
sends failed only because the number was not yet a channel in the directory — and the error told the
worker how to fix that. No control of SCOPE was involved at any point:

  · `worker_policy.classify_act` decides a worker's `widget_data` with `action_mode_now` (V2-719, «one
    consent rule»). `send_to` declares `confirm: false` because, in a TURN, «whoever calls it is executing an
    order the operator has just given» (V2-692). The voice and text channels back that premise with a
    verdict over his words (`leave_gate`, `tool_executor_widget_calls`). A worker has no such verdict: it
    borrowed the conclusion without the premise, so FAST → ALLOW.
  · The browser has the same hole: V2-712 stopped asking for consent on a form that wants his name, phone
    and email «because a booking form is the shape of the order he just gave». On an errand that was only
    «find», nobody gave that order.

## The rule

A worker act that acts FOR him toward somebody else — one that declares `external.send`, one whose
manifest declares `on_his_behalf` (naming the payload field that says WHO), or one of `critical` level
(money) — runs only when every WHO it carries is named in HIS OWN words for this errand (`his_words`).
Otherwise it is not refused and not run: it becomes the question to him, the worker's ordinary CONFIRM
(`worker_api._register_ask`), and his «sí» runs it. That is «propose it and ask», never a silent drop.

Named means literally: a phone or a handle appears in what he said, a name appears there as a contiguous
phrase. That is the same yardstick `leave_gate._named_by_him` applies to a send with a stranger's text in
the context — the recipient must be his — made strict here because a worker's recipient was FOUND by the
worker: «Fontanero Urgencia Madrid» shares two words with «necesito un fontanero… Madrid centro», and one
shared word is what `leave_gate` accepts. No verb is read anywhere: what he asked for is decided by WHO he
named, never by a word list.

Fails toward ASKING: no words on file (a restart, a sandbox that never recorded the turn) ask.
"""
from __future__ import annotations

import re
import time
import unicodedata

LOOKBACK_S = 900.0
_RECIPIENT_KEYS = ("to", "contact", "recipient", "chat")


def _fold(v) -> str:
    t = unicodedata.normalize("NFKD", str(v or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _spec(wid: str, action: str) -> dict:
    try:
        from widgets import runtime
        man = runtime.get(str(wid or "").split("::", 1)[0].strip().lower()) or {}
        spec = (man.get("actions") or {}).get(str(action or "").strip())
        return spec if isinstance(spec, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def acts_for_him(wid: str, action: str) -> bool:
    """Does this declared action act in his name toward somebody else? Read from declarations only."""
    spec = _spec(wid, action)
    if spec.get("on_his_behalf"):
        return True
    try:
        from widgets import effects as _fx
        if _fx.carries(wid, action, _fx.EXTERNAL_SEND):
            return True
        from nucleo import consent
        return consent.level_of(spec, action=action) == "critical"
    except Exception:  # noqa: BLE001 — unreadable: it acts for him, so it asks
        return True


def who_of(wid: str, action: str, payload) -> list[str]:
    """The WHO this call names: the declared `on_his_behalf` field, else the recipient keys of a send."""
    p = payload if isinstance(payload, dict) else {}
    field = _spec(wid, action).get("on_his_behalf")
    keys = (field,) if isinstance(field, str) and field.strip() else _RECIPIENT_KEYS
    out: list[str] = []
    for k in keys:
        v = p.get(k)
        for item in (v if isinstance(v, (list, tuple)) else [v]):
            if isinstance(item, dict):
                item = item.get("name") or item.get("email") or item.get("handle") or ""
            out.extend(x.strip() for x in re.split(r"[,;]", str(item or "")) if x.strip())
    return out


def _words_of(text: str) -> list[str]:
    return re.findall(r"[\w@+-]+(?:\.[\w@+-]+)*", _fold(text))


def named(who: str, said: list[str]) -> bool:
    """Is `who` named in his words — a handle literally, a phone by its digits, a name as a contiguous phrase?"""
    w = _fold(who).strip()
    if not w or not said:
        return False
    digits = re.sub(r"\D", "", w)
    if len(digits) >= 6 and len(digits) >= len(re.sub(r"[\s+().-]", "", w)) - 1:
        tail = digits[-9:]                      # a country prefix he did not say does not make it another number
        return any(tail in re.sub(r"(?<=\d)[\s.()-]+(?=\d)", "", _fold(t)) for t in said)
    if "@" in w:
        return any(w in _fold(t) for t in said)
    phrase = " ".join(_words_of(w))
    return bool(phrase) and any(f" {phrase} " in f" {' '.join(_words_of(t))} " for t in said)


def errand_words(rec=None, *, now: float | None = None) -> list[str]:
    """His turns for this errand: from a little before it started (the turn that asked for it) to now."""
    from nucleo import his_words
    start = float(getattr(rec, "started", 0) or 0) or float(now if now is not None else time.time())
    return his_words.since(start - LOOKBACK_S)


def _resolve(payload: dict) -> tuple[str, str, dict]:
    """(widget, action, inner payload) of a `widget_data` call — the generic `rows.*` door resolved to the
    declared action it runs (`collections.<c>.via`), because that action is what actually happens."""
    wid = str(payload.get("widget_id") or payload.get("id") or "").strip().lower()
    act = str(payload.get("action") or "").strip()
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    if act.startswith("rows."):
        op = act.split(".", 1)[1]
        try:
            from widgets import rows
            via = (rows.spec(wid, str(inner.get("collection") or inner.get("coll") or "")).get("via") or {})
        except Exception:  # noqa: BLE001
            via = {}
        act = str(via.get(op) or "")
        inner = inner.get("row") if op == "put" else inner.get("set") if op == "patch" else {}
        inner = inner if isinstance(inner, dict) else {}
    return wid, act, inner


def worker_question(rec, action: str, payload) -> str:
    """'' when a worker may run this act; otherwise the question to put to him (in his language)."""
    if action != "widget_data" or not isinstance(payload, dict):
        return ""
    wid, act, inner = _resolve(payload)
    if not wid or not act or not acts_for_him(wid, act):
        return ""
    who = who_of(wid, act, inner)
    said = errand_words(rec)
    if who and all(named(w, said) for w in who):
        return ""
    _emit("task", "🛑 acto en su nombre que él no pidió — se le pregunta",
          f"{wid}:{act} → {', '.join(who) or '∅'}", {"id": str(getattr(rec, "task_id", "")), "widget": wid,
                                                       "action": act, "who": who[:4], "said": len(said)})
    try:
        from i18n import langs as _lg
        return _lg.current_language().worker_confirm_on_behalf.format(action=act, who=", ".join(who) or wid)
    except Exception:  # noqa: BLE001
        return f"{act} · {', '.join(who) or wid}?"


# ── the browser: a form that hands his identity to a site ───────────────────────────────────────────────
_ID_GROUPS = (re.compile(r"e-?mail|correo", re.I),
              re.compile(r"\btel\b|phone|telefono|mobile|movil", re.I),
              re.compile(r"given-name|family-name|\bname\b|nombre|apellido", re.I))


def _site_of(url: str) -> str:
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""
    labels = [x for x in host.split(".") if x and x != "www"][:-1] or host.split(".")[:1]
    return max(labels, key=len) if labels else ""


def _site_named(site: str, said: list[str]) -> bool:
    """Is the site's name a contiguous run of his words («casalucio» ← «en Casa Lucio»)?"""
    site = re.sub(r"[^a-z0-9]", "", _fold(site))
    if len(site) < 3:
        return False
    for t in said:
        ws = [re.sub(r"[^a-z0-9]", "", x) for x in _words_of(t)]
        for i in range(len(ws)):
            run = ""
            for x in ws[i:i + 6]:
                run += x
                if run == site:
                    return True
                if len(run) >= len(site):
                    break
    return False


def form_question(task_id: str, sig) -> str:
    """'' when this submit may go; otherwise WHY it asks — a form that sends his identity (two of name, email,
    phone) to a site his words for this errand never named. A booking at the place he named still runs
    without a question, as V2-712 asked."""
    if not isinstance(sig, dict) or not (sig.get("isSubmit") or sig.get("inForm")):
        return ""
    hay = str(sig.get("signals") or "")
    if sum(1 for g in _ID_GROUPS if g.search(hay)) < 2:
        return ""
    rec = None
    try:
        from nucleo import dispatch
        rec = dispatch.record_by_nav_task(task_id)
    except Exception:  # noqa: BLE001
        rec = None
    site = _site_of(sig.get("targetUrl") or "") or _site_of(sig.get("pageUrl") or "")
    if site and _site_named(site, errand_words(rec)):
        return ""
    _emit("widget", "gate_on_behalf", site or "?", {"id": "navegador", "task": str(task_id)})
    try:
        from i18n import langs as _lg
        return _lg.current_language().nav_form_on_behalf.format(site=site or "?")
    except Exception:  # noqa: BLE001
        return site or "?"


def _emit(kind: str, label: str, text: str, extra: dict) -> None:
    try:
        from voice.observer import emit
        emit(kind, label, text=text, role="system", extra=extra)
    except Exception:  # noqa: BLE001 — the trace never stops the gate
        return
