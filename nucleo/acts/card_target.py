"""Which CARD an act lands on: the card his words name or the one in front, a declared action repaired from what
he said, the payload's reference resolved.
Moved from `nucleo/flash/frontend.py` (refactor2710-05 T-05); its names are read through `_fe`."""
from __future__ import annotations

from loguru import logger

from nucleo.flash import frontend as _fe


def _takes(card: str, action: str, payload) -> bool:
    """Can this card's declared `action` take the call's payload? False only when the card declares its payload
    keys and shares NONE with a non-empty payload (demo pass 66, M3: `markets:show {symbol}` was asked «imagenes
    or markets?» — the viewer's `show` takes items/query, never a symbol). Undeclared → True (no evidence)."""
    keys = {str(k) for k in (payload or {}) if str(k).strip()} if isinstance(payload, dict) else set()
    if not keys:
        return True
    try:
        from nucleo.turn import brief as _tb
        spec = (_fe.declared_actions(_tb._base_of(card)) or {}).get(action) or {}
        declared = spec.get("payload") if isinstance(spec, dict) else None
    except Exception:  # noqa: BLE001
        return True
    if not isinstance(declared, dict) or not declared:
        return True
    return bool(keys & {str(k) for k in declared})


def _screen_now() -> list[str]:
    """The cards on screen, from the normalised state — for a caller whose brief carries no open set. Never raises."""
    try:
        from memory import api as _memapi
        return [str(w).strip().lower() for w in ((_memapi.state() or {}).get("open_widgets") or []) if str(w).strip()]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"which_card: screen unread — {e}")
        return []


def _players_floor(cards) -> float | None:
    """Two PLAYERS that both declare the control are a coin the verdict settles only when sure (`PLAYER_SURE`) —
    the bar `acts.media` already set for the player tools, now for the `widget_data` path too: «turn the volume
    down a bit» read `musica:volume_down` 0.78 and «pause that» `youtube:pause` 0.67, both run in silence (V2-781)."""
    from nucleo.acts import media as _pc
    players = set(_pc.CARD_OF_TOOL.values())
    return _pc.PLAYER_SURE if all(str(c).split("::", 1)[0] in players for c in cards) else None


