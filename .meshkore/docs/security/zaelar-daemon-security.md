# The Zaelar Local Daemon — threat model, guards, and what is deliberately not covered

**Audience:** anybody deciding whether to install this on their own computer, and anybody changing its code.
**Scope:** `engine/daemon/` only. The engine's own security model is `zaelar-security.md`; the cloud's is not in
this repository.

---

## 1. What it is, in one paragraph

A small HTTP service that runs on the user's own machine and gives the Zaelar engine two things a container
cannot have: the user's **files**, under a per-folder permission circuit, and (later) a **real browser** on
their screen for authentication and CAPTCHAs. It binds loopback, it is standard library only, and it is
**additive** — the engine works exactly as it does today when the daemon is absent.

It is **read-only**. There is no code path in `daemon/fs/` that opens a file for writing, and a test asserts
that absence across the whole package.

---

## 2. The threat model, stated so it can be argued with

The interesting attacker is **not** somebody on the network. The daemon never listens off loopback, and if the
bind address were ever widened by accident a peer check refuses anything that is not this machine.

The interesting attackers are three, in order of how much they should worry you:

| # | Who | What they can already do | What they must not get |
|---|---|---|---|
| **A** | **A web page the user has open** | `fetch('http://127.0.0.1:45817/…')` from any site in the world, and re-point its own DNS at 127.0.0.1 | Any file, and even the knowledge that the daemon exists |
| **B** | **Another process running as the user** | Read `daemon.json`, connect to the port, send anything | Nothing extra — it already *is* the user; the goal is that it cannot get MORE than the user granted, and cannot do it invisibly |
| **C** | **A prompt-injected agent** — the cloud engine, driven by text from a hostile web page | Ask the daemon for any path it likes, in a loop | Anything outside the folders the human chose, and anything on the never-served list even inside them |

**C is the one that motivates the design.** A and B are conventional; C is the reason the boundary is enforced
in code by a single gate rather than described to a model in a prompt. A model can be talked into asking for
`~/.ssh/id_rsa`. It cannot be talked into being allowed.

---

## 3. The guards, and what each one is actually for

### 3.1 Admission — `daemon/security/guards.py`

A **pure function over headers**. It touches no socket and no disk, which is what lets every rule be exercised
in both directions without a running server. Five checks, in this order:

1. **The peer is loopback.** Belt to the bind's braces, for the day somebody widens the bind address.
2. **Nothing that smells of a browser.** `Origin`, `Sec-Fetch-Site`, `Sec-Fetch-Mode` or `Referer` present →
   refused. Browsers attach those; a server-side client never does. This holds *even if the token leaked into a
   page*, which is what makes attacker A structurally impossible rather than merely unlikely.
3. **The `Host` header names a loopback address and this daemon's port.** ⚠️ This is the one that closes the
   hole in check 2, and it is not hypothetical. A page on `evil.example` whose DNS is re-pointed at 127.0.0.1
   makes a **same-origin** request, and a same-origin request carries **no `Origin` header at all**. Modern
   browsers still send `Sec-Fetch-Site: same-origin`, so check 2 usually catches it — "usually" is one header
   away from nothing. What betrays the rebind is `Host`: the browser still names the site it *thinks* it is on.
   Exact match, never a prefix — `startswith("127.0.0.1")` is satisfied by `127.0.0.1.evil.example`.
4. **A body must be declared `application/json`.** A browser may send `text/plain`,
   `application/x-www-form-urlencoded` or `multipart/form-data` cross-origin with **no preflight** — those are
   "simple requests", the one shape that bypasses a CORS policy without asking. Requiring JSON forces a
   preflight, and the preflight never succeeds (no CORS headers are ever sent; `OPTIONS` is 405). **This closes
   the browser vector on its own**, independently of checks 2 and 3.
5. **The bearer token**, compared with `hmac.compare_digest`. 32 bytes of urandom, generated at first run,
   stored `0600`.

**Every refusal looks identical from outside**: one `401`, one sentence, whichever check fired. Telling a caller
which guard they tripped turns "try things until something works" into "read the error and adapt". The precise
reason goes to the audit log.

### 3.2 The permission circuit — `daemon/fs/roots.py`

The one gate. Nothing else in `daemon/fs/` builds a `Path` from caller input.

1. Non-empty string; `~` expanded.
2. Windows syntax that reaches *past* a name is refused before anything else looks at it — an alternate data
   stream (`notes.txt:hidden`), a UNC share (`\\server\share`), a device name (`NUL`, `COM1`). After resolution
   these are invisible: an ADS keeps the visible filename, so every name check sees `notes.txt` while the read
   returns the stream.
3. Must be **absolute**. Relative paths are refused rather than joined to something.
4. **Resolved** — normalizes `..`, follows every symlink, and on Windows expands 8.3 short names.
5. The **resolved** path is checked against the never-served list.
6. The **resolved** path must lie inside one of the **resolved** allowed roots.

Steps 4–6 in that order are the point. Checking before resolving is the classic hole. **Resolving the roots too
is the other half** and is not symmetry for its own sake: on macOS `~/Documents` is frequently a symlink into
iCloud, so a circuit that resolved only the request would refuse the user their own documents — a failure in
the *other* direction, with every escape test still green.

### 3.3 Opening — `daemon/fs/safeopen.py`

