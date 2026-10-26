---
title: The slow lane
updated: 2026-10-26
status: proposed (V2-811) — documented before the code so every adoption lands in one picture
---

# The slow lane — a second model seat for work that can wait

**What it is.** A model seat, `slow_process`, beside the ones that answer the turn: a cheaper, slower model for
background work that needs discernment, not conversation — classify a message, pull fields out of a text, summarise
one item, paraphrase a memory, decide whether a watched source has something new. It is **off by default** and,
off, the engine runs exactly as without it. On, nothing in FlashBrain or the Brain Worker changes: the lane is
adopted call site by call site, like the decision model was.

**Where it points.** Any OpenAI-compatible endpoint: the table's default pair (a cheap hosted titular and a
stand-in on another provider), a local server on the user's machine (then background work never leaves it), or
an agent on the MeshKore network that routes a request to a backend by cost. The engine treats all three the
same: one request format, an optional bearer, an answer that may be `202` and polled.

**The rule that governs it: nothing breaks.** A slow seat that is down, saturated or wrongly chosen costs at most
MORE tokens on the usual model — never a lost turn, never a lost job. Every adopter already fails open to today's
path, and the lane keeps that contract.

**Who decides what goes slow — once.** Never per item, never a model asked «slow or fast?» on every message. The
decision is one closed question to the decision model in a trip that already happens — when a rule is written,
when a complex task is commissioned — stored on that rule or task (`lane`, `lane_by`, `lane_why`) and flipped when
the user complains about the rule. At run time the field is read.

**Shape of a big job: map slow, reduce fast.** The plan and the final synthesis stay on the worker's model; the
per-item steps are slow jobs. A watch (V2-810) is the same shape with one item at a time, driven by events, so an
engine left on all day thinks only when something arrives or a job is due.

**Pieces** (`V2-811`): the row in `config/models.default.json` · `config/v2 §slow_process` · the door
`memllm.chat_sync(…, via="slow")` · the thin client `nucleo/slow/client.py` · an explicit egress family · later a
durable queue `slow_jobs` for bulk producers · the `slow` timeline family · the ⚙ card.