def which_card(widget_id: str, action: str, *, open_ids=(), brief=None, payload=None,
               min_confidence: float | None = None, operator_text: str = "") -> tuple[str, object]:
    """Which OPEN CARD a declared data-op belongs to, when more than one can do it (V2-740).

    THE SITUATION, in the operator's words (2026-09-21): *«si tengo dos widgets que tienen las mismas
    tools con los mismos nombres, el motor va a dar un 50% de ejecutar un play en un widget o en otro. Y
    cuando eso pase, el flashbrain tendrá que decir: tienes dos tipos de reproductores abiertos y me
    tienes que especificar cuál quieres. Si por contexto sabe identificarlo, perfecto.»*

    And he is right that this is not a defect in the widgets: `youtube` and `musica` share NINE action
    names by design (play, pause, next, previous, volume_up, volume_down, set_volume, play_local, ended).
    Sharing a vocabulary is what makes them both players. What was missing is what happens at that point.

    WHAT WAS ALREADY THERE AND WENT UNREAD. The turn brief has been asking exactly this question since
    V2-726 A4 — `screen_action`, keyed `<instance>:<action>`, enumerated over every open card, carrying
    each card's LIVE rail as its label («youtube — Apolo 11 · pausado»). With two players open it offers
    68 options and tells `youtube:play` from `musica:play`. But the only consumer was
    `repair_action_from_brief`, which fires *«ONLY on the invented-action path»* — so when the model
    picked a card for a DECLARED action, nothing checked it. The verdict was paid for and thrown away.

    THE SHAPE, which is the operator's third sentence and not a new mechanism:

      · **Not ambiguous** → `("keep", None)`. One card can do it, or none but the named one. Nothing is
        read, nothing is asked, no latency: the common path is untouched.
      · **Ambiguous and the brief knows** → `("card", wid)`. The verdict is read with `peek`, never a
        wait, and only a verdict naming THIS SAME ACTION on an open card can move it. A verdict about a
        different action is a different question and is ignored here.
      · **Ambiguous and the brief does not know** → `("ask", [labels])`, which is exactly
        `consent.ASK_WHICH` — the second of the four questions V2-712 already asks, with the count and
        the names. It is not a hardcoded question: the rule is the one the whole system uses, and what
        changes is that the thing in doubt can now be a CARD and not only a row inside one.

    ⚠️ It NEVER changes the action, only the card. «Pausa» stays «pausa»; what it decides is whose.
    Widening it to repair the verb would put two decisions behind one verdict, and the confident-and-wrong
    one would then be twice as expensive.
    """
    from nucleo.turn import brief as _tb
    wid = (widget_id or "").strip().lower()
    name = (action or "").strip()
    if not wid or not name:
        return ("keep", None)
    # Demo pass 66, S2-S3: «compare them side by side» landed on the BARE, blank `results` card while the
    # monitors sat on `results::a51e3e-3`: a data-op on a blank base with ONE non-empty sibling is that one's.
    if "::" not in wid:
        _sib = _fe._the_sibling_with_content(wid, open_ids or ((brief or {}).get("open_ids") if isinstance(brief, dict) else ()))
        if _sib:
            return ("card", _sib)
    # The open set defaults to the BRIEF's: exactly what Jev was offered candidates from, no new state read.
    if not open_ids and isinstance(brief, dict):
        open_ids = brief.get("open_ids") or ()
    if not open_ids:
        open_ids = _fe._screen_now()       # no brief, or one without its open set: the screen itself (V2-781 t2)
    # Who else could do this? `_possible_now` is the question's own refinement: ASK offers only choosable cards.
    cards: list[str] = []
    for other in (open_ids or []):
        other = str(other or "").strip().lower()
        if not other:
            continue
        if name not in (_fe.declared_actions(_tb._base_of(other)) or {}):
            continue
        if not _tb._possible_now(other, name):
            continue
        if other not in cards:
            cards.append(other)
    if wid not in cards:
        cards.append(wid)          # the model's own choice is always a candidate, open set or not
    # A card whose declared action cannot take the call's fields is not a candidate for it (M3, pass 66).
    if payload and _fe._takes(wid, name, payload):
        cards = [c for c in cards if c == wid or _fe._takes(c, name, payload)]
    if len(cards) < 2:
        return ("keep", None)
    # His words name the target and exclude the rest («el vídeo no lo toques», V2-781) before any verdict.
    if operator_text:
        from nucleo.acts import named_target as _nt
        named = _nt.target(operator_text, cards, name)
        if named:
            return ("keep", None) if _tb._base_of(named) == _tb._base_of(wid) else ("card", named)
    if min_confidence is None:
        min_confidence = _fe._players_floor(cards)

    # ⚠️ NO SYNCHRONOUS FALLBACK HERE, by design: the text channel has no brief, and asking synchronously adds a
    # THIRD blocking `choose_sync` (node 3.61 freezes them at two). Without a brief it ASKS, as he described;
    # a probe brief is his cost call. `min_confidence`: equal candidates ask a SURER verdict (player_control).
    choice, _info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=min_confidence)
    owner, _, verdict_action = str(choice or "").rpartition(":")
    if owner and verdict_action == name and owner in cards and _tb.owner_still_open(brief, owner):
        return ("keep", None) if owner == wid else ("card", owner)
    # V2-773 — a CONFIDENT «none»: the model's choice stands («Show me a chart of Apple stock» asked «documento
    # or markets?» since both declare `show`). Only an absent or unsure verdict asks.
    if str(choice or "") == "none" and isinstance(_info, dict) and _info.get("used"):
        return ("keep", None)
    return ("ask", [_tb._card_label(c) for c in cards])


