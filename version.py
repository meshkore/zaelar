#
# version.py — ENGINE VERSION SEAL (V2-074). To KNOW, without ambiguity, what code is running in an
# instance and which version generated each line of observability. It arose from a real need (2026-07-26): after
# several restarts with new code, there was no way to confirm that the live instance and the timeline lines
# belonged to the updated version.
#
# Exposes: a semantic VERSION (bumped by hand for notable changes) + the short git SHA (changes only on each
# commit) + the process start time. Everything is cached (the SHA is read once; subsequent reads take µs).
#
import os
import subprocess
import time

# Semantic version of the engine — bump it by hand when closing a notable block of changes.
#
# Latest (3.29): THE CLOSE LICENSE GOES LIVE IN BOTH CHANNELS. show_target.close_has_order is the one
# close-order reader the voice provider and the probe share: grammar first, a confident Jev "close"
# licenses a model [[close]] the grammar misses, a negated/narrated close vetoes even a confident Jev,
# anything else keeps the V2-635 discard bit-for-bit (the source-shape ratchet still passes unchanged).
# The ask fires once per turn, fail-soft to grammar-only. Restart required (hot path).
#
# Previous (3.28): JEV GOES GENERIC, AND THE CANVAS GETS A VERB. nucleo/jev.py generalizes from the single
# hardcoded request_type question to a reusable Choice primitive (choose_sync/ask_async/resolve_choice)
# with the filler API kept as a thin wrapper — node 3.58 passes unchanged. On top, show_target.py asks one
# canvas question per turn (show/close/neither) through a resolver both channels will share; no provider or
# probe wiring yet, so the hot path is bit-identical and no restart is required for this commit.
#
# Previous (3.27): THE PYRAMID, AND THE CIRCLE THAT CLOSES ITSELF. V2-705/V2-706, 2026-09-15, opened by the
# operator halting the session — «arreglamos una cosa y estropeamos otra… debería funcionar de forma
# piramidal» — after a `cancel_meeting {}` deleted 100 events from his real Google Calendar. One funnel for
# every widget mutation (`widgets/contract.py`): a destructive action with an EMPTY selector is refused,
# never widened to «all», and a payload spelled with a synonym is renamed to the manifest before it is
# judged. ONE tolerant matcher for contacts, calendar and messages (`widgets/textmatch.py`). And the
# meeting errand measured end to end: message → «Ok» → 20 s → real calendar row, Meet link minted, link
# sent back — with a conversation that now REMEMBERS its gestión while the commitment is ahead, so the other
# side can call it off and the row that errand wrote is unwritten without asking. Written where every spawn
# reads it (`.meshkore/context/principles.md`): mechanisms, not rules — a rail on CONSEQUENCES stays, a rail
# on JUDGEMENT goes. Also: voice metrics had been dead since 09-10 (a copied import), and the WhatsApp bridge
# is now a sidecar `stop` owns and `restart` keeps.
#
# Previous (3.19): THE WAIT SAYS WHAT IT IS DOING. The splash was a spinning ring under one fixed sentence,
# held until the app modules finished — tens of seconds on a cold account Machine, and an unattended spinner
# is indistinguishable from a hang. V2-558 gives both shells ONE narration: an outer progress arc, a line
# that changes every couple of seconds, and a wake-up story chosen by a real signal (`/healthz`), not a timer.
# It carries its own ES/EN strings because the i18n bundle needs the very engine being waited for — which is
# what used to leak raw `boot.encendiendo` keys on a cold start. The property under test (node 4.105, rendered
# in a phone-sized Chromium) is the honest one: the arc is asymptotic, capped, and cannot close on its own —
# only the app announcing itself fills it. A bar that arrives while nothing happens is the lie this screen is
# famous for.
#
# Previous (3.18): SEARCHING FOR LISTINGS, AND SAYING WHAT WE ALREADY HAVE. V2-556 makes the marketplace hunt
# ONE tool: FlashBrain calls `search_listings` and never picks fast-vs-deep — the module runs a seconds-long
# pass and either puts real rows on the sheet now or escalates to a Brain Worker that INHERITS that same
# sheet, so the operator watches one box from first finding to final report. Two rounds of the same defect
# were paid on the way: a page that prices itself (`AggregateOffer`, a `lowPrice` with no `price`) is a
# COLLECTION, not a candidate — five category pages had been delivered as cars — and a fact stated NEXT TO an
# imperative that does not mention it gets dropped, so a turn denied three cars it had by name and price and
# invented a stall at 37s. The fork now goes inside the imperative, in both places (2.44, 2.45).
#
# V2-557 brings the operator's cloud FILES: a connector (Drive/OneDrive) behind an agnostic facade and a
# generic explorer widget that does not know who it is talking to — a third provider is a client module and a
# registry row. Its real design point is the permission SCOPE: a narrow one answers 200 with an empty list,
# which is indistinguishable from an empty folder, so the facade returns a reason and the card prints it.
#
# And the architecture ratchet went red the day V2-556 existed, because the feature landed on three files
# sitting exactly at their ceilings. Closed by EXTRACTION, never by raising one: the router's tool CATALOG is
# pure data (964 -> 326 lines), the voice provider's deterministic widget-intent readers moved out
# (3495 -> 3327), and probe shed two helpers to the modules that own them.
#
# Previous (3.17): THE IMAGE, AND WHAT IT WAS MISSING. Three things that all shipped without a single red
# light. V2-553 the update channel — a build NUMBER a person can compare and a bar that offers a reload
# only when the FRONTEND changed. V2-554 `config/models.default.json` was being dropped from the cloud
# image by `.dockerignore`, and it did not crash the boot: the error was swallowed by the try/except
# around the «Colmena» block, so four routers silently did not mount and the smoke went green over it.
# And `widgets/instances.py` used `_re` with no `import re as _re` — valid syntax, green suite (the
# working tree had the import, the tagged commit did not), three fail-soft callers, and three shipped
# behaviours quietly gone. All three are now guarded: what git tracks inside a COPY must reach the
# image (7.16), and no module may use a name it lacks at import time (7.30).
#
# Previous: DELIVERY + REACH. Two blocks, both closed the same night.
#
#   DELIVERY — V2-475 the guarantees now speak the operator's language (they were mute in English and spoke
#   Spanish into English replies), V2-478 the backstop's gate is no longer LENGTH but whether the turn NAMES
#   what the sheet holds, V2-479 twelve rows travel instead of five, V2-480 the worker's door into the
#   scheduler normalizes like the other two, V2-481 a cold start no longer shows raw i18n keys.
#
#   REACH — V2-486 the «ask the mesh first» step reached only the BROWSER prompt, and a hotel that is SEARCHED
#   (rather than booked) is routed to the generic worker, which never named the bridge: the network was built,
#   verified live, and consulted zero times in 399 worker reports. V2-487 an agent answering 400 with the
#   field it needs HAS answered — that was flattened into «the network did not reply», which sends a Chromium
#   at Booking with the answer one field away; measured live, ten real New York hotels in 0.4 s. V2-488 the
#   research composer asked a model that CANNOT stop reasoning to stop reasoning, and a 400 gives no relay
#   tier, so every directed search silently degraded to a blind one. V2-489 the round now says whether the
#   worker asked the network at all. V2-490 a critical health limit is repeated LAST and phrased as a check on
#   what is about to be said — measurement still pending, and its initiative says so.
# INIT DATA. What a brand-new account Machine actually starts with, and what it silently did not.
#
# V2-562 — a cloud Volume mounts EMPTY, and `workspace.root()` only ever answered WHERE a path lives, never
# whether it EXISTS. On a self-host clone git ships `config/`, `credentials/` and `i18n/`, so no writer ever
# needed a mkdir; `/data` held only `memory/` and `widgets/` — the two
# writers that happen to makedirs — and the other three were simply absent. Every write into them raised
# inside code that treats persistence as best-effort, so it was caught, logged at WARNING and stepped over:
# the visible symptom was the language onboarding running again on EVERY cold boot, because `settings.json`
# could never be written. `SUBDIRS` is now the single declaration of that tree, `ensure()` runs before the
# app import, and a guard reads the real call sites so a new persistent root cannot silently reopen the hole.
#
# And the other half of the same class: a work session is usually born LAZILY, from whatever thread emits the
# first event, and only the EXPLICIT door announced itself. So the central activity registry only ever
# received `event="end"` — and closing a record nothing opened updates nothing, so no session was ever recorded.
#
VERSION = "3.45"

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE: dict = {}
_STARTED_MS = round(time.time() * 1000)


