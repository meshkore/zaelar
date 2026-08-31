"""Re-exports the voice tester's LLM client (tests/voice/e2e/agent/llm.py) — same DeepSeek/AIMLAPI +
GLM/Z.AI clients, same credentials, no reason to duplicate the HTTP/parsing code. This module exists only
so `from . import config, llm` reads the same way across every module in this package.

`call` gets one retry on top of the original: AIMLAPI sits behind Cloudflare and blips intermittently
(documented elsewhere in this codebase) — for an unattended run, one transient network error should not
waste the whole scenario's turns and cost so far. `glm_call`/`parse_json` are unchanged passthroughs.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from . import config
from tests.voice.e2e.agent.llm import call as _call
from tests.voice.e2e.agent.llm import glm_call, parse_json
from tests.voice.e2e.agent.llm import judge_call as _voice_judge_call


def _as_text(content) -> str:
    """Flatten a reply whose `content` came back as a LIST of parts instead of a string.

    Cost a real scenario (`buy-known-product__es`, 2026-08-18): the broker returned OpenAI's structured
    content form — `[{"type": "text", "text": "..."}]` — and `driver.py`'s `.strip()` on it raised
    `'list' object has no attribute 'strip'`, killing the scenario mid-run. Both shapes are legal in that API
    and which one arrives is the provider's choice, not ours, so the caller cannot be the place that knows.
    Non-text parts are dropped rather than stringified: a `str(dict)` of an image part inside the tester's next
    utterance would be worse than saying nothing.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text") or "" for part in content
            if isinstance(part, dict) and (part.get("type") in (None, "text") or "text" in part))
    return "" if content is None else str(content)


# ── DRIVE provider chain (operator rule, 2026-08-19) ──────────────────────────────────────────────────────
# ORDER: DIRECT DeepSeek V4 → AIMLAPI broker → Z.AI/GLM. ZERO OpenAI models (operator rule).
#
# The two tiers exist because of measured facts, not caution: on 2026-08-19 at 02:34 the AIMLAPI account
# returned 403 «You've run out of funds» (verified against the response body, with both the harness key
# AND the engine key), and DRIVE—the one acting as the person—died with it: INFRA with 0 turns, twice
# in a row, without a single measurable case. The primary is direct because it is ~30% cheaper than the same
# model through the broker and because the broker ACCEPTS `thinking:disabled` and reasons the same (TTFT p50 4.24 s vs 1.01 s).
#
# The tier that served is STAMPED in the measurement (`drive_model` → ledger + initiative round). A handoff
# changes the INSTRUMENT: the row is no longer comparable with previous ones, and with Z.AI, DRIVE would
# share a provider with the JUDGE, which exists on another provider precisely to remain independent.
# A SILENT handoff would leave the board advancing with two instruments without knowing which row used which.
# ── LICENSE tier: the Claude Code CLI with the local license ─────────────────────────────────────────────
# It is the tester's LAST tier, and exists for a reason the other two cannot provide: it is a SUBSCRIPTION,
# so it cannot fail because of balance or quota. On 2026-08-21, hours of runs were lost with both paid tiers
# down at once (Z.AI without quota until the 25th, and a network outage that left direct in `Connection error`),
# and a round without a tier is not a product failure: it is an invoice, and the harness records it as INFRA.
# With this tier the run DEGRADES instead of dying.
#
# It comes last rather than first for two reasons, neither related to model quality: it consumes the
# operator's license (2026-08-02 rule: flat rate, never pay per token, and ONLY locally), and it is slower—measured,
# ~7 s for a trivial turn—because it starts a process per call. Like any handoff, it SEALS the round:
# `drive_model()` returns `licencia-claude` and the row is no longer comparable with DeepSeek rows.
#
# This does NOT affect the Brain Workers: the product is measured with the chain the product uses (DeepSeek/GLM,
# which is all that exists in the cloud). This only changes WHO acts as the person and WHO scores—the instrument.
def _claude_licence(messages: list[dict], max_tokens: int = 4000, model: str = "") -> str:
    """One turn through the Claude Code CLI, using the license with which the operator is already logged in.

    Three precautions, all three real traps in this repo, not hypothetical caution:

    1. **The environment is cleaned.** `ANTHROPIC_BASE_URL`/`_AUTH_TOKEN`/`_API_KEY` are exactly the variables with which
       the engine uses to redirect this same CLI to Z.AI or DeepSeek. Inheriting them here would make the
       «Anthropic tier» actually be the tier that just failed—the handoff would be announced in the seal without
       having handed off anything.
    2. **It runs from a NEUTRAL directory.** The CLI loads `CLAUDE.md` from cwd; from `engine/` each
       driver turn would drag in the entire repo context (V2-117 measured that bomb: 167k → 25k tokens).
       Besides being expensive, a driver that has read the engine code stops acting as the PERSON.
    3. **Without MCP and with our system prompt.** `--strict-mcp-config` without `--mcp-config` leaves the process with no
       single MCP server, and `--system-prompt` replaces the code agent's: here we do not want an agent
       that edits files; we want a model that answers one sentence.
    """
    import subprocess
    import tempfile
    sys_parts = [m.get("content") or "" for m in messages if m.get("role") == "system"]
    convo = []
    for m in messages:
        if m.get("role") == "system":
            continue
        who = "ASISTENTE" if m.get("role") == "assistant" else "USUARIO"
        convo.append(f"{who}: {_as_text(m.get('content'))}")
    prompt = "\n\n".join(convo) or "(sin contenido)"
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
    model = model or (os.environ.get("USE_CASES_LICENCE_MODEL") or "").strip() or "sonnet"
    argv = ["claude", "-p", prompt, "--model", model,
            "--output-format", "text", "--strict-mcp-config"]
    if sys_parts:
        argv += ["--system-prompt", "\n\n".join(sys_parts)]
    with tempfile.TemporaryDirectory() as neutral:
        out = subprocess.run(argv, cwd=neutral, env=env, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"licencia-claude rc={out.returncode}: {(out.stderr or out.stdout)[:200]}")
    return out.stdout.strip()


