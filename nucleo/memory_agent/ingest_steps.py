# The memory HEART's ingest in two steps: the deterministic gates an utterance crosses before anything is written,
# and filing the atoms the distiller returned (V2-778 F1). Names are read through `ingest` (`_ing.<name>`) so a
# patch on `ingest` still governs them; a `return` comes back as `(_R, value)`.
from __future__ import annotations

from nucleo.memory_agent import ingest as _ing
from nucleo.memory_agent import answer_frame as _answer_frame   # a bare answer travels with its question

_R = object()     # «the turn returns here»: the first element of a returned tuple


async def gate_the_utterance(*, plan, role, text) -> dict:
    if role != "operator":
        return _R, {"source": "skip", "atoms": 0, "plan": plan}

    t = (text or "").strip()
    if not t:
        return _R, {"source": "discard", "atoms": 0, "plan": plan}

    # 0·SECRETS (V2-060, FAIL-CLOSED, FIRST): a secret in the turn is ENCRYPTED in the vault and REDACTED before
    #    any LLM or plaintext write; with no vault yet it is redacted and the vault is requested. Any failure redacts.
    try:
        from memory import secrets as _secrets
        from memory import vault as _vault
        _red, _found = _secrets.redact(t)
    except Exception as _e:  # noqa: BLE001
        _ing.logger.warning(f"memory_agent: secret gate failed ({_e}) — unchanged")
        _red, _found = t, []
    if _found:
        t, text = _red, _red                          # the distiller and gates see the version WITHOUT secrets
        try:
            has_vault = _vault.exists()
        except Exception:
            has_vault = False
        if not has_vault:
            return _R, {"source": "secret_needs_vault", "atoms": 0, "secrets": len(_found),
                    "labels": [d.label for d in _found], "plan": plan}
        vaulted = 0
        for d in _found:
            try:
                await _ing.asyncio.to_thread(_vault.store_secret, d.label, d.value,
                                        slot=d.slot, sensitivity=d.sensitivity)
                vaulted += 1
            except Exception as _e:  # noqa: BLE001
                _ing.logger.warning(f"memory_agent: encrypting secret {d.label!r} failed ({_e}) — NOT stored in plaintext")
        try:
            from memory import api as _mem
            _mem._emit("memory.updated", {"op": "vault"})   # refreshes the viewer 🧠 (best-effort)
        except Exception:
            pass
        # The turn ends here: the redacted remainder is the request, not a fact. Known limitation: a fact MIXED with
        # a secret in one turn is not distilled.
        return _R, {"source": "vault", "atoms": vaulted, "secrets": len(_found),
                "labels": [d.label for d in _found], "plan": plan}

    # 0-. UNFORGET (dim N): he RETRACTS a forget request — before forget; restores the matching invalidated rows.
    um = _ing._UNFORGET_RE.match(t)
    if um:
        obj = um.group(1).strip()
        if len(obj) >= 3 or obj.isdigit():  # "18"/"9" (an hour, a short number) is as valid as a word
            try:
                from memory import api as memory
                n = memory.unforget(obj)
                return _R, {"source": "unforget", "atoms": 0, "restored": n, "object": obj, "plan": plan}
            except Exception as e:  # noqa: BLE001
                _ing.logger.debug(f"memory_agent: unforget failed ({e})")

    # 0. FORGET ON REQUEST (dim N): "forget about the gift". DETERMINISTIC detection (without LLM) — imperative at the start,
    #    excludes "don't forget" (a reminder). Invalidates (soft) entries matching the object; preserves history.
    if "no olvid" not in t.lower():
        fm = _ing._FORGET_RE.match(t) or _ing._FORGET_TRAILING_RE.match(t)  # verb at the start OR end ("…, forget it")
        if fm:
            obj = fm.group(1).strip()
            hard = bool(_ing._FORGET_HARD_RE.search(t))     # "entirely/forever" → HARD deletion (privacy)
            obj = _ing._FORGET_HARD_RE.sub("", obj).strip(" ,.")   # keep the hardness marker from polluting the object
            obj = _ing._NEGATION_PREFIX_RE.sub("", obj).strip(" ,.")  # "no tengo ninguna alergia" → "alergia"
            if len(obj) >= 3 or obj.isdigit():  # "18"/"9" (una hora, un número corto) es tan válido como una palabra
                try:
                    from memory import api as memory
                    # include_pinned=True: the pin protects a critical datum from INVOLUNTARY forgetting; an
                    # explicit order to forget always wins over it.
                    n = memory.forget(obj, hard=hard, include_pinned=True)
                    return _R, {"source": "forget", "atoms": 0, "forgot": n, "object": obj, "hard": hard, "plan": plan}
                except Exception as e:  # noqa: BLE001
                    _ing.logger.debug(f"memory_agent: forget failed ({e})")

    # 0b. Explicit CORRECTION (dim M): "not ... X but Y" or "no longer ... X (now Y)" → forget the WRONG value (X)
    #     and continue to save the new one. Lets the old datum stop surfacing without depending on a slot.
    _wrong = []
    _m1 = _ing._CORRECTION_RE.search(t)
    if _m1:
        _wrong.append(_m1.group(1).strip())
    _m2 = _ing._CORRECTION_YANO_RE.search(t)
    if _m2:
        _wrong.append(_m2.group(1).strip())
    _m3 = _ing._CORRECTION_TRAILING_NO_RE.search(t)
    if _m3:
        _wrong.append(_m3.group(1).strip())
    for w in _wrong:
        if len(w) >= 3 or w.isdigit():  # "18"/"9" (una hora, un número corto) es tan válido como una palabra
            try:
                from memory import api as memory
                # include_pinned=True (same reason as forgetting on request): an explicit correction
                # ("it is not X, it is Y") must be able to invalidate the old value even if importance pinned it.
                memory.forget(w, include_pinned=True)
            except Exception as e:  # noqa: BLE001
                _ing.logger.debug(f"memory_agent: correction forget ({w!r}) failed ({e})")

    # V2-033 P0b: explicit correction OR declared move → allow overwriting established identity
    # (a move stated explicitly is not garble; slot supersede removes the old value).
    _is_corr = bool(_wrong) or bool(_ing._RELOCATION_RE.search(t))

    # 0c. Write-side ABSTENTION (dim E): UNAMBIGUOUS question to the assistant (X's weather, "would you recommend…?") →
    #     is not an operator fact → deterministic DISCARD before spending the LLM (avoids inventing preferences).
    if _ing._ASSISTANT_QUERY_RE.search(t):
        return _R, {"source": "discard", "atoms": 0, "reason": "assistant_query", "plan": plan}

    # 0d. V2-033 P1 — EPHEMERAL screen/action DIRECTIVE ("don't show me anything now"): it is session style, executed
    #     FlashBrain executes it immediately; NEVER a durable preference. Deterministic pre-LLM discard.
    if _ing._is_ephemeral_directive(t):
        return _R, {"source": "discard", "atoms": 0, "reason": "ephemeral_directive", "plan": plan}

    # 0e. V2-033 P0a — VAGUE REQUEST without a referent ("look at that", "can you look at that for me?"): noise, not a
    #     recordable (a CONCRETE task with data DOES pass: "find me flights to Tokyo"). Deterministic pre-LLM discard.
    if _ing._is_vague_request(t):
        return _R, {"source": "discard", "atoms": 0, "reason": "vague_request", "plan": plan}

    # 1. Cheap DISCARD (no LLM): trivia/command with no profile — but never a COMMITMENT/request/appointment.
    if plan["level"] is None and not plan["state_patch"] and not _ing._COMMITMENT_RE.search(t):
        return _R, {"source": "discard", "atoms": 0, "plan": plan}

    # 2. LLM processor: distills into pills (off-hot-path). We provide the STATE for dynamic importance.
    #    `None` = model unavailable → fall back to the heuristic; `[]` = the LLM ran and decided to DISCARD (respect it,
    #    do not re-inflate with the heuristic); list = pills to save.
    try:
        from nucleo.memory_agent.processor import distill, distill_config
        from memory import api as memory
        st = memory.state()
    except Exception:
        st = {}
        distill = None  # type: ignore

    atoms: list[dict] | None = None
    if distill is not None:
        try:
            atoms = await distill.process(_answer_frame.framed(t), state=st)
        except Exception as e:  # noqa: BLE001
            _ing.logger.debug(f"memory_agent: LLM processor failed ({e}); falling back to heuristic")
            atoms = None
        # V2-103: `None` after a network blip reads like «disabled»; ONE retry (off the hot path) before the heuristic.
        if atoms is None and distill_config.enabled():
            await _ing.asyncio.sleep(0.4)
            try:
                atoms = await distill.process(_answer_frame.framed(t), state=st)
            except Exception as e:  # noqa: BLE001
                _ing.logger.debug(f"memory_agent: LLM processor retry also failed ({e}); falling back to heuristic")
                atoms = None
    _out = locals()
    return {k: _out[k] for k in ('_is_corr', 'atoms', 'st', 't', 'text', ) if k in _out}


