"""nucleo/workers/findings.py — what a worker FINDS reaches the conversation as soon as it exists.

V2-223 closed this for what the BROWSER extracts: the finding is pushed as a system note the moment it
appears, not at the end of the session. What remained outside —the same hole with another door— is what a
WEB SEARCH returns, which in a worker is the path that most often produces the good, already-clean datum.

Measured by the harness on 2026-08-21 in `cheapest-monitor`, reading the full observability data: the events
`kind='search'` (`🌐 web ↩`) contained

    «Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €»
    «Alurin CoreVision 27" IPS 4K Freesync — 149,99 €»

exactly what the operator had requested, in clean text. **7 searches, 5 answers, 0 brain notes from that
channel.** And the reason: **5 of 8 workers returned `ok:false`** — they fail before delivering, and the good
text goes down with them. Zaelar said «the search failed without finishing», which was THE TRUTH.

Three decisions keep this from becoming noise:

  · **The JUDGMENT stays in the brain.** The note delivers the fact and names the evidence; it does not order
    it announced. An order saying «say this» would end up offering the first result of a failed search as the answer.
  · **A single instruction** (V2-226): the branching goes INSIDE the imperative, never as a second command.
  · **It is clipped, not summarized, and how much was left out is stated** (the doctrine of
    `observability/evidence.py`). A search response may be an entire page; what is pushed is its beginning,
    with a count of what is missing, and never a version rewritten by us.
"""
from __future__ import annotations

import re as _re

#: A monetary amount as sources actually write one: $1,299.99 · 199,99 € · €249 · USD 249 · 249 USD · £99.
#: Currencies, not categories — recognising money is domain-agnostic; recognising products would not be.
_AMOUNT_RE = _re.compile(
    r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£]|€)|(?:USD|EUR|GBP)\s?\d[\d.,]*|\d[\d.,]*\s?(?:USD|EUR|GBP))",
    _re.I)


def _lone_amount(text: str) -> str:
    """The ONE monetary amount `text` names, or "" when it names none — or several (V2-471).

    Several amounts is ambiguity («was $399 now $279», «from $199 to $499») and picking one would be
    inventing a datum with the shape of an observation; absence is honest and `fila()` says it out loud."""
    hits = [h.strip() for h in _AMOUNT_RE.findall(str(text or ""))]
    return hits[0][:20] if len(hits) == 1 else ""


#: A link, as any source writes one. Recognizing a link is domain-agnostic; recognizing a product would not be.
_URL_RE = _re.compile(r"https?://\S{4,}", _re.I)

#: A tool's WRAPPER: its own transcript, with the link JSON inside. It is STRUCTURE (an array of objects after
#: a colon), not a sentence — so there is no need to recognize the language in which each CLI writes its header,
#: which is the race this repo has been losing since V2-364.
_ENVELOPE_RE = _re.compile(r':\s*\[\s*\{\s*"')


def looks_like_a_finding(text: str) -> bool:
    """Does this text BRING something, or does it merely TELL what happened?

    V2-511. `_maybe_hand_web` pushes the RAW text of any web step that is not `is_error`, and a tool that
    successfully returns a rejection is not one. Measured in `cheapest-monitor__us` (20260830-130649) with
    the sheet EMPTY and 17 notes offered to the brain: seven were HTTP errors or refusals from the worker
    itself («The server returned HTTP 404…», «Based on the content provided, I'm unable to summarize…») and
    **eleven were the CLI searcher's wrapper** («Web search results for query: … Links: [{"title":…»). Zero
    records. The judge had spent four rounds filing «presents irrelevant candidates» and the agent was not
    choosing badly: that is what we gave it.

    TWO filters, both STRUCTURAL — not a list of English phrases, which is the treadmill that
    V2-364 already measured («chasing the language is a race that cannot be won») and that would also exclude
    any CLI that writes its header differently:

      · a tool WRAPPER (link JSON inside) is its transcript, not a result that anyone vetted;
      · a finding brings a HARD DATA POINT —a link or an amount—. A narrative about the page brings neither,
        and that is precisely their family resemblance: it tells, it does not deliver.

    ACCEPTED AND STATED COST: a finding whose only actionable datum is a PHONE (the service errand of V2-240)
    does not pass this filter through this door. It is deliberately not added here — «nine to fourteen digits»
    over free prose is the trap V2-321 paid for (a date read as a phone number), and the sheet DOES preserve
    the phone through its own path. Measure it before broadening it.
    """
    t = " ".join(str(text or "").split())
    if not t:
        return False
    if _ENVELOPE_RE.search(t):
        return False
    return bool(_URL_RE.search(t) or _AMOUNT_RE.search(t))


MAX_CHARS = 700          # what fits in a note without turning the conversation into a dump
MIN_CHARS = 12           # below this there is no finding worth reporting («ok», «done», an empty line)

