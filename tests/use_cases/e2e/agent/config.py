"""Configuration for the use-case tester. Deliberately thin: credentials, provider endpoints and the JUDGE
model are already solved by the voice tester (tests/voice/e2e/agent/config.py + llm.py) and reused as-is —
duplicating key-loading/client code here would just be a second place for it to drift. The one thing this
suite genuinely needs different is the DRIVE model: these scenarios are open-ended negotiations (invent a
plausible city, notice when the conversation drifted, decide when the goal is done), not the fixed-goal
turn-taking voice's flash model is tuned for — so DRIVE defaults to the reasoning-capable tier.
"""
from __future__ import annotations

from tests.voice.e2e.agent import config as voice_config

ZAELAR_URL = voice_config.ZAELAR_URL
AIMLAPI_BASE = voice_config.AIMLAPI_BASE
TESTER_KEY = voice_config.TESTER_KEY
ZAI_KEY = voice_config.ZAI_KEY
ZAI_BASE = voice_config.ZAI_BASE
ZAI_JUDGE_MODEL = voice_config.ZAI_JUDGE_MODEL
JUDGE_MODEL = voice_config.JUDGE_MODEL
JUDGE_PROVIDER = voice_config.JUDGE_PROVIDER


def _env(name: str, default: str = "") -> str:
    import os
    return os.getenv(name, default).strip()


# Path to the sandbox engine's own DB, set by `run._sandbox_batch` once it is up. Empty against the operator's
# live engine — the harness reads a database it created, never theirs.
SANDBOX_DB = ""

# The name the engine under test calls the person by (the lab profile's `operator_name`), set by
# `run._lab_batch`. The DRIVE model needs it to catch the vocative role-flip: the persona never addresses
# itself by name, so a tester line that does was written by the assistant. Empty outside the lab.
PERSONA_NAME = ""

# What the AGENT already knows about this person (`LabProfile.persona_ground()`), set by the same call.
# The DRIVE model needs it for the opposite reason to `PERSONA_NAME`: without it, an agent RESOLVING the
# errand from its seeded memory looks like an agent inventing facts, and the driver argues with it. Empty
# outside the lab, and then the driver simply says nothing about who the person is — same as before.
PERSONA_PROFILE = ""

_CODE_STAMP: dict | None = None


def code_stamp() -> dict:
    """WHICH CODE was measured: the engine's short HEAD sha plus the non-test files that were dirty at boot.

    A round is only comparable to another round if you know what was running in it, and this suite runs the
    WORKING TREE (the sandbox boots `python -m server` from `engine/`), not a checked-out commit. On 2026-08-20
    the fixing agent had to ask "did my 15:54 commit actually run in your 16:26 round, or did you reuse a server
    from before it?" — a question that took reading boot timestamps by hand to answer, and that every future
    round would raise again. Worse, a round measured while somebody is MID-EDIT measures a half-applied change
    and looks exactly like a round measured on a coherent tree.

    `tests/` is excluded from `dirty` on purpose: the harness editing itself does not change the engine under
    test, and counting it would make every round look dirty and the flag mean nothing. Fails soft to an empty
    stamp — not knowing the sha must never cost a measured round.
    """
    global _CODE_STAMP
    if _CODE_STAMP is not None:
        return _CODE_STAMP
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]

    def _git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=str(root), capture_output=True, text=True,
                              timeout=15).stdout.strip()

    try:
        sha = _git("rev-parse", "--short", "HEAD")
        # `l[2:].strip()`, not `l[3:]`: porcelain's two status columns are followed by a variable amount of
        # whitespace, and slicing a fixed 3 ate the first letter of every path ("ests/…"), which quietly broke
        # the `tests/` exclusion — every round would have been reported dirty.
        paths = [l[2:].strip() for l in _git("status", "--porcelain").splitlines()]
        dirty = sorted(p for p in paths if p and not p.startswith("tests/"))
        _CODE_STAMP = {"sha": sha, "n_dirty": len(dirty), "dirty": dirty[:12]}
    except Exception as e:
        _CODE_STAMP = {"sha": "", "n_dirty": 0, "dirty": [], "error": str(e)[:120]}
    return _CODE_STAMP



