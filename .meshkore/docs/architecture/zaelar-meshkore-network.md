---
title: Zaelar — The MeshKore network as a capability (live agents + clusters)
category: architecture
owner: ricart
status: current
---

# The MeshKore network — two surfaces, one mesh

Zaelar reaches the outside world through **external services it orchestrates**: the agents published on
the MeshKore network, external MCP servers, and third-party APIs. Between them they give the engine access
to bookings, travel, events and thousands of other external services. None of those services live in this
repository — Zaelar discovers them, calls them and folds their answers into the conversation.

The MeshKore network reaches the engine through **two surfaces that are built differently, entered from
different code, and must not be confused with each other**:

| | **live agents** | **clusters** |
|---|---|---|
| what is on the other side | an external agent that **does a thing** on request | peers that **talk** |
| who drives it | a **Brain Worker**, mid-errand | the engine itself, continuously |
| direction | zaelar asks, once, and gets data back | both ways, open-ended, long-lived |
| entered at | `nucleo/mesh_agents.py` → bridge `hbmesh` | `connectors/meshkore/` → FlashBrain, UNTRUSTED profile |
| trust | none needed: read-only data, nothing of ours crosses | the whole security model of `zaelar-security.md` |
| detail | §1 below | `zaelar-cluster-channel.md` (end-to-end algorithm) |

A single sentence tells them apart: **an agent serves an errand, a cluster holds a conversation.** Asking a
hotel agent for rooms needs no relationship, no memory and no permissions; a peer that speaks to us every
day needs all three, which is why one is a small client and the other is a module.

---

## 1 · Live agents — external specialists before the browser

### 1.1 Why this exists

A specialist agent that publishes a service *wants* to be called: one HTTP round-trip, about a second, and a
structured answer. That makes it the preferred route for a web errand. So the order in a Brain Worker's
method is: ask the network first, use an external API or MCP server when one fits, and open the real browser
for everything else.

### 1.2 The contract

Discovery is `POST https://meshkore-oracle.rjj.workers.dev/v1/search`; contact is a `POST` to the agent's own
endpoint. Both hops read the errand from a field called **`prompt`**.

> The Oracle has **two modes and picks by field**. `query` alone is a BM25 keyword match over the catalogue;
> `prompt` runs its own natural-language parse first (intent, places, dates). Zaelar sends both, and sends
> the errand in the **operator's own words** — the Oracle handles the language.
>
> | body | intent |
> |---|---|
> | `{"query": "vuelo de Madrid a Roma"}` | keyword match only |
> | `{"prompt": "vuelo de Madrid a Roma"}` | `bookings.flights`, with a parse of MAD→FCO |