def payload_ref(widget_id: str, action: str, payload, *, named_only: bool = False) -> str:
    """The row a call names in its PAYLOAD: the action's declared id field, else a `name`/`contact` given in
    its place (demo pass 102: `add_phone {name: "Rowan", …}` with `contactId` declared). "" for an action with
    no id field — a creation's name is the new row, not a reference. `named_only`: "" when the id field is set."""
    from widgets import refs as _refs
    if not isinstance(payload, dict):
        return ""
    field = _refs.id_field_for_action((widget_id or "").strip().lower(), (action or "").strip())
    if not field or (named_only and str(payload.get(field) or "").strip()):
        return ""
    for k in (field, "name", "contact"):
        if str(payload.get(k) or "").strip():
            return str(payload.get(k)).strip()
    return ""


def absent_widget_misroute(widget_id: str, action: str, item: str, *,
                           resolved: bool = True, named_widget: str = "", payload: dict | None = None) -> bool:
    """A LOOSE PRONOUN as the item, on a card that is neither open nor named → the verb mis-routed.

    The incident (2026-07-21, «hay que cancelarlo»): the model hooked the verb «cancelar» to `agenda.drop`
    on a widget that was NOT on screen and that the turn never named, while the pronoun's antecedent lived
    in the CONVERSATION (an ITV appointment). Acting there operates a closed card; the turn is escalated
    RAW instead, so the worker gets the recent window verbatim and resolves it with context.

    ⚠️ And the bug that shipped with the first version, twice: `looks_like_bare_ref("")` is True BY DESIGN
    (an empty ref IS bare), so the guard fired on every CREATE action — `add_meeting` never carries an item
    — and escalated «añade una cita con el dentista mañana» whenever the agenda was not already open. It
    only makes sense where the action REALLY points at an existing row, which is what a declared `*Id`
    field says.

    EXTRACTED because it was written TWICE, and the probe's copy says so in its own comment («ESPEJO del
    guard del provider … mismo fix que nucleo.py»). That is the R3 class this repo has a rule against: if
    two channels need the same rule, extract it — a copy costs a marker and leaves two places to edit, and
    both copies had to be fixed separately when the CREATE bug was found.
    """
    from nucleo.flash import router as _router
    from widgets import refs as _refs
    wid = (widget_id or "").strip().lower()
    # The row may be named in the PAYLOAD under the declared key, not only `item` (demo pass 2026-09-28,
    # full16 E2: «open it» → `open {name: "Inworld AI"}` was escalated as a loose pronoun).
    if not str(item or "").strip():
        item = _fe.payload_ref(wid, action, payload)
    # `resolved=False`: an unresolved reference reaches the same question; the probe takes the pronoun path.
    bare = (bool(_refs.id_field_for_action(wid, (action or "").strip()))
            and _router.looks_like_bare_ref(str(item or "")))
    if resolved and not bare:
        return False                                  # nothing to point AT: a creation is never a misroute
    try:
        from memory import api as _memapi
        open_now = {str(w).strip().lower() for w in ((_memapi.state() or {}).get("open_widgets") or [])}
    except Exception:  # noqa: BLE001
        open_now = set()
    return wid not in open_now and (named_widget or "").strip().lower() != wid


