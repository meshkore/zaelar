"""DETERMINISTIC friction detector (V2-053 F1) — pure functions, es/en, no LLM.

Friction is Susurro's CHEAP trigger signal: the powerful LLM is only paid when there is cause. Project doctrine
(V2-046): this is NOT word-table routing — it does not decide what to DO with the turn (that remains the
model's job); it only decides whether the segment is worth AUDITING. Precision > recall: an extra trigger costs
cents; a missed one is recovered by the next complaint or pulse.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


# STRONG signals: the operator is unambiguously correcting/complaining about zaelar. One is enough.
_STRONG = [
    r"\bte lo (?:he |habia |había )?(?:dicho|pedido|preguntado|repetido)\b",
    r"\bte lo estoy (?:pidiendo|preguntando|diciendo|repitiendo)\b",   # continuous present: frustration from repetition
    r"\bte (?:he|habia|había) (?:dicho|pedido|preguntado)\b",
    r"\b(?:ya )?te dije\b",
    r"\bno (?:era|es) eso\b",
    r"\beso no (?:era|es) lo que\b",
    r"\bno me (?:referia|refería|refiero)\b",
    r"\bte (?:has|estas|estás) equivocando\b|\bte has equivocado\b",
    r"\bno me (?:estas|estás) (?:escuchando|entendiendo|haciendo caso)\b",
    r"\bme (?:estas|estás) (?:escuchando|oyendo)\?",
    r"\bno me (?:has |)(?:respondido|contestado|hecho caso)\b",
    r"\bsigues sin\b",
    r"\b(?:todavia|todavía|aun|aún) no (?:lo )?has\b",
    r"\bhace (?:un montón de |mucho |un buen |)rato que\b",
    r"\bllevas (?:un rato|mucho|media hora|horas)\b",
    r"\botra vez (?:mal|no|te (?:has|vuelves)|lo mismo)\b",
    r"\bque no,?\s",                     # "no, the other one" — emphatic correction
    # en
    r"\bi (?:already )?told you\b",
    r"\bthat'?s not what i\b",
    r"\byou'?re not listening\b",
    r"\byou (?:did it |got it |were )?wrong\b",
    r"\byou still haven'?t\b",
    r"\bi asked you (?:for|to)\b.{0,30}\b(?:ago|already|again)\b",
]
_STRONG_RE = [re.compile(p, re.I) for p in _STRONG]

# WEAK signals: they suggest friction but have legitimate uses ("again" in "put it on again"). Two are needed.
_WEAK = [
    r"\botra vez\b",
    r"\bde nuevo\b",
    r"\bno,?\s+(?:asi|así) no\b",
    r"\bno es asi\b",                    # "no es así" (correction; weak: can be neutral in a long sentence)
    r"\beso esta mal\b|\beso está mal\b",
    r"\bmal\b[\s.!?]*$",
    r"\bagain\b",
    r"\bnot (?:that|this) one\b",
]
_WEAK_RE = [re.compile(p, re.I) for p in _WEAK]


def complaint_signals(text: str) -> list[str]:
    """Complaint/correction patterns that match in the turn (normalized without accents)."""
    t = _norm(text)
    if not t:
        return []
    hits = [p.pattern for p in _STRONG_RE if p.search(t)]
    weak = [p.pattern for p in _WEAK_RE if p.search(t)]
    if hits:
        return hits + weak
    return weak if len(weak) >= 2 else []


def is_complaint(text: str) -> bool:
    return bool(complaint_signals(text))


def repeated_request(text: str, prev_user_turns: list[str], thr: float = 0.7) -> bool:
    """The SAME request repeated (≥thr Jaccard with one of the operator's previous turns). Reuses the shared
    stability seam (nucleo/flash/dialog.similar) — the same metric as the turn's anti-echo."""
    t = (text or "").strip()
    if len(t) < 12:                       # "yes", "okay", "no" — never a repeated request
        return False
    try:
        from nucleo.flash.dialog import similar
    except Exception:
        return False
    return any(similar(t, p, thr=thr) for p in prev_user_turns if p and len(p.strip()) >= 12)


# RISK in the turn DECISION (V2-061): the fast brain performed a CONSEQUENTIAL widget action (changed data /
# deleted) WITHOUT escalating → it may have treated something that was a REAL-WORLD action (canceling an
# appointment/cancellation/order) as a simple local tweak and falsely said "done". This is the CHEAP signal that
# gives Susurro the OPPORTUNITY to intervene BEFORE the operator complains (what was missing in the ITV case).
# It does NOT decide what to do — that is the powerful model's job, through understanding —; it only marks the
# turn as worth AUDITING. It is not a verb table.
def risky_decision(decision: dict | None) -> str:
    """Reason if the turn DECISION is risky (consequential widget action without escalation); '' otherwise."""
    d = decision if isinstance(decision, dict) else {}
    if d.get("escalated"):
        return ""       # it already took the correct heavyweight path — not the risk pattern
    if d.get("confirm_opened"):
        # Real BUG (2026-07-25, Manolo's live session): asking "send a message to Zalo" OPENS the confirm-gate for
        # the `send` data-op (widget_acted=true BUT confirm_opened=true) — the action was NOT executed; it is
        # WAITING for the operator's Yes/No. Susurro read it as "consequential action without escalation/not
        # executed" and launched a worker_action that went to the code GENERATOR and began MODIFYING the widget
        # to "send the message". An OPEN confirm-gate is exactly the opposite of the V2-061 risk pattern (reflecting
        # something real locally without executing it and saying "done"): here it did not say "done", it ASKED,
        # and it will execute upon confirmation. Do not audit.
        return ""
    # Fix V2-081: ONLY a DATA MUTATION (data_done) is a candidate for "local reflection of a real action without
    # execution" (the ITV: agenda.drop). Previously it also triggered on `widget_acted`, which is True for a simple
    # canvas SHOW/CLOSE → spurious audit (2026-08-01 incident: a messaging close after a new WhatsApp triggered
    # Susurro, which over-escalated a "show the message" into a worker→generator→junk widget).
    # Opening/closing/showing a widget is NEVER a real-world action reflected locally.
    if d.get("data_done"):
        return "data-op sin escalar (¿reflejo local de una acción real no ejecutada?)"
    return ""


# data-op CONFABULATION (V2-078, 2026-07-31): the MIRROR of risky_decision. There the fast brain ACTED without
# escalating; here it did NOT act (chat turn, zero tools/tags) BUT its RESPONSE CLAIMS that it did/is doing
# something ("I'm already adding it to the calendar", "I'm still on it", "done") regarding a catalog widget the
# operator NAMED. This is the PHANTOM data-op exposed by the A/B test: with the widget CLOSED, the non-reasoner says
# it acts without calling widget_data → a lie. CHEAP signal (regex on the RESPONSE, es/en, not a per-widget verb
# table) that gives Susurro the opportunity to RE-ROUTE (worker_action) and actually execute, OFF the hot path. The
# MODEL decides whether something really remained undone; this only opens the door. V2-046/V2-075 doctrine: the
# decision belongs to the model.
_CLAIM = [
    # es — preterite/gerund/present that CLAIMS a mutation was made or is in progress
    r"\b(?:hecho|listo|ya (?:esta|está)|queda (?:hecho|anotad|apuntad|añadid|agregad|guardad|reservad|marcad|cread))\b",
    r"\b(?:lo|la|los|las|te) (?:he |)(?:anotad|apuntad|añadid|agregad|guardad|actualizad|reservad|marcad|puest|cread|cancelad|borrad|program)",
    r"\b(?:lo |la |los |las |)(?:añado|agrego|apunto|anoto|guardo|actualizo|reservo|marco|pongo|creo|cancelo|borro|programo)\b",
    r"\b(?:estoy|voy a) (?:añad|agreg|apunt|anot|guard|actualiz|reserv|marc|pon|cre|cancel|borr|program)",
    r"\b(?:sigo|me pongo) con ello\b|\bva en ello\b|\bahora mismo (?:lo|la|te)\b",
    # en
    r"\b(?:done|on it)\b",
    r"\b(?:i'?ve|i have|i'?ll|i will|i'?m|i am) (?:added|updated|booked|scheduled|noted|saved|marked|set|created|cancel|put|adding|updating|booking)\b",
    r"\b(?:adding|updating|booking|scheduling|noting|saving|marking|creating|cancelling|canceling) (?:it|the|your|a )\b",
]
_CLAIM_RE = [re.compile(p, re.I) for p in _CLAIM]


def claims_action(reply: str) -> bool:
    """Does zaelar's RESPONSE claim to have made / be making a mutation? (es/en, accent-insensitive).
    It is the trace of confabulation when the turn called NO tools."""
    t = _norm(reply)
    return bool(t) and any(p.search(t) for p in _CLAIM_RE)


def _nothing_acted(decision: dict | None) -> bool:
    """True if the turn executed NOTHING consequential — robust to both forms of `decision` (voice vs probe).
    Voice: escalated/searched/widget_acted/worker_acted/data_done/confirm_opened/clarify/shown_ids flags.
    Probe: action=='chat' + no tool_calls + no tags."""
    d = decision if isinstance(decision, dict) else {}
    if "action" in d:                       # forma del probe
        if str(d.get("action") or "") not in ("chat", ""):
            return False
        return not (d.get("tool_calls") or d.get("tags"))
    # voice provider form
    return not any(d.get(k) for k in ("escalated", "searched", "widget_acted", "worker_acted",
                                      "data_done", "confirm_opened", "clarify", "shown_ids"))


def phantom_dataop(user: str, decision: dict | None) -> str:
    """Reason if the turn is a PHANTOM data-op (chatted and claimed an action on a named widget without
    executing it); '' otherwise. `decision` must contain the RESPONSE in `reply`. Three-layer precision gate:
    (1) nothing acted · (2) the response claims an action · (3) the turn resolves to a widget with DECLARED actions
    (data-driven from the manifest, not a verb table). The powerful model then decides whether something really
    remained undone and re-routes; this only opens the door, cheaply."""
    d = decision if isinstance(decision, dict) else {}
    if not _nothing_acted(d):
        return ""
    if not claims_action(str(d.get("reply") or "")):
        return ""
    u = (user or "").strip()
    if len(u) < 8:                          # "okay", "thanks" — never a data-op
        return ""
    try:                                    # does the turn point to a REAL widget with data-changing actions?
        from widgets import runtime
        from memory import api as _mem
        st = _mem.state() or {}
        m = (runtime.identify(u, open_ids=st.get("open_widgets") or [],
                              recent_ids=st.get("recent_widgets") or []) or {}).get("match")
        if not m:
            return ""
        w = runtime.get(m) or {}
        if not (isinstance(w.get("actions"), dict) and w.get("actions")):
            return ""                       # widget without data-ops (display only) → it was not a data-op
    except Exception:
        return ""
    return "data-op fantasma (charló y dijo que actuaba sobre un widget, sin ejecutar la tool)"


# System events that are friction in themselves (emitted by whoever already monitors each piece; here they are only
# mapped to a readable reason). kind/label from the observer or bus topic → reason.
def system_friction(kind: str, label: str = "", topic: str = "") -> str:
    if topic == "worker.stuck":
        return "worker encallado (sin eventos)"
    if topic == "worker.budget_kill":
        return "worker matado por presupuesto (no entregó a tiempo)"
    if kind == "alert":
        return "turno degradado (cerebro rápido caído)"
    if kind == "rail" and "fail" in (label or "").lower():
        return "rail sin_resolver"
    return ""