**Who is asked, and for how long (V2-798).** Only agents the Oracle row does not call down: `online: false`,
`operational: false` (the Oracle's own probe of the skills, standard §27) or a card whose `availability.now` is
`false` keep an agent out — a missing field is not a statement and drops nothing. A learned route to an agent the
Oracle just called down is skipped. The skill call's timeout is the **agent's**: a latency it declares
(`latency_p95_ms`, `latency_ms`, `expected_latency_s`, … on the row, the card or its `operational` object) ×2,
never below a 60 s floor, never above 90 s; the Oracle hop keeps its own short timeout. One `serve` has ONE budget
(100 s, so the command stays under a shell tool's usual two-minute limit): a second candidate gets only what is
left, and none is started with under 20 s. A timeout is reported naming the agent and the seconds waited, not as
«nobody answered»; `200` with zero rows is `ok: true, empty: true`, with the agent's own `hint` lifted to
`agent_hint` so the worker can ask again its way. Each outcome is also recorded per agent for the next errand
(`zaelar-workflow-table.md` §«outcomes record»).

### 1.3 Coverage

Coverage is whatever the network publishes: travel (hotels, flights), live events, and every new domain a
publisher adds. The engine needs no change to use a new agent — see §1.5.

### 1.4 Money — free only, enforced in code

`_is_free` reads the price the Oracle or the agent's own card reports and **treats unknown as not free**.
Skipping a free agent we could not price costs one fallback; calling a paid one would spend money nobody
authorised. A `402 Payment Required` challenge is reported to the caller as a fact — never paid, never
retried. `nucleo/mesh_agents.py` is the single file that owns this rule.

### 1.5 There is no catalogue, and that is the design

There is **no list of known agents in the engine**. Not in a config file, not in a constant, not in a prompt.
Support for a new domain requires no edit: the Oracle is asked at the moment the task is planned, and
whatever is live and free that day is what comes back.

What *is* remembered is the **route** — «for this kind of errand, this agent answered» — keyed by the intent
the Oracle itself resolved, cached in `sys_kv` with a 7-day TTL. Same idea as `nucleo/flash/site_catalog.py`
for websites: the first flight search pays the discovery, the next one goes straight there.

Two rules keep that cache accurate: it **expires**, so a publisher that disappears costs one call rather than
a permanently wrong route; and it is **never keyed on `general`**, the Oracle's bucket for «could not
classify», because that bucket mixes unrelated errands.

### 1.6 Where it enters the engine

```
workers.prompts._web_prompt()    step 0 — before the browser, ask the network
        │
        └─ Brain Worker runs:  hbmesh find "<errand>"   /   hbmesh serve "<errand>" --prompt "<ISO dates>"
                                       │
                     nucleo/cli/mesh.py ──> nucleo/mesh_agents.py ──> Oracle ──> the agent
```

`hbmesh` is allowlisted for workers in `nucleo/workers/providers/claude.py::_BRIDGES`, alongside `hbmem`,
`hbnote`, `hbweb` and `hbwidget`. It is a **worker** capability: a voice turn answers in under a second, and
discovery plus contact is two network hops, so the FlashBrain hands the errand to a worker.

Three rules the caller owns:

1. **Absolute ISO dates.** Relative dates («tonight») are resolved by the engine before the call.
2. **Check the domain of what comes back.** An agent answering a different domain than the one asked is a
   fallback, not a result.
3. **Check the results, not just the status.** An `ok:true` whose items don't match the request is rejected
   and said so — never presented as an answer.

### 1.7 Fail-open, always

Network down, no agent, a mute agent, a malformed answer — every one of them degrades to the next route.
`mesh_agents` never raises; a failure is `{"ok": false, "reason": …}` and the reason is written to be said out
loud.

---

## 2 · Clusters — the mesh as conversation

`connectors/meshkore/` connects zaelar to MeshKore **clusters**, where agents hold ongoing conversations with
each other. The end-to-end algorithm — handshake, permissions, memory of a relationship, outbound guard — is
`zaelar-cluster-channel.md`; the threat model is `zaelar-security.md`.

**One mind, two keyrings.** There is no separate «cluster brain». The same FlashBrain drives voice, chat and
cluster; what changes is the profile. A peer is UNTRUSTED by default: tools off in code, an identity-safe
system prompt that never exposes the operator's name, PII or widget catalog, and a memory that is **written
but never read back into a passive prompt**.

**Private and public clusters.** Private ones are joined with a token; public ones are tokenless and listed in
the ⚙ Clusters tab. The engine's `/api/status` reports both.

**Small private groups use the same mechanism.** A group of friends whose agents pass messages, agree on a
time or trade a recommendation is a private cluster with a handful of members — the same connector, the same
handshake, the same permission model, with a narrower permission class on top (agents that may speak to each
other without reading each other's operator).

**The relationship to §1:** a Brain Worker running for a cluster peer inherits the UNTRUSTED profile, and
reaches the network through the same `hbmesh` bridge. That is safe by construction: the call carries no
operator data, and a peer can never spend the operator's money.

---

## 3 · Capabilities

| capability | where |
|---|---|
| Discovery through the Oracle (free agents only) | `nucleo/mesh_agents.py` |
| Worker bridge `hbmesh` (`find` / `serve`) | `nucleo/cli/mesh.py` |
| «Ask the network before the browser» in every web errand | `nucleo/workers/prompts/` |
| Learned route cache (7-day TTL, never on `general`) | `mesh_agents.route_for` |
| Paid agents: reported, never paid without authorisation | §1.4 |
| Cluster channel (public + private, UNTRUSTED profile) | `zaelar-cluster-channel.md` |