#: The commit an image was BUILT from (V2-837 G1). A container has no `.git`, so the build passes the commit in
#: (`docker build --build-arg ZAELAR_COMMIT=$(git rev-parse --short HEAD)`, kept as an ENV by the Dockerfile). A
#: self-host clone does not set it and keeps reading its own repository below.
COMMIT_ENV = "ZAELAR_COMMIT"


def sha() -> str:
    """Short SHA of the code being executed (cached): the commit baked into the image, else the repository's HEAD,
    else 'nogit'. Without the first, every container said `bNN+nogit` and a rebuild of the same build number was
    indistinguishable from the original."""
    if "sha" not in _CACHE:
        baked = "".join(ch for ch in os.getenv(COMMIT_ENV, "").strip()[:12] if ch.isalnum())
        if baked:
            _CACHE["sha"] = baked
            return baked
        try:
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_HERE,
                               capture_output=True, text=True, timeout=2)
            _CACHE["sha"] = (r.stdout or "").strip() or "nogit"
        except Exception:
            _CACHE["sha"] = "nogit"
    return _CACHE["sha"]


def build() -> int:
    """The build number that is RUNNING (`update/BUILD`, the one a user is shown). 0 when unreadable.

    V2-807 T-15: the stamp used to be `VERSION` — a constant bumped by hand that lagged dozens of releases
    behind, so every event of an up-to-date deployment said an old version. The build file is the one
    version that ships with every release (the release gate refuses a tag that did not move it)."""
    import update               # `update.build()` never raises: an unreadable file is 0 there
    return int(update.build() or 0)


