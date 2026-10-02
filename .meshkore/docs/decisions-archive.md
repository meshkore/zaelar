

## Moved on 2026-10-02 (V2-778 F3-30)

- **A config save is judged by what it LEAVES, and the suite stops writing the operator's routing (V2-673,
  2026-09-11)**: found on his LIVE engine while verifying something else — `config/v2.json` held
  `{"fast": {"provider": "aimlapi"}}` and nothing else, so the EFFECTIVE config was the broker as TITULAR of
  the voice brain (which the model table forbids outright) over a `model` and a `base_url` that were still
  DeepSeek's: one vendor's name printed over another's traffic, the V2-657 defect arriving by a new road.
  **Two faults, and the second is the one that matters.** (1) `config_api._model_mismatch` exists to stop
  exactly this and compared `patch["provider"]` against `patch["model"]` — a patch carrying ONLY a provider
  has no model IN IT to compare, and a partial write is the NORMAL shape of a config edit, so the guard was
  blind to the common case rather than to an exotic one. It reads the RESULT of the patch now, and also
  refuses a provider whose `base_url` was left behind. (2) The writer was
  `tests/infrastructure/unit/core/test_config_api_cloud_gate.py`, which POSTs a real save through the router
  and isolated NOTHING: every run of node 8.2 silently re-routed his brain, and had done since it was
  written — visible only because the new guard started refusing the incoherent result. Fixing that one file
  is not the fix: this is the THIRD time this class has been paid («a test never touches live artifacts»,
  «my suite reset its LIVE engine»), and each time the remedy was one file remembering. `config/v2.json` now
  moves to a temp path for the whole session in the ROOT `conftest.py`, beside `settings.json` and
  `widgets.store.DATA_DIR` which were already there — the routing store was simply the one this invariant
  had never reached — with its row in `test_suite_isolation`. Node **8.8**; four disarms, mutations
  asserted, all red. ⚠️ **A rule every test has to remember is not a rule**, and an unisolated test does not
  fail: it leaves something behind.