#: task_id → signatures already delivered. The SAME repeated response is not a new finding; a repeated search
#: would be if it brought something else, so comparison is by CONTENT and not by the fact that it was searched.
_HANDED: dict[str, set] = {}


def clip(text: str) -> str:
    """The beginning of the finding, with a count of what is left out. Never a rewritten version."""
    t = " ".join(str(text or "").split())
    if len(t) <= MAX_CHARS:
        return t
    return t[:MAX_CHARS].rstrip() + f"… [+{len(t) - MAX_CHARS} caracteres más en el registro]"


def forget(task_id) -> None:
    """The session ended: its memory of findings goes with it."""
    _HANDED.pop(str(task_id), None)


def render_search(res: dict, k: int = 4) -> str:
    """`{answer, results:[{title,snippet,url}]}` → the text delivered to the brain.

    `answer` is preferred when the source has already synthesized it (Perplexity/Tavily/AI Overview): it is what
    that source returned, not our own rewrite. Without it, the first rows EXACTLY AS IS. This does not judge
    which one is useful — that is the brain's job — and therefore does not reorder them either.
    """
    if not isinstance(res, dict):
        return ""
    ans = " ".join(str(res.get("answer") or "").split())
    if ans:
        return ans
    rows = []
    for r in (res.get("results") or [])[:max(1, k)]:
        if not isinstance(r, dict):
            continue
        bits = [str(r.get("title") or "").strip()[:90], str(r.get("snippet") or "").strip()[:160],
                str(r.get("url") or "").strip()[:120]]
        row = " — ".join(b for b in bits if b)
        if row:
            rows.append(row)
    return "; ".join(rows)


def hand_web_finding(task_id, text: str, goal: str = "") -> bool:
    """Pushes to the brain what a web search has just returned. Returns whether it was pushed.

    Entirely fail-soft: this runs inside a live worker's event loop and cannot bring it down.
    """
    body = clip(text)
    if len(body) < MIN_CHARS:
        return False
    # V2-511 — what TELLS what happened is not pushed as though it BROUGHT something. V2-510 fixed the imperative
    # (a page is not a candidate); this removes what is not even a page from the way.
    if not looks_like_a_finding(body):
        return False
    key = str(task_id)
    seen = _HANDED.setdefault(key, set())
    sig = body[:200]
    if sig in seen:
        return False
    seen.add(sig)
    what = str(goal or "").strip()[:70] or "la tarea de fondo"
    try:
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] Una búsqueda web ha devuelto esto, trabajando en «{what}»: {body}. Nadie más lo sabe: no "
            f"está en la conversación hasta que tú lo digas, y el worker puede morirse antes de entregarlo. "
            # V2-510 — THIS IS A LEAD UNTIL PROVEN TO BE A CANDIDATE, and the imperative must say so. What
            # returns from a search is almost always PAGES: comparison headlines, a store's homepage, the body
            # of a 403. Ordering «give it with name, price, and link» in that situation means ordering an article
            # to be offered as though it were the product — measured in `cheapest-monitor__us`
            # (20260830-125532): turn 4 delivered «The 6 Best Budget And Cheap Monitors of 2026 -
            # RTINGS.com» while the eight REAL monitors waited in the sheet.
            f"OJO CON LO QUE ES: lo que vuelve de una búsqueda suele ser una PÁGINA —el titular de una "
            f"comparativa, un listado, un error del sitio—, y una página NO es un candidato. NÓMBRALO EN ESTE "
            f"TURNO diciendo lo que ES: si trae ya la cosa concreta con su nombre y su precio, dásela como "
            f"resultado; si es un artículo, un buscador o un error, cuéntalo como por dónde vas a mirar y "
            f"NUNCA lo ofrezcas como una opción para elegir. No digas que no hay resultados ni que sigues "
            f"buscando sin más.")
        return True
    except Exception:  # noqa: BLE001
        return False


def _row(i: dict) -> str:
    """One extracted row as the conversation needs it. The PHONE travels with it: in a service errand it is the
    datum that RESOLVES («call this number») and the one that separates a business card from a directory link."""
    bits = [str(i.get("title") or "").strip()[:80], str(i.get("price") or "").strip()[:24],
            str(i.get("tel") or "").strip()[:24], str(i.get("url") or "").strip()[:120]]
    return " — ".join(b for b in bits if b)