The circuit proves a path is inside an allowed folder; then it returns, and the caller opens it. The filesystem
is not frozen in between. Three checks:

- **`O_NOFOLLOW`** — the resolved path had no symlinks left in it, so a link in the final component *now* means
  something changed in the window.
- **`S_ISREG`** — a pipe, device or socket is not a document. Measured with the check removed: the read returns
  an **empty string**, so the agent reports a blank document; on a blocking read with a writer that never
  writes, the thread never comes back at all. The open uses `O_NONBLOCK` so the descriptor can be inspected
  before anybody reads.
- **The descriptor's own path**, re-checked against the boundary. `F_GETPATH` on macOS, `/proc/self/fd/N` on
  Linux. This catches the swap of a directory *in the middle* of the path, which the other two cannot see.
  ⚠️ **Windows has neither and is a stated limit**, not a solved problem: there, what remains is step 4 of the
  circuit plus `S_ISREG`.

### 3.4 The never-served list — `daemon/security/denylist.py`

Names that are refused at any depth **even inside a folder the user granted**, because "the user allowed their
home directory" must not mean "the agent may read the SSH key". Five shapes — segments, exact names, filename
prefixes (`.env` is never one file: a project has `.env`, `.env.local`, `.env.production`), key extensions, and
Windows path syntax.

Matching is normalized for **case** (these filesystems are usually case-insensitive, so `.SSH` would walk
straight through) and for **Unicode form** (macOS stores names decomposed, so the composed spelling of the same
name is the same file to the OS and must be the same name here).

It covers keys and credential stores, cloud and package-registry credentials, **browser cookie stores** (session
tokens for every site the user is signed into — the highest-value target on the disk after the SSH key),
`.git/**` (a remote URL can carry a token; the project's actual code stays perfectly readable), and shell
history (people paste tokens into terminals).

**Not overridable in v1, on purpose.** An override switch is the first thing a confused user flips and the first
thing a prompt-injected agent asks for.

The list errs toward refusing: a false positive costs one refused file **with a reason attached**, a miss costs
a credential. `private` is deliberately *not* on it — it is an ordinary English word and `Documents/private/` is
a folder real people have.

### 3.5 Granting

A fresh install can read **nothing**. "Documents by default" is what the wizard *pre-checks*, never what is
readable before the wizard has run.

`grant()` refuses: the never-served list, the whole disk, **the home directory**, and system folders. Home is
refused because a name list is not a boundary — home is the machine minus a list, and it holds thousands of
things that are not on it (app databases, mail stores, local storage). That is not what a user thinks they are
agreeing to.

### 3.6 The record — `daemon/audit.py`

One line per operation, **allowed and refused**. Refusals are the half that earns the file: a run of
`outside_allowlist` against one folder is something probing the boundary, and a run of `bad_token` is something
talking to the daemon that has no business doing so. Both are invisible if only successes are kept.

⚠️ **Unauthorized attempts used to leave no trace at all** — the old shape answered `401` before it recorded
anything. They are recorded now, and **collapsed** by `daemon/security/throttle.py` so a flood cannot push the
interesting line off the end of a rotated log, with a small ramping delay that makes flooding cost the sender
more than it costs us. There is **no lockout**: every process on this machine already runs as the user, so a ban
would be trivially resettable by an attacker and permanently annoying for the person who mistyped their own
token.

The log is itself sensitive — a list of every path the agent opened is a map of somebody's life — so it is
`0600`, in a `0700` directory, like the token beside it.

---

## 4. What is deliberately **not** covered

Saying this plainly is part of the model. A limit somebody can read is a limit somebody can close.

| Not covered | Why, and what would close it |
|---|---|
| **TOCTOU on Windows** | No `O_NOFOLLOW`, no cheap `F_GETPATH`. Would need the Win32 API (`GetFinalPathNameByHandle`), which means leaving the standard library. |
| **A process running as the user reading `daemon.json` directly** | It already *is* the user; it does not need the daemon. The token protects against A and C, not B. |
| **Content-based secret detection** | The list is name-based. A file called `notes.txt` containing an API key is served, and should be — guessing at contents would refuse the user their own documents. |
| **A signed update channel** | No self-updater exists, on purpose: an update path that downloads and executes without a signature is remote code execution by design. Upgrading is re-running the installer. |
| **Rate limits per capability** | The budgets are per request (read cap, search time and file budgets), not per hour. A hostile local caller can read every allowed file slowly; it could also just read them directly. |
| **Anything about the relay** | The cloud path does not exist yet. `X-Zaelar-Relay` is honoured in the audit log now so the trail is not retrofitted after the fact, but nothing grants a remote caller anything. |

---

## 5. Changing this code

- The admission decision is a **pure function**. Add a guard there, not in the handler.
- **Every rule gets a counterweight in the same test file.** A daemon that refuses everything passes any battery
  of leak tests and is, to the user, a broken product with a good excuse. The macOS iCloud case is the standing
  example: it breaks legitimate access while every escape test stays green.
- **Disarm what you add.** Mutate the guard, *assert the mutation landed*, watch the node go red, restore. A
  disarm that comes back green is a mutation that was not applied until proven otherwise.
- Nodes: **7.34** (the circuit, both directions), **7.35** (not reachable from a browser), **7.36** (boot
  wiring), **7.37** (the installed process, end to end), **7.40** (a hostile local process), **7.41** (build and
  install).
