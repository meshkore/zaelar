"""Keeps the two lab agents up, on THEIR port, with THEIR memory — and wipes one on request.

The rest of this suite boots a throwaway engine per run and tears it down at the end, which is right for
an unattended measurement and useless for watching: by the time the operator opens the URL the port is
gone. These agents are the opposite — they outlive the command that started them, they answer on a port
that never changes, and the only thing that empties their memory is being asked to.

THE PORT IS FIXED, AND A BUSY PORT IS AN ERROR HERE. `preferred_port()` slides to an ephemeral one when
its first choice is taken, which is correct for a batch that must not fail over a leftover process and
wrong for a surface the operator has bookmarked: an agent that quietly moves is an agent you cannot find.
So a taken port is either OUR agent already up (say so, change nothing) or something else (say WHAT, and
stop) — never a silent relocation.

VOICE IS A PARAMETER, NOT A GUESS. Booted quiet (the default) there is no LiveKit worker at all, so there
is no microphone to leave open and no room to join: the agent is driven entirely by text while the
operator watches. Booted with voice, the engine runs its normal pipeline under its OWN room prefix so its
worker cannot pick up a job meant for the operator's real engine. What does NOT change either way is the
agent itself — widgets, workers, background, observability all run in both, because "the mic is off" must
never mean "the agent is half alive".

WHAT RESET DOES AND DOES NOT TOUCH. It deletes the database and the widget data of THIS agent and then
re-seeds its profile — a real fresh install with a known identity. It does not touch the operator's
engine, the other agent, or the credentials (shared on purpose: an isolated DATABASE is the point, a
crippled engine that cannot call a model is not).
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from tests.platform.sandbox_engine import ENGINE, SandboxEngine, spawn_engine, stop_engine
from tests.use_cases.e2e.agent.run import seed_provider_chain
from tests.use_cases.lab.profiles import LabProfile

LAB_ROOT = ENGINE / "tests" / "runs" / "use_cases" / "lab"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def workspace_of(profile: LabProfile) -> Path:
    return LAB_ROOT / profile.key


def _meta_path(profile: LabProfile) -> Path:
    return workspace_of(profile) / "lab.json"


def _log_path(profile: LabProfile) -> Path:
    return workspace_of(profile) / "logs" / "engine.log"


@dataclass
class LabState:
    profile: LabProfile
    running: bool
    pid: int | None = None
    voice: bool = False
    started_at: float = 0.0
    answering: bool = False        # the port answers /api/status
    foreign: bool = False          # something answers on our port and it is NOT ours
    chain: str = ""                # the provider ladder this agent was seeded with

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.profile.port}"


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


def _get(url: str, timeout: float = 2.0) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return None


def status(profile: LabProfile) -> LabState:
    meta = {}
    mp = _meta_path(profile)
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    pid = meta.get("pid")
    st = LabState(profile=profile, running=_alive(pid), pid=pid,
                  voice=bool(meta.get("voice")), started_at=float(meta.get("started_at") or 0.0),
                  chain=str(meta.get("chain") or ""))
    st.answering = _get(f"{st.base_url}/api/status") is not None
    # Something on our port that we did not start. Reported, never worked around: the operator opened
    # this URL expecting THIS agent, and answering them with someone else's engine is worse than an error.
    st.foreign = st.answering and not st.running
    return st


# ── profile seeding ──────────────────────────────────────────────────────────────────────────────────
# Written straight into the database in a subprocess, BEFORE the engine boots. A subprocess because
# `memory/db.py` and friends resolve their paths AT IMPORT TIME from the workspace env vars — the same
# reason `sandbox_engine` spawns instead of monkeypatching. See the module docstring of `profiles.py`
# for why this does not go through the probe channel like a scenario's `memory_seed` does.
_SEED_SRC = r'''
import json, sys
from memory import api as memapi

payload = json.loads(sys.argv[1])
memapi.set_state(payload["state"])
for slot, text in payload["pills"]:
    memapi.write_now(text, level="long", kind="fact", slot=slot, pinned=True,
                     importance=0.9, weight=0.9, meta={"source": "lab-profile"})
print(json.dumps({"state": len(payload["state"]), "pills": len(payload["pills"])}))
'''

# The voice PLUMBING the lab copies from the operator's real install, and nothing else. Same argument as
# the provider ladder: which STT and TTS actually have credentials on this machine is infrastructure, and
# an agent booted on the engine's stock `remote` profile would try a provider the operator does not pay
# for and come up mute — a voice that never speaks is indistinguishable from a broken agent. Their
# PERSONAL knobs are not copied, and `stt_language` is deliberately overridden per profile below: the
# whole point of two agents is that one of them is not Spanish.
_VOICE_PLUMBING = ("stt_provider", "tts_provider", "zaelar_profile", "config_profile", "attention_mode")


def _seed_settings(profile: LabProfile) -> None:
    """Write `config/settings.json` so the agent opens READY instead of on the first-run wizard.

    Two things, both measured rather than assumed. (1) `wizard_done` — a fresh workspace has no settings
    file, so `server/wizard_api._first_run()` is true and the operator's bookmark opens on «Elige un
    perfil» instead of on their agent. (2) `stt_language` — leaving it out means the language is decided
    by whatever the first sentence happens to be (`i18n/init/detect`), and that same code resolves the
    LOCALE of `nucleo/flash/site_catalog.py`: an agent that guesses wrong sends a Spanish errand to
    opentable.com. A lab agent's language is part of who it is, so it is written down, not detected.

    `assistant_voice` is deliberately NOT copied: `config/settings.apply()` picks the voice native to the
    language when the language is set without one, and a Spanish voice pinned on the US agent is exactly
    the cross the engine's own invariant exists to prevent.
    """
    real = ENGINE / "config" / "settings.json"
    base: dict = {}
    if real.exists():
        try:
            src = json.loads(real.read_text(encoding="utf-8")) or {}
            base = {k: src[k] for k in _VOICE_PLUMBING if src.get(k)}
        except Exception:
            base = {}
    dst = workspace_of(profile) / "config"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "settings.json").write_text(
        json.dumps({**base, "stt_language": profile.language, "wizard_done": True},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def seed_profile(profile: LabProfile) -> dict:
    ws = workspace_of(profile)
    (ws / "memory" / "_data").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "ZAELAR_WORKSPACE": str(ws),
        "ZAELAR_DB": str(ws / "memory" / "_data" / "sandbox.db"),
        "ZAELAR_LOG_DIR": str(ws / "logs"),
        "ZAELAR_LANGUAGE": profile.language,
        "MESHKORE_AUTORECONNECT": "0",
    })
    _seed_settings(profile)
    payload = json.dumps({"state": profile.state, "pills": [list(p) for p in profile.pills]})
    out = subprocess.run([sys.executable, "-c", _SEED_SRC, payload], cwd=str(ENGINE), env=env,
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(f"no pude sembrar el perfil {profile.key}:\n{out.stderr[-2000:]}")
    try:
        return json.loads((out.stdout or "{}").strip().splitlines()[-1])
    except Exception:
        return {}


#: The `sys_kv` keys that survive a wipe. A provider cooldown is a fact about the OUTSIDE WORLD — «this
#: endpoint has no quota left until Monday» — not something this agent learned about its operator, so wiping
#: it is wiping the wrong thing.
_KEEP_KV = ("worker_provider_cooldown", "cluster_provider_cooldown")


def _read_kv(ws: pathlib.Path, names) -> dict:
    """Read those keys straight from the sandbox DB, BEFORE it is deleted. Best-effort by design: on a first
    boot there is no database to read and that is the normal case, not an error."""
    db = ws / "memory" / "_data" / "sandbox.db"
    if not db.exists():
        return {}
    out = {}
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        try:
            for n in names:
                row = con.execute("SELECT value FROM sys_kv WHERE key = ?", (n,)).fetchone()
                if row and row[0]:
                    out[n] = row[0]
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return {}
    return out


def _restore_kv(ws: pathlib.Path, saved: dict) -> None:
    """Put them back after the seed. Runs BEFORE the engine boots, so the chain reads them on its first pick
    instead of rediscovering a dead tier with a real request."""
    if not saved:
        return
    db = ws / "memory" / "_data" / "sandbox.db"
    if not db.exists():
        return
    try:
        import sqlite3
        con = sqlite3.connect(str(db), timeout=5.0)
        try:
            for k, v in saved.items():
                con.execute("INSERT INTO sys_kv (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, v))
            con.commit()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        pass


def wipe(profile: LabProfile) -> dict:
    """Empty this agent's memory and widget data. The workspace directory itself stays (the operator may
    have the log open, and the path is in the terminal scrollback of every run).

    Returns the `sys_kv` entries worth carrying over — see `_KEEP_KV`. Measured on the round of 2026-08-24
    15:16, `search-buy-bicycle__es`: the round is 150 s long and the FIRST 67 of them produced nothing,
    because `--fresh` had wiped the cooldown store and the first worker went straight at `z.ai`, which has
    had no weekly quota since the day before (`sin cuota hasta el 25 Aug 01:39`). It died in half a second,
    the relay took over, and the browsing that the case actually measures got 83 s instead of 150. **21 % of
    every round spent rediscovering a fact we already knew**, once per case, all day.

    In PRODUCTION this does not happen: `sys_kv` persists, so the cooldown is discovered once and held for
    hours. It is an artefact of measuring against a brand-new install — which is why the fix belongs here and
    not in the engine.
    """
    ws = workspace_of(profile)
    saved = _read_kv(ws, _KEEP_KV)
    for sub in ("memory", "widgets", "config"):
        shutil.rmtree(ws / sub, ignore_errors=True)
    return saved


# ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────
def env_for(profile: LabProfile, *, voice: bool) -> dict:
    """The engine env that makes this agent THIS agent.

    ⚠️ VOICE IS NOT AN EXTRA HERE — IT IS WHAT MAKES THE SCREEN WATCHABLE. Measured 2026-08-21 by
    rendering the shell in a real Chromium: with `ZAELAR_ENGINE=off` the boot veil NEVER lifts, not at
    5s, not at 70s. The reason is not the missing microphone — it is that `server/livekit_api.py` is what
    SWAPS `services/session.js` for `services/session-lk.js`, and that router only mounts on
    `ZAELAR_ENGINE=livekit`. With the engine off the browser loads the LEGACY Pipecat client, which calls
    `/api/ice-servers`, `/api/offer` and `/api/hangup` — three routes that no longer exist (404, 404, 404)
    — and that path has none of the boot-unblock safety `session-lk.js` grew. The operator opens their
    bookmark and gets a permanent splash reading `boot.encendiendo`.

    So a quiet agent is a HEADLESS agent: fine for a batch nobody watches, useless for the one thing this
    lab exists for. Hence `voice=True` is the default and `--quiet` is the opt-out that says so.
    """
    # MEMORY_RERANK: pinned OFF in the ENV, not in the agent's `config/v2.json`, and the distinction is the
    # whole point. It WAS pinned in that file on 2026-08-22; by 13:08 the next day the ES agent had rewritten
    # its own config and the `memory` block came back EMPTY — a running engine rewrites that file and does not
    # preserve keys it considers defaults. With the key gone the lab falls back to the CODE default
    # (`config/v2.py`: "local"), which downloads a 1.1 GB cross-encoder ONNX blob and — because the probe path
    # still builds its prompt synchronously on the event loop (`nucleo/flash/probe.py:251`) — takes the WHOLE
    # engine down with it: every endpoint times out, and the round dies reporting `INFRA: timed out` with no
    # hint that memory was the cause. `config.v2.get()` reads stored > env > default, so an env var is the one
    # place the agent cannot erase from under us. It also matches what the operator's own engine runs, so the
    # lab is not measuring a memory path the product does not use.
    env = {"ZAELAR_LANGUAGE": profile.language, "MEMORY_RERANK": "off"}
    if voice:
        # The engine's own default. Its room prefix is deliberately NOT derived from "zaelar": the voice
        # worker admits any room whose name STARTS WITH its prefix (`voice/engine/pipeline/agent.py`), so
        # a prefix like "zaelar-lab-es" would still be accepted by the operator's real engine — their
        # worker would race ours for our own room. "lab-es" shares no prefix with "zaelar" in either
        # direction, so each worker only ever answers its own.
        env["ZAELAR_ENGINE"] = "livekit"
        env["ZAELAR_ROOM"] = f"lab-{profile.key}"
    return env


def up(profile: LabProfile, *, voice: bool = True, fresh: bool = False,
      boot_timeout: float = 180.0) -> tuple[SandboxEngine | None, LabState]:
    st = status(profile)
    if st.running:
        return None, st
    if st.foreign:
        return None, st

    ws = workspace_of(profile)
    ws.mkdir(parents=True, exist_ok=True)
    seeded = fresh or not (ws / "memory" / "_data" / "sandbox.db").exists()
    carried = wipe(profile) if fresh else {}
    if seeded:
        seed_profile(profile)
    _restore_kv(ws, carried)
    # EVERY boot, not only a fresh one: the chain is infrastructure, and it is the operator's live config
    # that decides it. Seeding it once at creation would freeze whatever ladder existed that day.
    chain = seed_provider_chain(ws)

    eng = spawn_engine(workspace=ws, port=profile.port, log_path=_log_path(profile),
                       extra_env=env_for(profile, voice=voice), boot_timeout=boot_timeout)
    _meta_path(profile).write_text(json.dumps({
        "pid": eng.process.pid, "port": profile.port, "voice": voice,
        "started_at": time.time(), "workspace": str(ws), "seeded": seeded, "chain": chain,
    }, indent=2), encoding="utf-8")
    return eng, status(profile)


def down(profile: LabProfile, *, clean_widgets: bool = True) -> bool:
    """Stop the agent. Returns whether there was one to stop."""
    st = status(profile)
    mp = _meta_path(profile)
    if not st.running:
        mp.unlink(missing_ok=True)
        return False
    # Reattached from another process, so there is no Popen to wait on — the same terminate/kill ladder
    # by hand, then the widget cleanup `stop_engine` would have done.
    pid = st.pid
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.25)
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(1.0)
    if clean_widgets:
        shim = SandboxEngine(base_url=f"http://127.0.0.1:{profile.port}", workspace=workspace_of(profile),
                             log_path=_log_path(profile), process=None)
        stop_engine(shim)
    mp.unlink(missing_ok=True)
    return True


def reset(profile: LabProfile, *, voice: bool | None = None,
          boot_timeout: float = 180.0) -> tuple[SandboxEngine | None, LabState]:
    """Wipe this agent's memory and bring it back on the SAME port, freshly seeded.

    `voice` defaults to whatever it was running as: a reset is about the memory, and silently changing
    how the operator was watching it is not part of that.
    """
    was = status(profile)
    keep_voice = was.voice if voice is None else voice
    down(profile)
    return up(profile, voice=keep_voice, fresh=True, boot_timeout=boot_timeout)