def hand_sheet_finding(task_id, items, goal: str = "") -> bool:
    """The FINAL sweep's rows → the conversation. Returns whether it pushed.

    WHY THIS EXISTS. `results.intake.push` is the one door for the rows (V2-257) but it has no note path — the
    note is the caller's job, and of the three callers only two do it (`act_api._hand_over`, `owner.py`). The
    third, `dispatch._finalize_web`, does its own `extract_listings()` when the worker finishes or dies and
    writes those rows to the sheet with nobody telling the conversation. Measured 2026-08-24: rows landed in the
    sheet 42-113 s before the last turn and the agent still said «I still have nothing».

    ONLY IF NOBODY HAS TOLD IT YET, and the condition is deliberately about the TAB and not about these rows:
    `act_api._HANDED` holds the tabs whose extraction already went out as a note. If the tab is in there the
    conversation has been told, and the final sweep is mostly the same page again — a second note would be the
    same findings twice, which reads as «it found more» when it found the same.
    """
    rows = [_row(i) for i in (items or []) if isinstance(i, dict)]
    rows = [r for r in rows if r][:3]
    if not rows:
        return False
    try:
        from widgets.navegador.act_api import _HANDED as _already
        if str(task_id) in _already:
            return False
    except Exception:  # noqa: BLE001
        pass                                  # cannot tell → tell the conversation; silence is the worse failure
    what = str(goal or "").strip()[:70] or "la tarea del navegador"
    tail = f" (y {len(items) - len(rows)} más)" if len(items or []) > len(rows) else ""
    try:
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] La tarea del navegador ha terminado y esto es lo que quedó en la página, trabajando en "
            f"«{what}»: {'; '.join(rows)}{tail}. Ya está en la hoja de resultados, pero NADIE se lo ha dicho al "
            f"operador todavía. NÓMBRALO EN ESTE TURNO y di si sirve: si responde a lo que pidió, dáselo con "
            f"nombre, precio o dato y enlace; si no responde, dilo y di qué haces ahora. No digas que no hay "
            f"resultados.")
        return True
    except Exception:  # noqa: BLE001
        return False


def hand_search_rows(rec, res: dict) -> int:
    """A search return → the errand's SHEET. Returns how many rows were handed over.

    V2-320, measured on `kid-friendly-activity-nearby` (2026-08-25 12:37): a worker resolved the errand by
    SEARCH alone — 709 s alive, 8 web searches, 7 returns — and the sheet stayed empty the whole time, because
    a search return had exactly one path out: `hand_web_finding` → a note the brain reads once. The rows were
    never rejected by the sheet (`intake._to_item` keeps a title+url row without a price); they simply had no
    door. Searching is a legitimate way to resolve «activities near X», so its findings are findings.

    Same door as everything else (V2-257: `results.intake.push`), same rows the NOTE carries (`render_search`'s
    top-k — one yardstick for «what the conversation saw» and «what the sheet holds»). Untitled rows (bare
    Perplexity citations) drop at the door, which is the door's own honesty rule. The sheet dedups by
    title+url, so eight overlapping searches converge instead of piling.
    """
    try:
        # V2-376 — WHAT RETURNS FROM A SEARCH IS A LEAD, NOT A CANDIDATE, and until now it entered the
        # sheet without being distinguished from a record extracted from a listing. Measured in
        # `weekend-adventure-sports-bilbao__es` (2026-08-27): **52 «named candidates»** from a SINGLE
        # source, and their titles were pages —«Canyoning descents in Vizcaya: 9 prices and offers
        # 2026», «Bilbao unveils eight free music venues», «Top activity in Bilbao - Book with free
        # cancellation»—. The same pattern as the eight Google titles counted as rental cars that same day.
        #
        # V2-320 is NOT undone and this is what must be preserved: searching is a legitimate way to resolve
        # «activities near X», so its findings are findings and the sheet cannot remain empty. What was
        # missing was for the row to SAY what it is. It travels through `facts`, vocabulary the sheet already
        # preserves —that is how the phone number travels— so there is no need to touch the widget contract.
        rows = [{"title": str(r.get("title") or "").strip(),
                 "subtitle": str(r.get("snippet") or "").strip()[:160],
                 "url": str(r.get("url") or "").strip(),
                 "facts": [{"label": "Origen", "value": "búsqueda web"}]}
                for r in (res.get("results") or [])[:4] if isinstance(r, dict)]
        rows = [r for r in rows if r["title"]]
        # V2-471 — the price the snippet already NAMES travels as the row's datum. Measured in
        # `cheapest-monitor__us` round 12: 46 rows, all `price: None`, while titles carried the figure
        # («…S2725QS for $279.99») — the model's «let me confirm the price» loop was honest, and the
        # delivery backstop cannot append what the rows do not carry. One unambiguous amount in the title
        # (else exactly one in the snippet) is the source's own claim; with several amounts nothing is
        # guessed — absence is said by `fila()`, a guess is invented data (V2-430's whole family).
        for r in rows:
            p = _lone_amount(r["title"]) or _lone_amount(r.get("subtitle") or "")
            if p:
                r["price"] = p
        if not rows:
            return 0
        from widgets.results import intake
        return intake.push(rows, sheet=str(getattr(rec, "sheet", "") or ""),
                           source_name=f"búsqueda web ({str(res.get('source') or 'web')})")
    except Exception:  # noqa: BLE001
        return 0                              # best-effort: losing a row is bad, bringing down the turn is worse