_FUNDS = ("run out of funds", "top up your balance", "insufficient", "403")
_used_drive = ""


def drive_model() -> str:
    """Which tier handled the LAST DRIVE call. `run.py` uses it to seal the round."""
    return _used_drive


def _override() -> str:
    return (os.environ.get("ZAELAR_UC_DRIVE") or "").strip().lower()


def _nonempty(text: str, tier: str) -> str:
    """An EMPTY response is a tier failure, not a response.

    Without this, the chain accepts `""` and the tester tells the agent NOTHING: the scenario degrades and the
    report reads it as the agent having gone silent. An empty turn from the one acting as the person is not measurable.
    """
    if not (text or "").strip():
        raise RuntimeError(f"{tier} devolvió una respuesta VACÍA")
    return text


# The native endpoint REASONS by default and reasoning is charged against `max_tokens`: measured, «Say only OK»
# with `max_tokens=8` it spends all 8 thinking and returns `content=''` with `finish_reason=length`—an EMPTY
# response without any exception. The driver's budget of 200 accommodates it (24–38 reasoning tokens in the
# probes), but a difficult negotiation turn is exactly where reasoning becomes longer, so the failure would
# appear in the most complicated case and be read as the agent not responding. Reasoning is NOT disabled
#—it is what led us to choose this tier for DRIVE—so it gets a separate ceiling, which is free when unused.
_REASONING_RESERVE = 512


