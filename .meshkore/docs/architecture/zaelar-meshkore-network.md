---
title: Zaelar — The MeshKore network as a capability (live agents + clusters)
category: architecture
updated: 2026-08-19
owner: ricart
status: current
---

# The MeshKore network — two surfaces, one mesh

MeshKore is not a vendor zaelar calls and not a dependency it could swap. It is the network zaelar is a
citizen of, and it reaches the engine through **two surfaces that are built differently, entered from
different code, and must not be confused with each other**:

| | **live agents** | **clusters** |
|---|---|---|
| what is on the other side | somebody else's agent that **does a thing** on request | peers that **talk** |
| who drives it | a **Brain Worker**, mid-errand | the engine itself, continuously |
| direction | zaelar asks, once, and gets data back | both ways, open-ended, long-lived |
| entered at | `nucleo/mesh_agents.py` → bridge `hbmesh` | `connectors/meshkore/` → FlashBrain, UNTRUSTED profile |
| trust | none needed: read-only data, nothing of ours crosses | the whole security model of `zaelar-security.md` |
| detail | §1 below | `zaelar-cluster-channel.md` (end-to-end algorithm) |

A single sentence tells them apart: **an agent serves an errand, a cluster holds a conversation.** Everything
else follows from that. Asking `roomrover` for hotels needs no relationship, no memory and no permissions; a
peer that speaks to us every day needs all three, which is why one is ~270 lines and the other is a module.

---

## 1 · Live agents — the mesh as an alternative to opening a browser

### 1.1 Why this exists

A browser is how zaelar does a web errand when nothing better exists. It is not the *good* way, it is the
last resort: driving a real Chromium through a booking site means fighting the exact defences those sites
deploy against automation. Measured on real runs (V2-167): one errand spent its entire life on Booking's
`chal_t=` anti-bot challenge, another walked into Google's `/sorry/index` CAPTCHA, a third re-photographed
the same page for eleven minutes. None of them delivered anything.

The same errands over the mesh are **one HTTP round-trip, about a second, and no defence to fight** — the
agent is a publisher who *wants* to be called. So the order in a Brain Worker's method is: ask the mesh
first, open a browser only when nobody answers.

### 1.2 The contract

Discovery is `POST https://meshkore-oracle.rjj.workers.dev/v1/search`; contact is a `POST` to the agent's own
endpoint. Both hops read the errand from a field called **`prompt`**, and this is the single most expensive
detail on this page:

> The Oracle has **two modes and picks by field**. `query` alone is a BM25 keyword match over the catalogue;
> `prompt` runs its own NL parse first. Keyword-matching an English catalogue with Spanish words finds
> nothing — and answers `200` with an empty list, which reads exactly like «the mesh has nobody for this».
> Measured the same minute, 2026-08-19:
>
> | body | intent | agents |
> |---|---|---|
> | `{"query": "vuelo de Madrid a Roma"}` | `general` | — |
> | `{"prompt": "vuelo de Madrid a Roma"}` | `bookings.flights` | `aerocast`, plus a parse of MAD→FCO |
>
> This cost a wrong conclusion that survived a day in three files: that the Oracle «is markedly better in
> English» and errands should be translated before asking. It is not a language problem. Both fields are now
> sent, and the errand goes in the **operator's own words**, which is what the upstream skill doc said all
> along.

A real agent given `{"query": …}` at least answers `400 missing_fields`. The Oracle answering *something* is
what made this hide.

### 1.3 What is live today

Verified live on 2026-08-19, each with a real call, not a listing:

| agent | domain | price | measured |
|---|---|---|---|
| `roomrover` | hotels (LiteAPI → Booking/Expedia/RateHawk) | **free** | 10 real properties, price + rating + booking link, ~1 s |
| `aerocast` | flights (Duffel, 300+ carriers) | **free** | 10 offers MAD→FCO from €58,39, with carrier and flight number |
| `ticketlumen` | live events (Ticketmaster Discovery) | **free** | 10 events with venue, date and ticket link |

Two things about that table matter more than its contents. First, **it is not in the code anywhere** — see
§1.5. Second, it is a snapshot: the honest statement of coverage is «hotels, flights and events today, and
whatever is published tomorrow».

Where the mesh does **not** answer, measured the same day: restaurant *booking* (`bookings.restaurants`
resolves, but no agent serves it), second-hand shopping, and anything local-service shaped. Those keep the
browser, and that is the ordinary case, not a failure.

### 1.4 Money — free only, enforced in code

`_is_free` reads the price the Oracle or the agent's own card reports and **treats unknown as not free**. The
asymmetry is deliberate: skipping a free agent we could not price costs one fallback to the browser, calling
a paid one costs money nobody authorised. A `402 Payment Required` challenge is reported to the caller as a
fact — never paid, never retried. When paid agents become a product decision, `nucleo/mesh_agents.py` is the
single file that changes.

### 1.5 There is no catalogue, and that is the design

There is **no list of known agents in the engine**. Not in a config file, not in a constant, not in a prompt.
Support for a new domain requires no edit: the Oracle is asked at the moment the task is planned, and
whatever is live and free that day is what comes back. A static list would be stale the first time somebody
published something and would need curating by us forever.

What *is* remembered is the **route** — «for this kind of errand, this agent answered» — keyed by the intent
the Oracle itself resolved, cached in `sys_kv` with a 7-day TTL. Same idea as `nucleo/flash/site_catalog.py`'s
genetics for websites, and for the same reason: the first flight search pays the discovery, the next one goes
straight there.

