# Context packs — prompt that belongs to a PHASE

**What this document is for:** before adding a sentence to the turn's system prompt, decide WHICH of the four
kinds of prompt it is. Three of them already had a home; this is the fourth, and putting a phase instruction
in one of the other three is a specific, repeatable defect.

Built by V2-675 (2026-09-11). Code: `nucleo/context_packs/`. Seam: `nucleo/flash/prompt.py::build_flash_system`.

---

## 1 · Four kinds of prompt, and only one of them is a pack

| kind | true when | lives in | cached? |
|---|---|---|---|
| identity + resources | ALWAYS — it is what the agent IS | `_lang_lock` + `_flash_layer` | yes, it IS the stable prefix (V2-536) |
| style directive | a preference the operator gave this session | `_directive_block` | no |
| **phase context** | **a STRETCH of the relationship** | **`context_packs.compose()`** | **never** |
| live state | this second | `live_state()` | never |

The ordering in the composed prompt is: identity → memory/recall → **directive → packs** → live state.

- A pack comes AFTER the operator's own directive because **his instruction is read last of the two**.
- A pack comes BEFORE live state because "true for this stretch" is a weaker claim than "true right now".
- A pack is **outside the stable prefix on purpose**. A phase ends mid-conversation; a cached block keeps
  being spoken after its own phase is over, which is the exact failure the mechanism exists to prevent.

Every pack's contribution is wrapped in a header that says it is TEMPORARY. Without it, a model reads a phase
instruction as a permanent fact about who it is — the one thing a pack must never become.

---

## 2 · The contract

```python
Pack(id, title, order, active: Callable[[], bool], block: Callable[[], str])
```

`active` and `block` are callables, not values: a phase can end mid-conversation, and a pack whose text was
computed once would keep speaking after its phase closed.

**Three rules the registry enforces:**

1. **A pack that is over is never composed again.** `active()` is asked every turn; once archived it answers
   False for good.
2. **A pack costs nothing while inactive.** The check must be a cheap LOCAL read — a settings flag, a memory
   slot. Never a model call, never network: it runs on the hot path of every turn.
3. **A pack never raises, and the catch is PER PACK.** One net around the whole section would let a single
   broken pack silently delete every other phase's contribution, producing a turn that looks exactly like the
   steady state.

Registration is **explicit** (`_install()`), never auto-discovery: a prompt that appears because a file was
dropped in a folder is a prompt nobody decided to pay for.

---

## 3 · Writing a pack

**The three questions, in order:**

1. **What FACT opens it, and what fact closes it?** Both have to be readable locally and cheaply. A phase
   whose start or end can only be decided by a model is a phase that costs a model call per turn.
2. **Where does the closing flag live?** `settings` AGENT_KEYS if the phase is about the RELATIONSHIP (a
   factory reset should re-run it); INSTALL_KEYS if it is about the machine; a memory slot if it is a fact
   about the person.
3. **What does the block tell the model to DO?** Not what it IS. A fact-shaped block survives the phase in
   the model's reading of itself long after the text stops being sent.

**And the one rule about content:** a pack **never re-lists what another layer already carries.** The resource
layer puts the live widget/tool catalog in the same prompt; a second inventory written by hand is how two
lists end up disagreeing — measured twice (V2-594, V2-603). Name the FAMILIES, which are architecture and do
not go stale, and point at the catalog.

**Closing a phase: three exits, cheapest first.** Deterministic (a fact we can read) → a judge, off the hot
path and RATIONED → a cap. Fail-open in the direction that keeps the phase RUNNING when the judge cannot be
reached: skipping a phase silently is worse than running it a few turns too long. But fail-CLOSED when the
flag itself is unreadable: a block that cannot be turned off costs every turn forever.

**Watch turns from the bus** (`turn.completed`), not from the voice provider. Zero coupling, and it covers the
voice channel and the probe channel from one place because `observer.turn_detail` is where both close.

---

## 4 · The pack that exists: `introduction`

Active while `settings.intro_done` is falsy **and** a language has been chosen (while the language ceremony is
open nobody has spoken yet — V2-672).

It tells the model to lead the conversation toward meeting each other: one thing per turn, after whatever the
operator asked for, dropped if he deflects. It lists what is still unknown (`operator_name`, `location`,
`treatment`) so the phase narrows as it goes, and it caps the self-description at two or three capabilities —
the operator's own limit: *«tampoco hace falta que se pase cuatro minutos hablando»*.

Exits: knowing his name (free — the memory writes it on its own) · a judge after 4 turns, then one call every
4 · a cap at 30.

**The phrasebook (V2-674) stands aside while any pack is active.** During the introduction «hola» is not small
talk — it is the first move of a conversation that has somewhere to go. The gate lives in the LANE, not in the
pack: a lane that never reaches a model would never read the pack's text.

---

## 5 · Observability

A pack closing emits `kind="phase"` (family `flash`), with the reason and the turn count. It happens once per
phase per install, which is exactly why it needs its own kind rather than being lost among the turn's rows.
`context_packs.state()` reports what is registered and what is running.

---

## 6 · What this is NOT

- **Not a rule store.** The operator's standing rules are `style_policy` and the directive; those are his and
  persist. A pack is ours and expires.
- **Not memory.** A pack reads facts; it never writes them. What the operator says during a phase is written
  by the memory heart like any other turn.
- **Not a router.** A pack adds context. It does not choose tools, gate actions or decide a channel.
- **Not a place for a permanent capability.** If a sentence should still be true in a year, it belongs in the
  resource layer, where it is cached and paid for once.
