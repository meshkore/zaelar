# zaelar — changing a model (the mechanism checklist)

**Trigger**: a provider announces a new/renamed model, retires one, or changes pricing, and the engine's
model allocation must follow. This doc is the ENGINE half (mechanism — which files hold model identity and
how to verify a change); anything about a managed deployment's accounts, billing or fleet lives outside this
repo.

**The rule that governs the whole doc: a model id is switched only after it is MEASURED as served — never on
an announcement.** Measured 2026-09-09: DeepSeek announced V4.1 Flash "around September 10"; on the 9th the
API's own `/models` still listed only `deepseek-v4-flash`, `deepseek-v4-pro` and
`deepseek-v4-flash-vision-exp`, and every plausible v4.1 id answered 400. Switching that day would have taken
the voice brain down with a config edit that *looked* routine.

## 0 · Measure availability first

```bash
cd engine && ./.venv/bin/python - <<'EOF'
import httpx
import config.credentials as cred
key = cred.get("DEEPSEEK_API_KEY")           # keys resolve from the credential store BY ENDPOINT
base = "https://api.deepseek.com"
print(httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20).text)
r = httpx.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
               json={"model": "<candidate-id>", "messages": [{"role": "user", "content": "reply: pong"}],
                     "max_tokens": 8}, timeout=40)
print(r.status_code, r.text[:200])
EOF
```

Both checks must pass: the id in `/models` AND a real 200 completion. A broker (if any is authorized) is
measured separately — broker ids differ from the provider's, and a broker `/models` list can 403 behind
bot-protection while completions work (or the reverse).

## 1 · Where model identity lives (the complete list)

| File | What it holds | Notes |
|---|---|---|
| `config/models.default.json` | **THE canonical table** (V2-500): one row per service (voice_brain, brief_composer, memory_writer, memory_rem, workers, embeddings…) with provider/model/base_url/key_env and the WHY | The only place a default model id is data. Keys are never here. |
| `config/v2.json` (gitignored, per install) | Local overrides written by the ⚙ UI | ⚠️ Check it does not pin a stale provider: found 2026-09-09 pinning `fast.provider=aimlapi` (retired, wallet empty) over the table's DeepSeek-direct titular — the override wins silently. |
| `config/model_benchmarks.py` | The measured WHY behind each choice | Update the affected entries or mark them stale with a date; a bench that names a retired model as "current" misleads the next reader. |
| `config/profiles.py` | Wizard profiles (first-run defaults) | Grep for the old id. |
| `.env` comments | Power-user fallbacks (`FAST_*`) | Deliberately unset; do not add. |

`grep -rn "<old-id>" config/ nucleo/ voice/ --include="*.py" --include="*.json"` is the completeness check —
prompt/docs mentions are cosmetic, config hits are load-bearing.

## 2 · Apply and verify locally

1. Edit `config/models.default.json` (and clean any stale `config/v2.json` override).
2. Restart the engine (never with a live voice session).
3. Probe the REAL lane, not just the config:
   `curl -X POST 127.0.0.1:43917/api/flash/say -d '{"text":"contesta solo: pong","ingest":false}'` — the
   response's `spec` field names the provider/model that actually served the turn.
4. If the memory writer changed: run one `tests run memory --case memory::group::1.4::v4 --no-open`.
5. Pricing changed too? A managed deployment meters energy per model — that table is not in this repo, but
   the change is not DONE until whoever operates one has updated their rates.

## 3 · Reaching a managed fleet

The image ships `config/models.default.json`, so a release (tag → pipeline) carries the change to NEW
machines. **An existing machine keeps its old image until recycled** — cutting a release updates nobody who
is already running (the V2-553 lesson: their old number is *correct*, they run the old engine). Recycle (or
wait for natural recycle) and verify from inside the account, not from the config.

Also verify the target environment actually HOLDS the credential the new row's `key_env` names — a row
pointing at an endpoint whose key is absent fails only at the first real call.

## Known traps (each one paid)

- **Announced ≠ served** (2026-09-09, above).
- **A local override outlives the canon** (`config/v2.json` pisa la tabla — 2026-09-09).
- **A stale doc claims a key does not exist**: `model_benchmarks.py` said "no DEEPSEEK_API_KEY in any store"
  while the credential store held one — trust `config.credentials.get()`, not prose.
- **A reasoner eats `max_tokens` and returns a truncated 200 with no error**; **"reads images" per the
  broker ≠ reads images**; **an untested failover turns a provider outage into a total outage** (allocation
  doc's three traps — re-check all three when the MODEL changes, not just the id).
- **Provider bot-protection poisons probes**: bare `urllib` got Cloudflare 1010 where the engine's own
  client passed — probe with `httpx` + a browser UA, or through the engine itself.
