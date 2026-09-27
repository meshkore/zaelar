# The decision bank — `tests/brain/`

**What it is.** A fixed corpus of real turns, each one frozen at the point where the brain has to DECIDE: the
words the model would have said and the tools it would have called, the verdicts Jev would have returned,
the cards on screen, the memory the turn needs. The engine gets all of that and answers one question — *what
did you decide?* — in a grammar of one line. The judge compares the line to the one the case expects. It is
V2-776 scope A1, the net under which the brain is compacted (scope B): a guard leaves only when its cases are
green through the new decision step, and **a new failure of the brain is written as a CASE here, never as a
guard** (operator's rule, 2026-09-27).

**Where the turns come from.** The session files (`.meshkore/logs/sessions/*.jsonl`, the operator's real
phrases with what the engine did), the demo scripts (`TMP/demo/` at the workspace root, with the v1-v5 pass
results), and the decision entries of `.meshkore/docs/decisions.md` (V2-753 … V2-756, each phrase quoted with
its verdict). Every case says where it came from in `source`.

## Run

```sh
export ZAELAR_WORKSPACE=$(mktemp -d)                       # the suite isolates itself too; belt and braces
./.venv/bin/python -m pytest -q tests/brain/unit           # one test per case + the disarm proofs
./.venv/bin/python -m tests.brain.runner                   # the table and the four numbers (A2's control run)
./.venv/bin/python -m tests.brain.runner --case demo-v7-stop-it-and-close-the-video
```

The runner's exit code is about REGRESSIONS: non-zero when a case that was green is red, or when an `open`
case has turned green without anyone removing its mark.

## The case

One JSON object per case, grouped in `cases/*.json` by origin (`demo-v2.json`, `sessions.json`,
`decisions.json`). Ids are unique across files; `harness.validate` refuses anything outside the schema.

```json
{
  "id": "demo-v7-stop-it-and-close-the-video",
  "lang": "en",
  "phrase": "Stop it and close the video widget.",
  "source": "TMP/demo/02-demo-script-v2.txt V7 · 03-results v5: closed and the model REOPENED it",
  "screen": {"open": ["youtube"]},
  "memory": {"agenda": [{"title": "Dentist", "day": "+1", "start": "09:30", "end": "10:00"}]},
  "model": {"say": "Done.", "tools": [{"name": "show_widget", "args": {"widget_id": "youtube"}}]},
  "brief": {"screen_action": ["youtube:close", 0.97]},
  "expect": "close youtube",
  "also": [],
  "forbid": ["show", "worker"],
  "open": "V2-776 B1: …"
}
```

| Field | Meaning |
|---|---|
| `lang` | `es` or `en`. Sets the install's language, so the action map seeds the right pack. |
| `screen.open` | The cards on screen (`memory.state().open_widgets` in the isolated DB). |
| `memory` | Fixtures the turn needs: `agenda` rows (`day` is relative, `+1` = tomorrow, so nothing goes stale) and `state` fields. Never the operator's DB. |
| `model` | The RECORDED model: `say` (its words, tags included) and `tools` (its calls, in order). **Absent = the case belongs to a deterministic lane** (action map, presence, small talk) and consulting the model at all is a failure. |
| `brief` | Jev's verdicts for this turn, `key → [choice, confidence]`, in the shape `nucleo.jev.read` consumes. Absent = no brief (today's fail-soft path). |
| `expect` | The decision, one line of the grammar below. |
| `also` | Secondary mutations that must ALSO happen (a compound turn's second card). |
| `forbid` | What must NOT happen: `worker` `search` `show` `close` `data-op` `second-card` `model` `ask`. |
| `open` | A defect the bank has named and nobody has fixed: the test runs as a **strict xfail** with this reason, and the runner counts it apart. Remove the mark when it turns green. |

### The grammar of a decision

```
talk · ask · escalate · search · listings · close all · minimize · unfullscreen
show <card> · close <card> · read <card> · data-op <card>:<action> · music <action> · panel:<tab>
```

`talk` is the model's own words and nothing else. `ask` is a question the ENGINE decided to ask (the
`clarify` route), not a question the model happened to write. `data-op` names the card the call LANDED on
after the engine's own resolution, which is the point: a case where the model aimed at the wrong card and
the verdict names the right one expects the right one.

## The harness

`harness.run_case` runs the phrase through `nucleo.flash.probe.run_turn` — the headless channel the use
cases and the agent-headless corpus already drive: the real prompt, the real fast lanes, the real guards and
the real decision seam, `execute=False` so nothing spawns or moves for real — inside `harness.Isolated`:
`ZAELAR_WORKSPACE`, `ZAELAR_DB`, the widget store, the observer's log dir, the language and the Jev switch
all redirected, `FastClient` replaced by the recorded model, `turn_brief.ask_for_turn` by the recorded brief,
everything restored in `finally`. `decision_of` maps the probe's action vocabulary onto the grammar; an
action it does not know comes back verbatim, so a new mechanism shows up as a red case with its own name.

**The voice provider is a parallel implementation of the same turn** (V2-539's standing lesson). The bank
runs on the channel that runs headless today and joins the voice adapter the day B2 hands both channels to
`nucleo/turn/`. Until then a green case says «the shared seam decided right», and the wiring guards in
`tests/agent_headless/unit/actionmap/` keep the channels honest about carrying the same seam. One case
(`v2-567-cierra-los-mensajes-y-ensename-la-agenda`) is open precisely because the probe reports ONE action
and a compound turn needs two.

## The bank measures the product, not itself

`unit/test_the_bank_measures_the_product.py` disarms three rungs and requires the matching case to go red:
the action map off (a lane case consults the model), the close-vs-show guard off (V7 reopens the video),
the brief ignored («Vale, para el vídeo.» becomes `talk`). If one of these stays green the harness is
measuring itself.

## Baseline (2026-09-27, the day the bank was built)

42 cases, ES+EN · **35 green** · 7 open, each naming the scope that owns it:

- **B1 (one decision step with explicit precedence)** — `v2-754-vuelve-al-dashboard-verdict-vs-model`,
  `demo-e2-open-the-most-important-one`, `demo-i3-open-the-second-one-model-picks-the-wrong-card`,
  `demo-r1-tesla-insurance-answered-then-escalated`, `session-3a9a082c-close-the-weekend`. All five are the
  same question asked five ways: when the model's own call and a sure verdict disagree, who wins.
- **B2 (one turn for both channels)** — `v2-567-cierra-los-mensajes-y-ensename-la-agenda`.
- **C2 (source of truth by kind)** — `demo-z1-whats-on-my-plate-tomorrow`.

A case that was green on this date stays green: that is the initiative's third definition-of-done line.
