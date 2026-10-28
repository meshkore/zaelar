# The workflow table — what serves this kind of errand, and is that still true?

**Module:** `nucleo/workflows/` · **Table:** `workflows` (`memory/schema.py`, facade in `memory/api.py`)
**Sibling doc:** `zaelar-action-map.md` — read that one too, because the first
question anyone asks here is how the two differ.

## What it answers

Before an errand pays for a browser or a Brain Worker, something has to answer *«do we already know a faster
way to do this?»*. The workflow table is where that answer lives — including the two cases a success-only
route cache cannot hold:

- *«nobody on the mesh serves this domain yet»* is remembered too, so the next errand of that kind skips the
  Oracle round trip and goes straight to the next channel;
- domains the Oracle files under `general` (events, shopping, wellness…) get their own key here.

## Anatomy

| piece | what it is |
|---|---|
| `domains.domain_of(text)` | the KEY. One regex sweep over normalised text → a domain (`restaurant`, `wellness`, `housing`…) or `""`. No model, no network, no tokens. |
| `store.plan(text)` | the ANSWER. `Plan(domain, channels, ask_mesh, known_empty)`, decided from the table alone. |
| `store.learn` / `note_empty` / `forget` | writing what a real errand proved. |
| `store.site_for(domain)` | the browser channel, **derived** from `site_catalog`, never copied. |
| table `workflows` | one row per `(domain, channel)`: `status`, `rank`, `source`, `target`, `evidence`, `ttl_s`, `checked_at`. |

Channels, best first: `connector` (built into the engine) → `mesh` (an agent on the network) → `browser`
(the trusted site) → `worker` (always available, always slowest). `mesh` is written by learning and `browser`
is derived; `connector` and `worker` are declared channels a row can carry.

## The three rules that keep it honest

**1 · It is not a second action map.** `action_map` maps a PHRASE to a LOCAL action on a widget and never
leaves the machine. This maps a DOMAIN of errand to the ORDER of EXTERNAL channels. They meet only in that
both are looked up by a function and cost zero prompt tokens. **When a phrase is a local action, the action
map wins and this is never consulted** — the fast lane must not grow a network call.

**2 · It is not a third opinion about what «reservar mesa» means.** `domain_of` asks
`site_catalog.category_of` FIRST, because that is already the shared classifier behind `errand_kind` and
`flash/router_guards`, whose own comment warns that *«two components deciding the same thing end up
disagreeing»*. Only the verticals the catalogue cannot name are added — wellness, health, train, taxi,
car_rental, delivery, shipping, housing, home_services, image — and they are named after **the Oracle's own
intents**, so both sides of the wire share one key.

One deliberate widening: the fallbacks cover `hotel` even though `category_of` demands a booking verb there
(it stays strict so a hotel research errand stays in the research funnel with its own budget).
That reasoning is about **routing** — which worker gets the task. This table never routes; it only answers
«is there a faster channel?». So the strict rule keeps owning `kind`, and the loose one owns the cache key.

**3 · It is never carried in a prompt.** A table that had to be pasted into the context to be useful would
cost more than the work it saves. The per-turn cost is one regex sweep plus one indexed SELECT. The only
thing that ever reaches a prompt is **one line, and only when something is known** —
`dispatch_prompts._known_route_line`, which names the agent that already served this kind of errand, or says
the mesh is known empty so the worker does not make the trip. When nothing is known it writes nothing.

## TTL, and why the negative one is shorter

`TTL_OK_S` 7 days, `TTL_NONE_S` 3 days. A negative answer is the one most likely to stop being true: new agents
join the MeshKore network all the time. Rows expire ON PURPOSE, or the
system decides once, in its first week, and is wrong for ever.

A row whose `source` is `operator` is never overwritten by learning — a human decision outranks a
measurement, the same invariant the action map holds for a seed row the user disabled.

## The distinction that makes the negative row SAFE

`find()` returns **`reached`**. A negative row is written only when the Oracle actually answered and had
nobody. **An outage is never cached** — that would turn one bad minute into three bad days.

The key is `reached`, not the coverage value: against the real Oracle a genuinely uncovered vertical returns
an **empty** coverage, and `find` keeps «answered with nobody» and «did not answer» as two distinct outcomes
so only the first is ever cached.

A warm lookup answers from one indexed SELECT — no network and no model.

## Its sibling keyed by SOURCE: the outcomes record (V2-798)

The workflow table is keyed by the **kind of errand** («restaurants»). Some facts belong to a **source** instead —
a site host, a network agent id, a search provider — and hold for every errand that touches it: *this site
answered 403*, *this page's text could not be extracted*, *this provider is out of quota until Thursday*, *this
agent did not answer within its timeout*, *this agent answered with no rows and said how to ask again*, and the
positive one, *this source gave usable rows*. Those live in `nucleo/source_outcomes.py` (one memory KV entry,
`sources:outcomes`, bounded to 150 sources).

| door that observes it | outcome |
|---|---|
| `nucleo/cli/nav.py` — a response annotated with `wall` | `wall` (by host, `www.` stripped) |
| `nucleo/cli/nav.py` — `extract` on a page | `served` (≥1 named row) or `extract_empty` |
| `nucleo/mesh_agents.ask` | `served`, `empty` (with the agent's hint) or `timeout` (by agent id) |
| `nucleo/workers/providers.note_tool_blindness` | `quota` for `search:<provider>`, until the provider's own reset time |

Rules that keep it a **resource and not a fence** (brain-worker doctrine §5):

- **Newest fact wins, and everything expires.** `served` lives 14 days; `wall` 3 days, `extract_empty` 2,
  `timeout`/`empty` 1, `quota` until the reset the provider stated (12 h if it stated none). A repeated failure
  lives ×n (capped at ×3) — one 403 can be a bad minute, three are a policy. A later success resets the repeats.
- **The same sighting is counted once.** A wall stays on screen across several actions on one page; reports within
  two minutes refresh the date without inflating the count.
- **It orders, it never drops.** `mesh_agents.serve` asks an agent whose newest fact is a hard failure (`wall`,
  `quota`, `timeout`) AFTER the others — it is still asked when it is the only one. `empty` and `extract_empty`
  depend on the query and demote nothing.
- **It is read, not obeyed.** The worker's step 0 (both worker prompts, via `_mesh_first_block`) gets ONE line —
  at most six sources, newest first, each with its date — and **nothing at all** when nothing current is known. The
  full record is `python -m nucleo.source_outcomes` (`--all` includes expired facts), JSON like its sibling bridges.