def current_head() -> str:
    """The engine's short HEAD right now, UNCACHED — `code_stamp()` deliberately memoises and would lie here.

    Exists so a repeated round can notice the tree moved under it. Measured on 2026-08-20: two rounds launched
    as one pair from a shell loop landed on different commits, because the fixing agent (correctly) committed
    between them. Two rounds of different code are not a pair, and a stamp per round only reveals that after
    both are paid for.
    """
    import subprocess
    from pathlib import Path
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=str(Path(__file__).resolve().parents[4]),
                              capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def engine_fingerprint() -> str:
    """WHAT THE ENGINE IS RIGHT NOW, as one string — HEAD plus the CONTENT of every dirty non-test file.

    UNCACHED on purpose, unlike `code_stamp()`: this exists to be called again later and compared with itself,
    so a memoised answer would report "nothing moved" forever.

    It hashes CONTENT, not the mere fact of being dirty, and that is the whole point. The walk's mid-batch
    guard used to reason "the tree is dirty, therefore it moved", which is two different claims welded into
    one — and on 2026-08-24 the wrong half fired: another agent had two files in flight *before* the batch
    booted, so from the second case onward every batch stopped itself after exactly one case and reported the
    engine as having moved when nothing had. Four-case batches became one-case batches for an afternoon.
    A tree that was already dirty and has not changed since is perfectly comparable with itself; a tree whose
    files changed is not, whether or not anything got committed. Comparing fingerprints says exactly that and
    nothing else.

    `tests/` is excluded for the same reason `code_stamp()` excludes it: the harness editing itself does not
    change the engine under test. Fails soft to "" — and a caller must read "" as UNKNOWN, never as "equal",
    which is why the comparison below refuses to conclude anything from an empty pair.
    """
    import hashlib
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]

    def _git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=str(root), capture_output=True, text=True,
                              timeout=20).stdout

    try:
        h = hashlib.sha256()
        # EL ÁRBOL DEL MOTOR, no el sha. Usar `rev-parse HEAD` fue mi propio defecto y es el MISMO que este
        # fichero vino a arreglar: allí «sucio» no era «movido», y aquí «hay un commit nuevo» tampoco lo es.
        # Un commit que solo toca `tests/` deja el motor exactamente igual, y aun así paraba la tanda — la
        # pagué dos veces la misma tarde, una por un commit mío del arnés y otra por uno de un agente. Se
        # hashea la lista de blobs de HEAD sin `tests/`: dos commits distintos con el mismo motor dan la
        # misma huella, que es justo lo que se quiere decir.
        h.update("".join(sorted(l for l in _git("ls-tree", "-r", "HEAD").splitlines()
                                if l and "\ttests/" not in l)).encode())
        paths = sorted(l[2:].strip() for l in _git("status", "--porcelain").splitlines() if l[2:].strip())
        for rel in paths:
            if rel.startswith("tests/"):
                continue
            h.update(b"\x00" + rel.encode())
            f = root / rel
            try:
                h.update(hashlib.sha256(f.read_bytes()).digest() if f.is_file() else b"-")
            except Exception:                    # noqa: BLE001 — unreadable is a state too, and a stable one
                h.update(b"?")
        return h.hexdigest()[:16]
    except Exception:
        return ""


def engine_moved(before: str, now: str) -> bool:
    """Did the engine change between these two fingerprints? UNKNOWN ("" on either side) is NOT movement.

    Deliberately the opposite default from `stale_engine_refusal`'s: there, not knowing means refusing,
    because the failure it guards against (measuring code that no longer exists) is silent and expensive.
    Here the failure mode of a false alarm is a batch that stops itself, and a fingerprint we could not read
    is not evidence of anything. Refusing to answer must not be dressed up as an answer.
    """
    if not before or not now:
        return False
    return before != now


# Reasoning-capable tier, not voice's low-latency flash default — negotiating an open-ended request and
# noticing when it's gone off track needs real reasoning, and this suite runs far less often than every
# voice turn so the extra cost/latency per call is the right trade.
DRIVE_MODEL = _env("USE_CASES_DRIVE_MODEL", "deepseek/deepseek-v4-pro")
# The watchdog (mid-scenario off-track detector) can reuse DRIVE or run cheaper/faster — default same tier.
WATCHDOG_MODEL = _env("USE_CASES_WATCHDOG_MODEL", DRIVE_MODEL)