def _deepseek_direct(messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
    """Native DeepSeek (OpenAI-compatible). Model name WITHOUT the broker prefix—see `config`."""
    key = config.deepseek_key()
    if not key:
        raise RuntimeError("no DEEPSEEK_API_KEY")
    payload = {"model": config.native_model(model), "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens + _REASONING_RESERVE}
    req = urllib.request.Request(
        config.DEEPSEEK_BASE.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    return _as_text(((data.get("choices") or [{}])[0].get("message") or {}).get("content"))


def call(messages: list[dict], model: str | None = None, temperature: float = 0.0, max_tokens: int = 4000) -> str:
    global _used_drive
    want = _override()
    model = model or config.DRIVE_MODEL

    def _direct() -> str:
        return _deepseek_direct(messages, model, temperature, max_tokens)

    def _broker() -> str:
        return _as_text(_call(messages, model=model, temperature=temperature, max_tokens=max_tokens))

    def _zai() -> str:
        return _as_text(glm_call(messages, max_tokens=max_tokens))

    def _licence() -> str:
        return _claude_licence(messages, max_tokens=max_tokens)

    def _last() -> str:
        # Third tier = Z.AI/GLM, NOT an OpenAI model (see `config.LAST_RESORT_MODEL`). If one day a model is
        # if a model is set there, it goes through the broker; empty—the default—is Z.AI.
        if config.LAST_RESORT_MODEL:
            return _as_text(_call(messages, model=config.LAST_RESORT_MODEL, temperature=temperature,
                                  max_tokens=max_tokens))
        return _zai()

    # Manual hatch: pin ONE tier and do not move from it (to measure a specific arm without a failure
    # handing off behind the scenes and contaminating the comparison).
    forced = {"direct": ("deepseek-directo", _direct), "deepseek": ("deepseek-directo", _direct),
              "aimlapi": ("aimlapi", _broker), "broker": ("aimlapi", _broker),
              "zai": ("zai/glm", _zai), "glm": ("zai/glm", _zai),
              "claude": ("licencia-claude", _licence), "licencia": ("licencia-claude", _licence)}.get(want)
    if forced:
        _used_drive = forced[0]
        return _nonempty(forced[1](), forced[0])   # forcing a tier does not exempt it from providing a response

    chain = [("deepseek-directo", _direct), ("aimlapi", _broker),
             (f"último recurso · {config.LAST_RESORT_MODEL or 'zai/glm'}", _last),
             ("licencia-claude", _licence)]
    errs: list[str] = []
    for i, (name, fn) in enumerate(chain):
        try:
            out = _nonempty(fn(), name)
            _used_drive = name
            return out
        except Exception as e:
            errs.append(f"{name}: {e}")
            # Retry on the SAME tier before falling back: AIMLAPI sits behind Cloudflare and blips, and a blip
            # should not change the measurement instrument for the entire run.
            if not any(x in str(e).lower() for x in _FUNDS):
                time.sleep(2.0)
                try:
                    out = fn()
                    _used_drive = name
                    return out
                except Exception as e2:
                    errs[-1] += f" | reintento: {e2}"
            if i == len(chain) - 1:
                raise RuntimeError("DRIVE sin escalón disponible → " + " ;; ".join(errs))
    raise RuntimeError("DRIVE sin escalón disponible")


def judge_call(messages: list[dict], max_tokens: int = 2000, out: dict | None = None) -> tuple[str, str]:
    """The JUDGE, with the local license at the bottom of the chain.

    Losing the judge means losing the ENTIRE ROUND: the conversation has already been paid for and occurred, and without a verdict it does not
    it enters the scoreboard. The voice harness chain (GLM → direct DeepSeek → broker) already retries transient
    failures; what it does not cover is all three being unavailable at once, which is exactly what happened on
    2026-08-21 (Z.AI without quota until the 25th + a network outage affecting direct).

    It returns the model that scored, as before, because a round judged by another instrument must be distinguishable
    distinguirse en el tablero: la licencia es un modelo distinto y sus notas no son comparables sin decirlo.
    """
    import sys
    try:
        return _voice_judge_call(messages, max_tokens=max_tokens, out=out)
    except Exception as e:
        print(f"[judge] cadena de pago sin escalón ({str(e)[:100]}) → licencia local de Claude Code",
              file=sys.stderr)
    txt = _claude_licence(messages, max_tokens=max_tokens)
    # The local license does NOT say whether it cut off: record «I don't know» instead of leaving the reading from the leg that
    # that just failed. Anyone inspecting this must be able to distinguish «it fit» from «not known to me».
    if out is not None:
        out["finish_reason"], out["cortada"] = "", False
    if not (txt or "").strip():
        raise RuntimeError("licencia-claude devolvió una respuesta VACÍA al JUEZ")
    return (txt, "licencia-claude")


__all__ = ["call", "glm_call", "judge_call", "parse_json", "drive_model"]