def label() -> str:
    """The version part of the stamp: 'b69' from the running build, `VERSION` only when no build is known."""
    b = build()
    return f"b{b}" if b > 0 else VERSION


def short() -> str:
    """Compact label for sealing EVERY observability event: 'b69+a1b2c3d'. Cheap (constant at runtime)."""
    if "short" not in _CACHE:
        _CACHE["short"] = f"{label()}+{sha()}"
    return _CACHE["short"]


def instance() -> dict:
    """WHICH process ran an event (V2-837 G3), as the compact `inst` block every event carries: the host it runs
    on, its pid and the second it booted (two processes of one account, or the old and the new image, are told
    apart by these), plus a region and an image reference when the deployment provides them in the environment
    (`ZAELAR_REGION`, `ZAELAR_IMAGE`). Read ONCE and cached: the stamp is on every event, so it costs a dict read."""
    if _CACHE.get("inst_pid") != os.getpid():         # a forked child is ANOTHER process: re-read, never inherit
        import socket
        try:
            host = socket.gethostname().split(".")[0][:32]
        except Exception:  # noqa: BLE001 — an unnamed host is still an instance
            host = ""
        out = {"host": host, "pid": os.getpid(), "boot": _STARTED_MS // 1000}
        for key, env in (("region", "ZAELAR_REGION"), ("image", "ZAELAR_IMAGE")):
            v = os.getenv(env, "").strip()[:48]
            if v:
                out[key] = v
        _CACHE["inst"] = {k: v for k, v in out.items() if v not in ("", None)}
        _CACHE["inst_pid"] = os.getpid()
    return _CACHE["inst"]


def started_ms() -> int:
    """Epoch ms when THIS process started (to distinguish instances/restarts in observability)."""
    return _STARTED_MS


def info() -> dict:
    """Details for /api/status and the frontend."""
    return {"version": VERSION, "build": build(), "sha": sha(), "short": short(), "started_ms": _STARTED_MS,
            "instance": instance(),
            "uptime_s": round((time.time() * 1000 - _STARTED_MS) / 1000)}


_COMPONENTS: dict = {}


def _tool_version(cmd: list[str]) -> str:
    """The first version-looking token a tool prints for `--version`; "unknown" when the tool is missing or hung."""
    import re
    import subprocess
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):     # a missing or hung tool is reported, never raised
        return "unknown"
    m = re.search(r"\d+\.\d+(?:\.\d+)?", out or "")
    return m.group(0) if m else ""


def components() -> dict:
    """The versions of what this process RUNS — the engine build and the tools it drives: the `claude` CLI the brain
    workers use, Node, Playwright (its Chromium), and the image the host booted, when the host names one
    (`FLY_IMAGE_REF`). Read once per process: none of them changes without a restart. Values only, never paths."""
    if not _COMPONENTS:
        from importlib.metadata import PackageNotFoundError, version as _pkg
        try:
            playwright = _pkg("playwright")
        except PackageNotFoundError:                     # an image without it says so: unknown
            playwright = ""
        _COMPONENTS.update({"engine": VERSION, "build": build(), "commit": short(),
                            "claude_code": _tool_version(["claude", "--version"]),
                            "node": _tool_version(["node", "--version"]), "playwright": playwright,
                            "image": (os.getenv("FLY_IMAGE_REF") or "").strip()})
    return dict(_COMPONENTS)