# ── Provider order (operator norm, 2026-08-19) ────────────────────────────────────────────────────────────
# DeepSeek V4 DIRECT from its own provider is the PRIMARY option; the AIMLAPI broker is the fallback; an
# OpenAI/Anthropic model is the last resort. Measured reasons this order is not arbitrary: direct is ~30%
# cheaper than the same model through the broker, and the broker ACCEPTS `thinking:disabled` while still
# reasoning (TTFT p50 4.24s vs 1.01s) — see the V2-097 entry in CLAUDE.md. The same day the broker also ran
# out of funds mid-loop, which is the other half of why a chain beats a single endpoint.
#
# The model NAME differs per endpoint and that is the trap: the broker namespaces it (`deepseek/deepseek-v4-pro`)
# and the native API does not (`deepseek-v4-pro`). Sending the broker's name to the direct endpoint gets a 400
# listing the accepted names — exactly how the workers' DeepSeek tier shipped broken (`model="sonnet"`), which
# nobody could see because a relay tier only runs once the titular is already down.
DEEPSEEK_BASE = _env("TESTER_DEEPSEEK_BASE", "https://api.deepseek.com")


def deepseek_key() -> str:
    """The direct DeepSeek credential. Store first, env as the power-user fallback (repo convention)."""
    k = _env("DEEPSEEK_API_KEY")
    if k:
        return k
    try:
        from config import credentials as _C
        return (_C.get("DEEPSEEK_API_KEY") or "").strip()
    except Exception:
        return ""


def native_model(model: str) -> str:
    """Broker name → native name (`deepseek/deepseek-v4-pro` → `deepseek-v4-pro`)."""
    return model.split("/", 1)[-1] if model else model


# Último escalón, solo si los DOS caminos de DeepSeek están inalcanzables: GLM por Z.AI. **Ningún modelo de
# OpenAI aquí** (norma del operador, 2026-08-19: «no quiero usar modelos de OpenAI»; la formulación inicial de
# la norma nombraba OpenAI/Anthropic como último recurso y se corrigió el mismo día). No hace falta ninguno: el
# escalón existe para que una corrida desatendida DEGRADE en vez de morir, y Z.AI ya está aquí con su
# credencial. Cuesta independencia —el JUEZ vive en ese proveedor— y por eso la ronda queda SELLADA como no
# comparable; ese coste es real, pero es el mismo que tendría cualquier tercer escalón y no mejora por ser de
# otro vendedor.
LAST_RESORT_MODEL = _env("USE_CASES_LAST_RESORT_MODEL", "")   # vacío = usa el escalón Z.AI, sin modelo propio

RUNS_DIR = voice_config.ZAELAR_ROOT / "tests" / "runs" / "use_cases"

# Loopback default: no ZAELAR_OBS_TOKEN needed when the tester runs on the same machine as the engine.
OBS_TOKEN = _env("ZAELAR_OBS_TOKEN", "")


_MACHINE_STAMP: dict | None = None


def machine_stamp() -> dict:
    """WHAT ELSE the machine was doing: the models resident in the local GPU when the round started.

    A round records which code measured it and, until 2026-08-20, nothing about the machine — so a round run
    while another agent held 39,2 GB in Ollama was indistinguishable in the ledger from a round on an idle box.
    That happened, and it was only caught because the other agent said so: their `scale_eval` was competing for
    the GPU with the sandbox's embeddings, and the engine's local write model was paying a TimeoutError per pill
    before failing over. Honesty about a measurement cannot depend on somebody volunteering that they were busy.

    It RECORDS, it does not judge: the local write titular is legitimately resident, and what matters is that a
    reader comparing two rounds can see whether the box was the same. Fails soft to an empty stamp, and is taken
    once per process — the point is the state at the start of the batch.
    """
    global _MACHINE_STAMP
    if _MACHINE_STAMP is not None:
        return _MACHINE_STAMP
    import subprocess
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10).stdout
        models = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                models.append({"name": parts[0], "size": f"{parts[2]} {parts[3]}"})
        _MACHINE_STAMP = {"gpu_models": models, "n": len(models)}
    except Exception as e:
        _MACHINE_STAMP = {"gpu_models": [], "n": 0, "error": str(e)[:80]}
    return _MACHINE_STAMP