def card_decision(widget_id: str, action: str, *, brief=None, ask_phrase: str = "", payload=None, open_ids=(),
                  min_confidence: float | None = None, operator_text: str = "") -> dict:
    """`which_card`, shaped into what a CALL SITE does with it — so neither channel grows to hold this.

    Both callers live in files the architecture ratchet lists (the voice provider and `probe.py`), and its
    rule is «extract a module, do not raise the ceiling». Ten lines of routing and its archaeology in each
    of them is the shape that made them god files in the first place, so the decision AND its consequences
    are assembled here and each call site spends four lines applying a plan.

    Returns `{card, ask, label, text, extra}` — `card` is the widget to act on (unchanged when nothing
    moved), `ask` is the sentence to say INSTEAD of acting (empty when there is nothing to ask), and the
    rest is one observability event or nothing. It writes no state and speaks to nobody: the caller does.
    `open_ids` is the screen when the brief carries none (see `acts.media`); empty = the brief's set.
    """
    wid = (widget_id or "").strip().lower()
    route, alt = _fe.which_card(wid, action, open_ids=open_ids, brief=brief, payload=payload, min_confidence=min_confidence,
                            operator_text=operator_text)
    if route == "card":
        return {"card": str(alt), "ask": "",
                "label": "🎯 la orden era de OTRA tarjeta — la reubica el veredicto de pantalla",
                "text": f"{wid}→{alt}:{action}",
                "extra": {"id": str(alt), "from": wid, "action": action, "src": "jev"}}
    if route == "ask":
        # ONE question, ONE phrase: `ask_which_item` is consent's ASK_WHICH sentence and this IS that verdict (a
        # card, not a row). Cards are named as he knows them («Música, YouTube»), never by id, and the control
        # is parked so «el de la música» runs it (V2-781, `named_target`).
        from nucleo.flash import card_receipt as _receipt
        from nucleo.acts import named_target as _nt
        ids = [str(c).split(" — ", 1)[0] for c in (alt or [])]
        _nt.park(action, ids)
        try:
            from i18n import langs as _langs
            code = str(getattr(_langs.current_language(), "code", "") or "")   # the question's own language
        except Exception:  # noqa: BLE001
            code = ""
        names = [_receipt.display_label(str(c), code) for c in (alt or [])]
        return {"card": wid,
                "ask": (ask_phrase or "").format(cands=", ".join(names[:3])) or "",
                "label": "❓ varias tarjetas pueden hacer eso — pregunto en cuál",
                "text": f"{wid}:{action}",
                "extra": {"id": wid, "action": action, "cands": names[:4]}}
    return {"card": wid, "ask": "", "label": "", "text": "", "extra": {}}


def resolve_undeclared_action(widget_id: str, action: str, text: str,
                              *, timeout_s: float | None = None, brief=None,
                              blocking_ok: bool = True) -> tuple[str, str | None]:
    """The ONE decision for an action the manifest does NOT declare, shared by the voice rail
    and the probe mirror (parallel implementations must not drift).

    Returns ("canvas", verb) — the existing boundary rule, a canvas verb smuggled in as a data
    op maps to the deterministic canvas tag; ("repair", declared_action) — Jev named the declared
    action the user means, so the call continues through the normal mode flow (FAST / CONFIRM /
    ESCALATE, confirm gates untouched); or ("escalate", None) — today's path, unchanged.

    ⚠️ `blocking_ok=False` is the VOICE channel, and it is not a preference (V2-726 A2, audit
    finding 9). With no brief to read, the `repair_action` fallback below opens a synchronous
    `urlopen` — from inside the provider's `async def`, that is up to two seconds of frozen event
    loop shared with STT, TTS and barge-in. The voice path normally HAS a brief, which is why the
    static ratchet never saw this: the hole only opens when `turn_brief.ask` returned None with Jev
    still enabled (an exception swallowed during assembly), and then the fallback looks like an
    ordinary local call. A caller that cannot afford to block says so, and gets today's escalate.
    """
    from widgets import runtime
    wid = (widget_id or "").split("::", 1)[0].strip().lower()   # the BASE declares; an instance is one card of it
    name = (action or "").strip()
    if not wid or not name or runtime.get(wid) is None:
        return ("escalate", None)
    verb = _fe.canvas_verb(name)
    if verb:
        return ("canvas", verb)
    # The brief answers without a trip; `repair_action` is the blocking fallback: no brief AND it may block.
    fixed = _fe.repair_action_from_brief(wid, brief) if brief is not None else None
    if not fixed and brief is None and blocking_ok:
        fixed = _fe.repair_action(wid, name, text, timeout_s=timeout_s)
    if fixed:
        return ("repair", fixed)
    return ("escalate", None)
