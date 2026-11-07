# Long-haul memory run (V2-858)

Years of a generated life on one isolated, time-travelled DB — the evidence that the memory holds up for months
and years, not only for a session.

```bash
./.venv/bin/python -m tests.memory.e2e.longhaul.runner --days 1095 --out /tmp/longhaul.json   # three years
./.venv/bin/python -m tests.memory.e2e.longhaul.runner --days 365 --scale 0.3                # one year, light
```

- `life.py` generates, for a seed, what one operator says day by day: ~12 conversation lines, ~8 passing
  remarks with a TTL, one durable fact about a newly named person or place, a request every other day, and the
  life events that change a singular fact (home every 160 days, job every 330, car every 280, diet every 400). The
  language moves from Spanish to English half-way, as it did on the live install.
- `runner.py` replays it with daily light sleep and weekly REM (deterministic synthesis hook; the concept-fold
  grouping is a stub that knows the generator's own label pairs — the stand-in for the model call). No network.
- Every checkpoint and the end measure: found@12 of named facts asked back by name (by age bucket), slot truth and
  `as_of` truth, the allergy said on day 9, expired rows still valid, superseded shells still indexed, concept hubs,
  query p50/p95, rows/valid/DB size, SQLite and FTS integrity. The exit code is the gates' verdict.
- `tests/memory/integration/test_a_long_life_keeps_its_memory.py` runs one year at 0.3 volume in the suite, with a
  disarm that re-opens the defect the first run found (REM semantic dedup on an uncalibrated backend).
