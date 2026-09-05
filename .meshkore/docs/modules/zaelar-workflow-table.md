# The workflow table — what serves this kind of errand, and is that still true?

**Module:** `nucleo/workflows/` · **Table:** `workflows` (`memory/schema.py`, facade in `memory/api.py`)
**Initiative:** V2-594 · **Sibling doc:** `zaelar-action-map.md` — read that one too, because the first
question anyone asks here is how the two differ.

## What it answers

Before an errand pays for a browser or a Brain Worker, something has to answer *«do we already know a faster
way to do this?»*. That answer had nowhere to live. `nucleo/mesh_agents` kept a learned route, but only for
**success**, and only under an Oracle intent it would key on — so the two most expensive cases were exactly
the ones it could not hold:

- *«nobody on the mesh does wellness»* was discarded every time, so every massage errand paid the Oracle
  round trip again **and then paid a language model to narrate the emptiness back**;
- anything the Oracle classified `general`, which was events, shopping and wellness — most of it.

## Anatomy

| piece | what it is |
|---|---|
| `domains.domain_of(text)` | the KEY. One regex sweep over normalised text → a domain (`restaurant`, `wellness`, `housing`…) or `""`. No model, no network, no tokens. |
| `store.plan(text)` | the ANSWER. `Plan(domain, channels, ask_mesh, known_empty)`, decided from the table alone. |
| `store.learn` / `note_empty` / `forget` | writing what a real errand proved. |
| `store.site_for(domain)` | the browser channel, **derived** from `site_catalog`, never copied. |
| table `workflows` | one row per `(domain, channel)`: `status`, `rank`, `source`, `target`, `evidence`, `ttl_s`, `checked_at`. |

Channels, best first: `connector` (built into the engine) → `mesh` (an agent on the network) → `browser`
(the trusted site) → `worker` (always available, always slowest). Today only `mesh` is written by learning
and `browser` is derived; `connector` and `worker` are declared and unwritten.

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
(V2-477 kept it strict so the `hotel-under-15-days` errand stays in the research funnel with its own budget).
That reasoning is about **routing** — which worker gets the task. This table never routes; it only answers
«is there a faster channel?». So the strict rule keeps owning `kind`, and the loose one owns the cache key.

**3 · It is never carried in a prompt.** A table that had to be pasted into the context to be useful would
cost more than the work it saves. The per-turn cost is one regex sweep plus one indexed SELECT. The only
thing that ever reaches a prompt is **one line, and only when something is known** —
`dispatch_prompts._known_route_line`, which names the agent that already served this kind of errand, or says
the mesh is known empty so the worker does not make the trip. When nothing is known it writes nothing.

## TTL, and why the negative one is shorter

`TTL_OK_S` 7 days, `TTL_NONE_S` 3 days. A negative answer is the one most likely to stop being true: the mesh
gained two agents (`tablescout`, `spascout`) the afternoon this was built. Rows expire ON PURPOSE, or the
system decides once, in its first week, and is wrong for ever.

A row whose `source` is `operator` is never overwritten by learning — a human decision outranks a
measurement, the same invariant the action map holds for a seed row the user disabled.

## The distinction that makes the negative row SAFE

`find()` returns **`reached`**. A negative row is written only when the Oracle actually answered and had
nobody. **An outage is never cached** — that would turn one bad minute into three bad days.

This was not designed in, it was measured: the first version keyed on `coverage == "none"`, and the unit test
passed because it MOCKED that value. Against the real Oracle a genuinely uncovered vertical returns an
**empty** coverage, so the saving never fired where it mattered. Fixing that exposed that `find` had been
flattening «answered with nobody» and «did not answer» into one empty list — the same fault V2-487 fixed a
layer below.

## Measured

A plumber errand: **1.02 s cold → 0.0002 s warm**, no network and no model.