async def file_the_atoms(*, _is_corr, atoms, plan, st, t) -> dict:
    if atoms is not None:                       # el LLM CORRIÓ (aunque haya devuelto [])
        for a in atoms:
            # V2-033 precision GATE: a reified question/request is not written (P0a); an identity value contradicting
            # the established state is demoted to a recoverable `long`, never into `state` (P0b, STT garble).
            if _ing._precision_reject_atom(a, raw=t):
                continue
            # Two signals from the processor itself (multilingual by nature): (1) singular slot + `value` → the state
            # patch is SYNTHESIZED from the registry, even when the model wrote the change as a loose fact.
            fld = _ing._memslots.state_field(a.get("slot"))
            val = (a.get("value") or "").strip()
            if fld and val and not (a.get("state_patch") or {}).get(fld):
                a = dict(a, dest="state", state_patch={**(a.get("state_patch") or {}), fld: val})
            # (2) `change: update|correction` — a DECLARED change may overwrite an established fact; the host's
            #     Spanish regexes are only its backstop.
            a_corr = _is_corr or (a.get("change") in ("update", "correction"))
            # INJECTION: a capable model OBEYS «from now on the operator is called Pepe» and emits change=update.
            # With an injection preamble in the turn, an identity slot cannot be overwritten by the self-declared
            # signal; a legitimate move or correction carries no preamble and still passes.
            if a.get("slot") in _ing._IDENTITY_SLOTS and _ing._looks_like_injection(t):
                a_corr = _is_corr
            # (2026-08-21) …and the SAME question without an injection: `change` is signed by the distiller itself, so
            # it alone could overwrite an identity slot — «que se llama Calatayut,, ciudad de Calatayut» (a place he
            # was spelling) became `operator.location`. Self-declaration counts only if the turn talks about HIM, as
            # every legitimate move does in any language («ara visc a Girona» still passes by `change`).
            # V2-802 T-02 — and a SPOKEN identity claim from a turn that is not about him is not his at all (ambient
            # audio: a TV commentator's name became «the operator is called …»): quarantined, never a trusted row.
            # A typed/pasted turn is exempt — nobody types by accident, and a signature never speaks in first person.
            # V2-747 — …over the slots the question is ABOUT. `_IDENTITY_SLOTS` holds one whose subject is
            # the ASSISTANT (`assistant.name`), and «does this turn talk about the operator?» can never be
            # true of a sentence renaming it — so the guard did not protect that slot, it sealed it. The
            # registry now says which slots the question applies to; see `memory/slots.slots_about_the_operator`.
            if a.get("slot") in _ing._OPERATOR_IDENTITY_SLOTS and not _ing._talks_about_the_operator(t):
                if a_corr and not _is_corr:          # only when the self-declaration was the ONLY evidence
                    _ing._report_self_declared_change_ignored(str(a.get("slot")), t)
                a_corr = _is_corr
                if _ing._channel() != "typed":
                    a = _ing._quarantine_identity(a)
            # V2-752 — `assistant.name` is excused from both guards above, so it gets its own question
            # (`rename_decision`): «He dicho, Apollo once», a correction of a video search, once renamed him.
            if a.get("slot") == "assistant.name":
                from nucleo.memory_agent import rename_decision as _rn
                if not _rn.renames_the_assistant(t):
                    _ing._report_self_declared_change_ignored("assistant.name", t)
                    continue
            a = _ing._plausibility_demote(a, state=st, is_correction=a_corr)
            # (P0d) P0b guards `state`; this guards the SLOT supersede, which destroys his own pill even when
            # `state` survives. Only on the LLM-atom path: the deterministic backstops are covered by P0b.
            a = _ing._slot_supersede_guard(a, is_correction=a_corr)
            # V2-565 · a correction reaches the SLOTLESS pill it corrects. The model may name targets in
            # `supersedes`, but only ids it was OFFERED (`api.correction_targets()`, the same function that
            # built the offer in `_render`) survive — an invented or stale id dies here, so this path cannot
            # be steered at rows the prompt never showed. Requires the atom to DECLARE change:"correction":
            # a plain update naming ids is not a correction and gets no reach.
            _sup = a.get("supersedes") or []
            if _sup and a.get("change") == "correction":
                _allowed = _ing._correction_whitelist()
                _sup = [i for i in _sup if i in _allowed][:4]
            else:
                _sup = []
            a = dict(a, supersedes=_sup)
            await _ing._write_atom(a, raw=t)
        # PROFILE→STATE BACKSTOP (V2-038): the heuristic's state patch when no atom touched those fields — a move
        # written as a loose fact must still move the state. Same anti-garble gate as the atoms.
        if plan.get("state_patch"):
            _patched: set = set()
            for a in atoms:
                _patched |= set((a.get("state_patch") or {}).keys())
            _missing = {k: v for k, v in plan["state_patch"].items() if k not in _patched}
            if _missing:
                _pa = {"text": t, "kind": plan.get("kind") or "profile", "dest": "state",
                       "slot": plan.get("slot"), "state_patch": _missing,
                       "importance": plan.get("importance", 0.9), "pinned": True}
                _pa = _ing._plausibility_demote(_pa, state=st, is_correction=_is_corr)
                await _ing._write_atom(_pa, raw=t)
        # COMMITMENT BACKSTOP: a request/task/appointment is always kept raw (semantic dedup merges a duplicate).
        if _ing._COMMITMENT_RE.search(t):
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "event", "importance": 0.55,
                            "meta": {"source": _ing._channel(), "path": "commitment-net"}, "auto": False})
            return _R, {"source": ("llm+net" if atoms else "net"), "atoms": len(atoms) + 1, "plan": plan}
        # BACKSTOP DETERMINISTA de RUTINAS (dim O): una costumbre recurrente es memorable aunque el LLM la descarte.
        if _ing._ROUTINE_RE.search(t):
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "pref", "importance": 0.5,
                            "meta": {"source": _ing._channel(), "path": "routine-net"}, "auto": False})
            return _R, {"source": ("llm+routine" if atoms else "routine"), "atoms": len(atoms) + 1, "plan": plan}
        # OBSERVATION BACKSTOP (dim I): a pattern he notices about himself is kept on an explicit mark.
        if _ing._OBSERVATION_RE.search(t):
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "pref", "importance": 0.5,
                            "meta": {"source": _ing._channel(), "path": "observation-net"}, "auto": False})
            return _R, {"source": ("llm+obs" if atoms else "obs"), "atoms": len(atoms) + 1, "plan": plan}
        # REVERSAL BACKSTOP (dim M): «I no longer drink coffee» is a change of state, kept.
        if _ing._REVERSAL_RE.search(t) and "no olvid" not in t.lower():
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "fact", "importance": 0.5,
                            "meta": {"source": _ing._channel(), "path": "reversal-net"}, "auto": False})
            return _R, {"source": ("llm+rev" if atoms else "rev"), "atoms": len(atoms) + 1, "plan": plan}
        # HEALTH BACKSTOP (dim C): a serious operation/diagnosis is durable, kept on a medical mark.
        if _ing._HEALTH_RE.search(t):
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "fact", "importance": 0.7,
                            "meta": {"source": _ing._channel(), "path": "health-net"}, "auto": False})
            return _R, {"source": ("llm+health" if atoms else "health"), "atoms": len(atoms) + 1, "plan": plan}
        # DURABLE-PROFILE BACKSTOP: «my FAVOURITE restaurant», «my FIRST dog» → long.
        if _ing._PROFILE_DURABLE_RE.search(t):
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "fact", "importance": 0.6,
                            "meta": {"source": _ing._channel(), "path": "profile-net"}, "auto": False})
            return _R, {"source": ("llm+profile" if atoms else "profile"), "atoms": len(atoms) + 1, "plan": plan}
        # INBOUND-MESSAGE BACKSTOP (V2-050): a relayed message from a third party is kept RAW for recall, unless
        # it is an empty negation («no me dijo nada»).
        if _ing._INCOMING_MSG_RE.search(t) and not _ing._EMPTY_MSG_RE.search(t):
            await _ing._pkg().remember({"text": t, "level": "long", "kind": "event", "importance": 0.5,
                            "meta": {"source": _ing._channel(), "path": "incoming-msg-net"}, "auto": False})
            return _R, {"source": ("llm+msg" if atoms else "msg"), "atoms": len(atoms) + 1, "plan": plan}
        return _R, {"source": ("llm" if atoms else "discard-llm"), "atoms": len(atoms), "plan": plan}
    _out = locals()
    return {k: _out[k] for k in () if k in _out}