Two rules keep that cache from becoming a lie: it **expires**, so a publisher that disappears costs one
failed call rather than a permanently wrong route; and it is **never keyed on `general`**, the Oracle's
bucket for «could not classify», because that bucket is a normal answer for a query it still serves
(«entradas de teatro en Madrid» → intent `general`, agent `ticketlumen`) and caching under it would send the
next plumber errand to the theatre agent.

### 1.6 Where it enters the engine

```
dispatch_prompts._web_prompt()   PASO 0 — before the browser, ask the mesh
        │
        └─ Brain Worker runs:  hbmesh find "<errand>"   /   hbmesh serve "<errand>" --prompt "<ISO dates>"
                                       │
                     nucleo/mesh_cli.py ──> nucleo/mesh_agents.py ──> Oracle ──> the agent
```

`hbmesh` is allowlisted for workers in `nucleo/workers/claude_session.py::_BRIDGES`, alongside `hbmem`,
`hbnote`, `hbweb` and `hbwidget`. It is a **worker** capability: the FlashBrain does not call the mesh
directly in a voice turn, because a turn has to answer in under a second and discovery plus contact is two
network hops.

Three rules the caller owns, all of them paid for by a measured failure:

1. **Absolute ISO dates.** Asked for «esta noche» on 2026-08-19, `roomrover` resolved check-in to 2025-06-21
   and returned zero; the same request with `2026-09-10` returned ten.
2. **Check the domain of what comes back.** The mapping is loose at the edges — an English restaurant query
   is answered by a *hotel* agent. An agent answering the wrong domain is a fallback to the browser, not a
   result.
3. **Check the results, not just the status.** Live run, 2026-08-19: asked for theatre in Madrid,
   `ticketlumen` answered `ok:true` with ten events that were all the same Banksy *exhibition*. The worker
   rejected them and said so, which is the behaviour V2-057 asks for and the reason that run is a success and
   not a fabrication.

### 1.7 Fail-open, always

Mesh down, no agent, a mute agent, a malformed answer — every one of them degrades to exactly the behaviour
zaelar had before any of this existed. `mesh_agents` never raises; a failure is `{"ok": false, "reason": …}`
and the reason is written to be said out loud, because «no hay ningún agente para esto» is worth hearing
*before* zaelar opens a browser for four minutes.

---

## 2 · Clusters — the mesh as conversation

The second surface is older and much deeper: `connectors/meshkore/` connects zaelar to MeshKore **clusters**,
where agents hold ongoing conversations with each other. The end-to-end algorithm — handshake, permissions,
memory of a relationship, outbound guard — is `zaelar-cluster-channel.md`; the threat model is
`zaelar-security.md`. What belongs *here* is how it relates to everything above.

**One mind, two keyrings (V2-069).** There is no separate «cluster brain». The same FlashBrain drives voice,
chat and cluster; what changes is the profile. A peer is UNTRUSTED by default: tools off in code, an
identity-safe system prompt that never exposes the operator's name, PII or widget catalog, and a memory that
is **written but never read back into a passive prompt**.

**Two kinds of cluster exist today.** Private ones, joined with a token, and public ones — tokenless, opened
in V2-086, which is what the ⚙ Clusters tab lists. The engine's `/api/status` reports both
(`meshcore·sin peers, commons·wanderer` on this machine at the time of writing).

**Friend clusters are the near-future shape, and they are not a new mechanism.** A group of friends whose
agents pass messages, agree on a time, arrange a meeting, or trade a recommendation is a **private cluster
with a handful of members** — the same connector, the same handshake, the same permission model. What they
will need that does not exist yet is a permission class narrower than «peer» (agents that may speak to each
other but not read each other's operator) and the product surface to create one. Neither is built.

**Publishing posts to a cluster is not built.** The channel today carries messages between agents, not a
feed. When it arrives it will be a cluster capability, not a new integration.

**The relationship to §1:** a cluster peer can already escalate work, and a Brain Worker running for that
peer inherits the UNTRUSTED profile — which means it reaches the mesh through the same `hbmesh` bridge. That
is safe by construction (the mesh call carries no operator data), but it is the seam to think about first if
paid agents ever land: a peer must never be able to spend the operator's money by asking nicely.

---

## 3 · State of development — read this before planning anything

| capability | state | where |
|---|---|---|
| Discovery through the Oracle (free agents only) | **built, verified live** | `nucleo/mesh_agents.py` |
| Worker bridge `hbmesh` (`find` / `serve`) | **built, verified live in a real dispatch** | `nucleo/mesh_cli.py` |
| PASO 0 «ask the mesh before the browser» | **built, verified live** | `nucleo/dispatch_prompts.py` |
| Learned route cache (7-day TTL, never on `general`) | **built** (unit-tested; not yet observed expiring in production) | `mesh_agents.route_for` |
| Hotels / flights / events over the mesh | **working against 3 live free agents** | see §1.3 |
| Restaurant booking, shopping, local services | **no agent on the mesh** — browser keeps them | — |
| Paid agents (402 challenge) | **reported, never paid** — by decision, not by omission | §1.4 |
| Reputation feedback after a good call | **not built** — the Oracle accepts it, we do not send it | open in V2-169 |
| Publishing our own agent to the mesh | **not built** | open in V2-169 |
| Mesh from a voice turn (no worker) | **not built, and deliberate** | §1.6 |
| Cluster channel (public + private, UNTRUSTED profile) | **built** | `zaelar-cluster-channel.md` |
| Friend clusters (small private groups) | **not built** — needs a narrower permission class | §2 |
| Posts / feed on a cluster | **not built** | §2 |

Open work and its evidence: **`.meshkore/roadmap/initiatives/V2-169-integracion-red-meshkore.md`**. That
initiative is the place where anything about this integration gets recorded — a broken call, a wrong
language, an instruction the agents misread — so that this table stays true and nobody has to re-measure the
mesh to find out where we are.
