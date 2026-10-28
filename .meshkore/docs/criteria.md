# Criteria — the standing rules of the engine

**What this is.** The rules the engine obeys TODAY, one line each, and nothing else: no history, no incident
narrative, no superseded version. When a rule changes, its line changes here and the old text is gone — the
story of how it changed is the diary's job (`.meshkore/docs/decisions.md`, then `decisions-archive.md`). An
agent that has read this file knows what the engine must do; an agent that wants to know why reads the diary.
The diary is local-only (gitignored): on a clone it does not exist, and this file is the whole public canon.

**How to read a line.** `CRIT-<group><n>` · the rule · `— since <date> · nodes <ids>` where the ids are nodes
of `tests/run_testmap.py` that guard it, and, when it helps, the code seam that implements it. A line marked
`⚠ sin test` ("no test yet") names a rule no node guards yet; it is a debt, not a decoration.

**How to change one.** Edit the line (never append a second line on the same topic), move the date, cite the
node of the test that proves the new behaviour, and write the WHY as a diary entry. The ratchet
(`tests/infrastructure/unit/test_the_criteria_are_one_and_current.py`) keeps every line dated and tested and
the contradictions table empty.

**The base, above all of these:** `.meshkore/context/principles.md` — mechanisms, not rules. A change that
bounds a CONSEQUENCE is a mechanism and stays; one that bounds JUDGEMENT is a rail and goes. Every criterion
below is the first kind, or it names the mechanism that replaced the second.

---

## 1 · What the mouth says (voice)

- **CRIT-V1 · One short line at most.** An order that ran says at most one short line: the model's own, or
  «Done.» / «Here it is.» when the model said nothing. A spoken rule turns the ack off («no me confirmes las
  órdenes») and a retraction restores it. — since 2026-09-29 · nodes 3.22, 2.50, 3.97 · `nucleo/genesis.json`,
  `nucleo/style_policy.py`, the ack backstops in `voice/engine/llm/providers/nucleo.py`.
- **CRIT-V2 · A repaired act is said after the words only when the words DENIED it** (or asked a question: «which…?» gets
  «I went with the likeliest one», «want me to…?» gets «I've gone ahead» — one table, `act_repair.TAILS`); a claim or a promise in any language needs nothing after it. — since 2026-09-29 ·
  nodes 2.89, 2.154, 2.237 · `nucleo/flash/act_repair.after_the_repair`.
- **CRIT-V3 · A «yes» is answered with a START, never with a completion.** The outcome is reported when the work
  settles (`op_receipt`), witnessed against the widget's own view; a pool timeout is not an outcome; an op that
  could not start or whose dispatch raised is said as not done, never left behind «Done.». — since 2026-09-30 ·
  nodes 2.17, 3.35, 2.201.
- **CRIT-V4 · Fillers are «smart».** A wait cover sounds only on a turn that thinks (a question, real work), never
  on a short order; a cover describes motion and never ends the turn; a promise to look with nothing behind it is
  withdrawn. — since 2026-09-17 · nodes 2.50, 2.164, 3.58 · `voice/engine/core/filler_audio.py`,
  `nucleo/flash/answer_guards.py`.
- **CRIT-V5 · A claim is not a fact.** A delivery claimed over an empty sheet becomes a follow-up; «still on it»
  is said only about live work on THIS request; a result already spoken is not news on the next turn. — since
  2026-09-19 · nodes 3.35, 2.102, 2.86.
- **CRIT-V6 · The agent's language, always.** Every spoken line is in the agent's language; an internal system
  note never sets the reply language; a stage direction the model writes is not read aloud. — since 2026-09-26 ·
  nodes 2.129, 2.123, 2.152, 2.160.
- **CRIT-V7 · The chat wall is the conversation.** A voice line is written when the mouth STARTED it
  (`bot_speech speaking`), never when generated; its identity is the turn's trace, not its position; a held
  fragment is glued to the next only if the next continues it. — since 2026-09-22 · nodes 4.210 ·
  `nucleo/flash/continuation.py`.
- **CRIT-V8 · The assistant's own name changes by a verdict, never by a regex, and fails CLOSED** (absent or
  unsure → no rename). The brief's `identity_change` decides, sure at 0.85, and the new name is the model's declared
  `set_style_directive.name` — nothing is read from his words; a rename takes one model turn
  (`nucleo/turn/identity.py`, refactor2710-07). — since 2026-09-22 · nodes 2.56.
- **CRIT-V9 · A phase pack rides only a FREE turn.** A question, an order or a long sentence gets its answer and
  no introduction block that turn (`nucleo/context_packs/free_turn.py`, `context_packs.compose(turn_text)`).
  — since 2026-10-11 · nodes 2.474.
- **CRIT-V10 · The microphone is only parked over an ear that has HEARD.** In a wake-word mode the browser's
  recogniser may close the paid tap only after it has returned a result; its `onstart` proves nothing, and
  runs that keep ending empty within seconds give the licence back (`frontend/app/services/wakeword.js`).
  — since 2026-10-23 · nodes 4.208.
- **CRIT-V11 · A failed turn's fallback line follows what the turn IS.** A reply that the model could not produce
  says the i18n `say_again`; the first turn (the kickoff greeting) answers nothing he said and says the i18n
  `kickoff_fallback` instead, or nothing — never «say that again» (`turn_failure._fallback_line`).
  — since 2026-10-24 · nodes 2.770.
- **CRIT-V12 · An owed act ends in one of three states, never in a log line.** Whether the turn OWED an act is the
  brief's verdict (`reply.owes_an_act`: an order or a sure escalation at its confidence), never our reply's words
  (refactor2710-03). A turn that owed one and fired nothing that ran gets ONE second pass on a card — the verdict's,
  else the card of the model's own call a guard discarded, else (decision model silent) the card his last turn acted
  on or the one open; the pass makes the call, or declares `cannot_do`, or judges nothing is owed. A repaired call a
  guard swallows is not done; when nothing ran and nothing was routed, he hears that it was not done (the pass's
  sentence or the i18n `promise_not_kept`), said by the mouth (`nucleo/turn/reply.py`, verdict `cannot` or `unmet`)
  through `nucleo/turn/promise_kept.py`. Nothing is owed when the brief does not say an act was owed, nor when a
  claimed state is one an op of this request left on screen and nothing refused. A sure `escalate` with nothing run,
  no model call and no pass that ran or refused starts its errand through the turn's escalation instead of a «not
  done» (`promise_kept.deferred_errand`). — since 2026-10-24 · nodes 2.790, 2.794, 2.796.
- **CRIT-V15 · Inside the attention window a line is still judged, and only an addressed line keeps it open.** In
  `always` the window admits without waiting (deafness inside a conversation is the worse failure), and the line is
  judged beside the turn by the same judge, which answers two questions — addressed? a clear request?
  (`attention.open_line`). A line judged not addressed renews nothing: its admission is given back and neither the
  reply's chunks nor its falling edge re-anchor (an armed delivery still does). A worker, or an act with a consent
  class or from `sensitive` up, started from a line that was not a clear request asks first — `consent.decide`
  (`licensed`, step 0; `his_yes` and `allow` do not clear it) and the one worker door
  (`dispatch_confirm.unlicensed_gate`, an `offered` question in his language; his yes licenses the line). A wake
  word, a typed line or a judge that failed license nothing new and keep today's path. — since 2026-10-26 ·
  nodes 8.26 · `voice/attention.py`, `nucleo/consent.py`, `nucleo/dispatch/confirm.py`.
- **CRIT-V16 · The STT boosts a place only where one is expected.** Keyterms bias every word of a session, so the
  national list of mis-heard towns is never sent on its own; only his own places (memory, behind
  `ZAELAR_STT_BOOST_FROM_MEMORY`, off by default) are boosted, spelled by that list. Re-measure
  (`gazetteer.expected_terms`) before boosting anything wider. — since 2026-10-26 · nodes 3.13 ·
  `voice/engine/speech/stt/gazetteer.py`.
- **CRIT-V13 · «I didn't catch what you said before the pause» only over words that were really lost.** A
  discarded fragment whose words still travel, in order, in the text the turn runs with (or in the buffer still
  held) is not a loss: `Accumulator.offer` returns no `dropped`, so no timeline line and no spoken notice. A
  fragment that reaches no turn is still reported and rescued. — since 2026-10-24 · nodes 2.795.
- **CRIT-V17 · A typed line is complete by construction.** Each channel says at its own door when what it carries is
  finished (`nucleo/input`); the phrase accumulator (`nucleo/input/stt.py`) runs on speech only, so a line he finished
  with Enter is one turn with every sentence — nothing peeled, held or dropped, no gap notice in a text chat. — since
  2026-10-27 · nodes 2.818 · `nucleo/input/__init__.py::of_turn`, `voice/engine/llm/providers/turn_fragment.py`.
- **CRIT-V14 · The microphone is conditioned per platform, and the agent-side filter is one setting that fails
  open.** A phone or tablet opens its mic with the full profile (echo cancellation + noise suppression + gain
  control), a desktop Mac with «isolate» (echo cancellation only, so macOS Voice Isolation works without the
  browser's suppression on top); `voiceIsolation` is asked only where `getSupportedConstraints()` reports it
  (`frontend/app/services/mic-profile.js`). Agent-side voice isolation is `ZAELAR_VOICE_ISOLATION` = off | nc | bvc,
  default bvc (operator, 2026-10-26: on by default on desktop and phone, `off` is the flag): it attaches `livekit-plugins-noise-cancellation` to the room's audio input only on a LiveKit Cloud
  project; elsewhere (a self-hosted livekit-server refuses it) or with the plugin missing the session runs as with
  off and one warning says why (`voice/engine/pipeline/voice_isolation.py`). A self-hosted server skips it with one info line.
  `tests/voice/bench/voice_isolation_bench.py` measures WER with and without it; a result that raises WER on clean
  speech turns the default back to off. — since 2026-10-26 · nodes 3.138, 4.299.

## 2 · Consent — act or ask

- **CRIT-C1 · One consent rule.** A missing datum → ask for the DATUM; a doubt between two → ask which; a radius
  → ask; otherwise act. Genesis asks at `critical`; a spoken rule moves it in both channels, understood ONCE when
  written by one structured call (`rules/shape.py`: «pregúntame siempre antes» → `ask_at` sensitive, «no me pidas
  confirmación para los correos» → a gate at that channel's scope); every field is validated against declared data,
  removal is by id, and with no answer nothing is guessed into a gate. A question only clarifies WHAT he wants,
  never asks permission: when the verdict is sure of the order and its action at `consent.intent_act_at` (genesis
  0.7), the engine acts even if the model asked — below it the question stands. — since 2026-10-26 · nodes 4.188,
  4.185, 2.174, 2.811, 2.431, 2.728, 2.729 · `nucleo/consent.py`, `rules/shape.py`, `nucleo/flash/undecided.py`.
- **CRIT-C2 · A «yes» answers ONE proposal** and spends only that proposal's authority; an order that starts with
  «ok» is not a yes to a different pending action; every pending confirmation can be answered in words. A line
  that follows a question of OURS is his reply whether the verdict reads it as `answer` or `order` — the label only
  excludes (his own question, a comment, a complaint), it never licenses; one definition
  (`prior_line.answers_our_question`), read by the fragment guard and the stop. — since 2026-10-28 · nodes 2.29,
  2.156, 2.125, 3.73, 2.763 · `nucleo/flash/prior_line.py`, `nucleo/flash/escalation_guard.py`.
- **CRIT-C3 · The agenda goes DIRECT.** Deleting or adding an item never asks; a bounded trash and `restore` put
  the row back in its slot (an appointment: `restore_meeting`, also for one skipped day or a series cut short); sweeps (clear or delete a list, clear all or a range) still ask. A row's content is
  never an order («add a task: buy bread» buys nothing) — the danger gate is repaired by SUBTRACTING, never by
  adding a pattern. — since 2026-09-21 · nodes 4.206, 4.188, 2.67, 2.238 · `widgets/agenda/data.py`, `nucleo/danger.py`.
- **CRIT-C4 · Building or rewriting a card of his asks first**, at the one door a worker is lit
  (`dispatch._run_session`, `kind == code`); the cluster dev-worker is exempt. — since 2026-09-23 · nodes 2.76.
- **CRIT-C4c · Every appointment he writes carries its notice**: a timed one ~2 h before, an all-day one at 09:00 that
  day; an asked `remind` wins; items synced from Google stay silent. — since 2026-10-10 · nodes 2.250.
- **CRIT-C4d · A notice is a ROW and reaches him exactly once.** Every reminder, finished job and pending approval goes
  through `nucleo/pulse/notices.py`: voice when he is at a screen, Web Push to his devices when not, `owed` (retried, then
  shown on the next screen) when nothing could take it — the same `dedupe_key` never twice. A DEFAULT appointment
  notice that Google Calendar alarms itself is `covered` (read at fire time); an asked one is always ours. ⏻ silences
  the voice, never the push. — since 2026-10-25 · nodes 2.800, 2.801, 2.802, 4.271 · `nucleo/pulse/notices.py`,
  `nucleo/pulse/webpush.py`, `nucleo/pulse/wake.py`.
- **CRIT-C4b · A worker never deletes a card.** Deleting is a confirmed act (`pending_confirm`, the UI's Yes/No);
  the first verb of a request names its act, so a build that mentions deleting its own entries builds. — since
  2026-10-09 · nodes 2.246.
- **CRIT-C5 · An act that LEAVES runs only when the verdict backs it and its recipient is certain.** A send, a
  forward or a meeting invitation (`external.send`) runs when the verdict does not name another action; unbacked, it
  is DROPPED with a note to the model — never turned into a question, because the next «ok» would answer it. Its
  recipient is never a doubt: one he did not name (this turn or his last 15 min) is asked «¿se lo mando a X?», a
  spelling-only near contact is named back, never written to, and the engine never turns a draft into a send to
  somebody he did not name. When it was asked, the yes is HIS words (a plain yes, or the judge's YES), never the
  model's `confirmed=true` over a sentence about something else. — since 2026-09-29 ·
  nodes 2.106, 2.168, 2.730, 2.740 · `nucleo/flash/leave_gate.py`, `widgets/mensajeria/outbound.py`,
  `widgets/confirm.py::backs_a_yes`.
- **CRIT-C6 · An action does not manufacture permission for its own side effects**; the confirm gate asks
  SOMEONE, and its «yes» returns to the click it stopped. — since 2026-09-18 · nodes 4.21, 2.29.
- **CRIT-C7 · A transactional op never enters the task list** (deleting an item, sending a message); the list is
  for work that takes time and that he may come back to. — since 2026-09-21 · nodes 3.82.
- **CRIT-C9 · A send held for his word is a ROW, and his order over it is the yes — asked once, in one place.** A
  message he wants to review first is a draft of the mail card (a NEW one to a person: `draft` with `contact`); a
  send for later is a scheduled row (`send_draft` with `at`/`in_minutes`, shown on the card, `cancel_send` until it
  leaves). A widget whose action delivers a row he has SEEN declares `held_row`; with the verdict sure of that act at
  `consent.intent_act_at`, the one consent rule runs it with `his_yes` and the leave gate takes the row's recipient
  as his (`nucleo/flash/held_send.py`) — his standing «ask» rule, a missing fact, a doubt and the radius still stop.
  A channel refines a send's class (`messaging.send_new@email`), so his rule for one channel governs that channel
  only. A pending confirmation lives in the conversation (voice or the chat's Yes/No resolve the same row), never
  also on the card; the confirmed act owes its declared end state (`send_draft.done_when`: a sent row for that
  recipient), so «confirmed» and «done» are judged apart. — since 2026-10-26 · nodes 2.806, 2.807 · `widgets/mensajeria/held.py`, `nucleo/consent.decide`.
- **CRIT-C10 · Every act that reaches the real world reads ONE door, and his rules override its defaults.** A widget's
  act through `frontend.action_verdict`; a cluster message, an errand's reply and a worker's click through
  `consent.decide_act(class, channel)` — `messaging.send_new@<channel>`, `web.commit`, `payment.authorize`, defaults
  in genesis (each as it was before). A spoken rule that names a channel by the connector catalog's own vocabulary
  moves that channel only («no me pidas confirmación para mandar correos» → `@email: allow`); one that names none
  moves `ask_at`. An act that leaves and runs FAST by its manifest still stops on his `ask`/`never`. An errand
  replies only inside its mandate (`may: message`, its channels) — outside it the reply is a held draft row, inside it
  his channel rule still stops it. A held cluster send is one pending row; voice, chat and the Clusters tab resolve it
  through the same reader. A page that cannot be read keeps asking; the agenda's invitation is decided once, at the
  door. — since 2026-10-26 · nodes 2.808, 2.806 · `nucleo/consent.py::decide_act`, `nucleo/errands/mandate.py`,
  `connectors/meshkore/send_gate.py`, `widgets/navegador/click_gate.py::consent_verdict`.
- **CRIT-C8 · A search is never gated as a charge.** A negated act («do not buy») and a first-person wish beside
  a lookup order («I want to buy X, give me the link») are subtracted before the money verbs are read — a
  negation only subtracts the act it governs, inside its own clause («don't forget to pay», «no compres el barato,
  compra este» still park); the pay click is where money stops. The core guard reads whole words only. — since
  2026-09-30 · nodes 2.181, 2.200, 3.29 ·
  `nucleo/danger.py`, `nucleo/protected_core.py`.

## 3 · The canvas — whose card, what runs

- **CRIT-K1 · A verb table is not a router.** A grammar may PROPOSE (free, instant); the decision model chooses
  among DECLARED options; a backstop never contradicts a verdict already paid — the promise branches of both
  channels ask `escalation_guard.word_tables` before a word table escalates (2026-10-26). — since 2026-09-22 · nodes
  2.71, 2.72, 3.59, 3.120 · `nucleo/jev.py`, `nucleo/flash/build_decision.py`, `nucleo/flash/escalation_guard.py`.
- **CRIT-K2 · The verdict COMPLETES the model, never contradicts it.** A valid, resolvable model call runs (a
  discrepancy is recorded ⚖️); an empty turn or an unresolved call is filled by the verdict's declared action on
  the open card; unsure, closed card or Jev off → the model's path bit for bit. Two exceptions: a verdict VIEW at
  ≥ 0.95 on the card in front beats a model VIEW on ANOTHER card; a player's one-shot `play` on a turn the brief
  reads as a SURE commission (`escalate` ≥ `player_control.COMMISSION_SURE` on an order) is that errand, not his
  description played as a title (`player_control.commissioned`, both channels). — since 2026-10-24 · nodes 2.73,
  2.121, 2.244, 2.797 · `nucleo/flash/direct_action.complete`, `nucleo/flash/verdict_card.py`.
- **CRIT-K3 · The verdict's action lands on the LIVE card**, never a bare phantom; with several cards of one type
  «close» goes to the one his last turn touched; «it» / «that» is the card his last turn acted on. — since
  2026-09-29 · nodes 2.167, 2.169, 2.85 · `nucleo/flash/show_target.py`, `nucleo/canvas_focus.py`.
- **CRIT-K4 · An order NAMES its target.** A show never falls on the card that happens to be open; what is
  unknown is the REFERENCE, never the card; the show backstop uses the verdict's card before a contextual guess.
  — since 2026-09-29 · nodes 4.160, 2.170.
- **CRIT-K5 · A canvas mutation needs the operator's words.** The room is not the operator: ambient speech
  reaches neither the chat nor the canvas; a system note never names a card to close and never vetoes a show. —
  since 2026-09-09 · nodes 4.145, 2.134, 3.99.
- **CRIT-K5b · Content he NAMES in the turn licenses its own load.** Context-bleed is a PREVIOUS call replayed, so
  its query is absent from his words; a `play_video` whose query terms he said in this turn runs (any language,
  no verb table), minus the player's declared vocabulary and minus what the player already holds (praise naming
  what plays reloads nothing). A close the canvas route refuses is neither logged as done nor counted as an act. —
  since 2026-10-24 · nodes 2.771 · `nucleo/flash/canvas_license.names_what_to_play`, `show_target.close_dispatch`.
- **CRIT-K6 · The canvas that counts is the tab holding the voice session**; a fullscreen card covers everything
  and always has an exit; leaving fullscreen is its own, idempotent order. — since 2026-09-24 · nodes 2.91, 2.78,
  2.79.
- **CRIT-K7 · A descriptor is written under the cut and measured against its NEIGHBOURS** (`MAX_DESC_CHARS`); a
  homograph is closed by naming it; a number he said is a READING, not an invention, and a question asked twice
  keeps its answer. — since 2026-09-23 · nodes 2.74, 4.204.
- **CRIT-K8 · Closing a card is a TOOL, like opening one**; «close the calendar and the messages» closes both; an
  op inside a card runs and the card he NAMED closes after it. — since 2026-09-24 · nodes 2.88, 2.127, 2.126.
- **CRIT-K8b · A close that names no card closes the OTHERS, never nothing, and never in silence.** The card in use
  (the newest card a data-op ran on, still open, or one the turn kept) is spared unless his words name it; when
  sparing would leave nothing to close, everything closes; every bulk close leaves one short line in his language —
  what it closed, what is still on screen, cards by name — spoken by the doors with no model reply (hard interrupt,
  action map). — since 2026-10-26 · nodes 3.133, 3.135 · `nucleo/flash/bulk_close.py`, `nucleo/flash/hard_turn.py`.
- **CRIT-K8c · A verdict vetoes a clear close only when it reads a negation; his answer to OUR question carries its
  licence.** A sure `canvas=neither` refuses a close the grammar saw only beside a sure reading of the turn as neither
  an order nor an answer (the canvas door's `close_ordered`); a turn the brief reads as an `answer` while our
  «which one should I close?» is pending licenses the close (the cards it picks, `close_answer`) and nothing that
  starts a player (`runtime.produce`), and never a negated close. — since 2026-10-26 · nodes 3.136 ·
  `nucleo/acts/canvas.py::close_ordered`, `nucleo/flash/close_answer.py`.
- **CRIT-K9 · A classifier before the model is a PRICE** (~780 ms), paid only where the decision cannot be read
  after; a fixed table may decide alone only where a wrong answer costs nothing — a fail-open default. — since
  2026-09-22 · nodes 3.58.
- **CRIT-K10 · A card named only to be LEFT ALONE is never the target.** With several open cards declaring the
  same control, his sentence decides before any verdict: the card it names as the target wins, a card inside a
  keep / don't-touch / negation clause is excluded (`nucleo/acts/named_target.py`); a «which card?» the engine
  asks parks the control, is phrased with the cards' display names, and his next answer naming one of them runs
  it; two players settle on a verdict only at `PLAYER_SURE` (0.9). — since 2026-10-11 · nodes 2.470, 2.471, 2.472.
- **CRIT-K10b · A card is named by what it shows, never by its id.** Every «which card?» names an instance by its
  content (title, what it was looking for, its first row), else by its kind, and two that still collide by their
  place among the open cards (`instances_nth`); the last door before the question (`widgets/instances._no_ids`)
  replaces any label carrying an open card's id, whatever the widget's `card_face` returned. — since 2026-10-26 ·
  nodes 3.137 · `widgets/instances.py`, `widgets/results/sheet_names.py`.
- **CRIT-K11 · A close order answered with a player's pause is the card's CLOSE** («cierra la música» →
  `musica:pause` closes the card, both channels through `card_close.data_close`, and the receipt says closed).
  — since 2026-10-11 · nodes 2.473, 2.430.
- **CRIT-K12 · A redo is not a drag.** A re-emitted op is context-bleed only when the previous one LANDED and the
  turn did not ask for it again: the card reporting afterwards that it did not happen (`late_report.falsified_since`),
  his turn naming that card as its target (never one named to be left alone), or the redo verdict on that card make
  it a redo that runs — with or without a verdict, no phrase table (`nucleo/flash/redo_license.py`). — since
  2026-10-24 · nodes 2.793.
- **CRIT-K14 · The late catalogue question is asked once per sentence.** Every repair of a turn reads the same
  answer (`card_commission.late_catalogue`); a failed or timed-out trip is never remembered as an answer, and an
  unsure one stays under each caller's own floor. — since 2026-10-24 · nodes 2.798.
- **CRIT-K13 · What an order changes ends where he can see or hear it, or the card says why not.** An answer that
  fills a card's list brings that face forward; a video ordered to be watched wants sound unless he muted it, and
  what the player really lets be heard is the player's own report (`audio_blocked`: the hint stays, the brain reads
  it, an agent order is told); what it shows carries the fact he needs to check it (a video's publication date).
  — since 2026-10-24 · nodes 2.791, 2.792 · `widgets/youtube/sound.py`, `widgets/youtube/library._fill_list`.
- **CRIT-K15 · A step asked again is another step, and a skip says what sounds now.** An action a card declares `"repeatable": true` (next, previous, a volume notch, a relative seek) is never eaten as the previous turn's op dragged along; a repeated WRITE still is. A list is handed to a provider whose skip lives in its context (`plays_lists_as_context`, Spotify) as ONE play, and a skip reports the song the player shows afterwards or says that nothing changed. — since 2026-10-24 · nodes 2.799, 5.63 · `nucleo/flash/data_ops.is_step_op`, `connectors/music.play_list`.
- **CRIT-K16 · A player's capability is a declared op of its card, and a provider's limit is said, not faked.** List management, the queue, play modes, mute and the catalogue are ops of the music card reached through the generic widget door; what the card fires about itself (`played`, `ended`, `enrich_art`) is `"internal": true` and never offered to the model. The catalogue asks the connected account first and the free metadata next (played by its words), never coming back emptier than a play; a queue the provider cannot edit is shown read-only and an edit answers `unsupported`. The card's effects say the REAL state: the meter animates only while the player reports sounding, a paused current song wears a still marker. — since 2026-10-24 · nodes 4.264, 4.265, 5.64 · `widgets/musica/player.py`, `widgets/musica/browse.py`, `connectors/music/catalog.py`.
- **CRIT-K17 · One agent, many screens: what a request does to a screen happens on the screen that asked.** Every event carries `origin_dev` (the voice holder for a spoken turn, the typing screen for a typed one, the commissioning screen for an errand's cards, by trace within a turn — `voice/screens.py`); `event-scope.js` is the one table of what is origin-scoped (a card opening, full screen, the panel) and everything else reaches every screen; another screen gets a chip, never the card. Voice in and out live on one screen and the loser stands down on the hand-over event; any screen types (`POST /api/chat`); every widget declares `"screens"` — `shared` (a reflection, open anywhere) or `single` (takes the device's sound or picture: lives on one screen, and asking for it from another screen moves it), with `runtime.output` ⇒ `single` (`widgets/screen_policy.py`); the brain sees the canvas of the current turn's screen. — since 2026-10-25 · nodes 4.266, 4.267, 4.268, 4.269, 4.270 · a widget is done only after the two-screen test (`.meshkore/docs/ops/zaelar-two-screen-test.md`).
- **CRIT-K17b · Music plays where he listens, and «playing» is read back.** A start is placed on the screen that asked: a device of a provider that `plays_elsewhere` is used only when it sits with that kind of screen (`device_near`, the provider's own device types), otherwise the asking screen's page player (`plays_in_page`); an unknown screen keeps the old choice. A start on a device elsewhere is true only once the player reports that device sounding that song (`confirm` — the reply names the device); a silent or refusing device falls back to the page and a refused chosen device is never swapped for the first one listed; the same words again while it sounds are not re-sent. The page player reports what the browser lets be heard (`player_audio` → `audio_blocked`): the card shows the tap, the digest says it, an agent start is told against. — since 2026-10-26 · nodes 5.65, 4.297 · `connectors/music/__init__.py`, `connectors/music/placement.py`, `connectors/spotify/provider.py`, `widgets/musica/sound.py`.
- **CRIT-K16b · The brain sees what a card shows, and controls reach the player that sounds.** No rows is not «empty»: a card whose published interior (`prompt_digest`) says something is not reported EMPTY (`refs.items_line`). The music card publishes its live state — song, which player and where, playing or paused, volume, a silent browser. Pause, volume, next, the queue and the reading go to the provider the last start was recorded on (`music.sounding_provider`), the first connected one only when nothing was started. — since 2026-10-26 · nodes 4.298 · `widgets/refs.py`, `widgets/musica/data.py`, `connectors/music/__init__.py`.
- **CRIT-K18 · Each screen shows its own state, the same on the desktop eye, the desktop bar and the phone.** One derived state per screen (`store.screenState()`): stopped → the grey ⏻; holder → the grey orb; speaking → the ORANGE orb, only on the screen that holds the voice (`services/orb-colour.js`, replacing «orange = listening»); voice elsewhere → the grey orb with the slashed mic, never orange, and a tap on it brings the voice here — it never stops the agent. The ⏻ means power only. Icons are lilac when on/open and grey when off/closed; the mic and the speaker only when really live on this screen. Switching the agent on goes through ONE door for both shells, the server first (`services/power.js`). — since 2026-10-25 · nodes 4.147, 4.266.
- **CRIT-K19 · ⚙ Settings is one left menu, everything reads from the left, and «Back» goes where he came from.** Settings (its sections listed under it), Appearance, Connectors and Widgets are the groups of ONE side menu, no top tabs; on a phone the menu is the first page and a section opens with «← Menu». Content is never centred: a row is a label column then a control column, both from the left, and a form's actions sit on the left, primary first. A connector page is built from the same pieces on every step and ends on «Back to <whoever opened it>» · «Close»; a card that opens a connector names itself (`openConnector` → `from`), and its «Back» closes the panel instead of landing on the list. A message about how the deployment is configured never reaches the end user. — since 2026-10-25 · nodes 2.219, 2.803 · `frontend/app/components/ConfigPanel.js`, `frontend/app/components/ConnectorWizard.js`.
- **CRIT-K20 · A result card is laid out by the space it really has; length is never the data's fault.** The results sheet stores a field whole up to a storage cap and never budgets characters for the layout; every card is a container, its text clamped to its lines for its real width with the whole text one click away («Ver todo») and in the hover title; the grid reflows by width; every card of a photo layout keeps a fixed-aspect plate (a monogram for a missing or dead photo); the list shows the declared `meta` chips (else the first facts) and the record keeps everything else; the presentation audit reports data quality (shape, links, `columns`), never a length. Tokens come from the design system, the card one rung above its sheet. — since 2026-10-26 · nodes 4.274, 4.10, 2.685 · `widgets/results/widget.js`, `widgets/presentation.py`.
- **CRIT-K21 · A card says where he is, and the messaging card's mail section is a mail client.** A house left of the card's title is lit with the title on its home and dims inside a section, whose name follows as the current crumb; every screen below has a way back one level. The messaging home holds only what is addressed to him — a held draft or a scheduled send lives in its own channel (email's in Drafts). The mail section is ONE left rail and a list — no folder row under the header, which names only where he is: Compose, the Inbox split into the categories the PROVIDER returns (only when the server advertises them, `X-GM-EXT-1`; never invented), each with the provider's own unread figure (the Inbox badge is its first category's, as in Gmail), then every folder the server declares (RFC 6154 roles, never read from a folder's name); the rail folds to icons, then to a drawer, by the card's own width. Pages come a page at a time, read-only; a draft is the WHOLE card and its only content — recipient, subject, text and Send · Save · Discard, found by state for «abre el borrador» — STATE that survives the card mounting after the order and an order that only names the section; on any list (and in a channel's strip) a held draft is one line that opens it, never its body or a Send button; «back» returns to the list it was opened from; each button is ONE order whose outcome the screen reads back from the state. — since 2026-10-26 · nodes 4.275, 4.278, 4.279 · `widgets/mensajeria/mailbox.py`, `widgets/mensajeria/mail_actions.py`, `connectors/email/folders.py`, `connectors/email/categories.py`.
- **CRIT-K22 · The mail card mirrors the server's membership, not only its flags.** Of the messages on screen (the pending Inbox items, the first page of a folder he entered in the last 15 min), each poll tick asks the folder which it still holds: what it no longer holds (archived, deleted or moved in his own client) leaves the card, and a folder whose size changed has its first page read again, so mail moved back reappears. One login per folder per tick, no connection held open (no IMAP IDLE); an unanswered check removes nothing. — since 2026-10-26 · nodes 4.277 · `connectors/email/membership.py`, `connectors/email/service.py`, `widgets/mensajeria/mailbox.py`.
- **CRIT-K23 · His mail categories are criteria he reorganises by voice, rows of the rules table — the default is the provider's own sorting.** With no row the card lists the provider's categories as they are. «Los de Amazon que vayan a Principal» / «no me enseñes Social» is the turn model's verdict over what is declared (the categories the provider returned, a sender he named) → `mail_sort` → a `pref` row at `widget:mensajeria` (`mail_route:<sender>` = category, `mail_hide:<category>`) in his words; code composes routes into the provider's own query, so the list and its count follow, and hides an entry from the rail. Listed and removable by id in the card, by voice and in ⚙ Settings → Rules; a category the provider never returned and a sender that is not an address, a domain or a word are refused; nothing moves in his real mailbox. — since 2026-10-26 · nodes 4.280 · `widgets/mensajeria/mail_rules.py`, `widgets/mensajeria/mailbox.py`, `connectors/email/categories.py`.
- **CRIT-K35 · A repaint never moves him.** Every repaint of a card goes through one door that keeps where he is: a scroller that declares itself (`data-scroll-key`) keeps its bottom if he was on it, else the same row at the same offset; a chat opens on its latest message (`data-open="bottom"`); the focused field (`data-keep`) gets its focus and caret back, its value being its own buffer's job. — since 2026-10-27 · nodes 4.305 · `widgets/mensajeria/widget.js` (`_captureWhere`/`_restoreWhere`).
- **CRIT-K36 · A send from his own hand is his order, and it is answered.** The card's Send is ONE order with the box's text naming its conversation (never «the most recent draft»); what cannot leave is refused before it is queued; every connector's reply drain echoes the order's `ref` on success and publishes `msg.send_failed` with the reason on failure, the owner settles the card's outbox row, and the box keeps his text until the row says it left — refused, failed or unconfirmed, the text stays and the reason is shown. — since 2026-10-27 · nodes 4.304 · `widgets/mensajeria/card_send.py`, `widgets/mensajeria/sent.py`.
- **CRIT-K37 · A conversation is named by his contacts first, through one resolver.** `directory.namer`: the contact holding the conversation, then the contact whose phone (a phone JID only) or address its id carries — unique, or nobody — then the platform's own display name, then the bare id; applied once to the whole messaging view and to the voice lookup. His own downloaded media plays in the thread like what he receives (`store.with_media`, both doors). — since 2026-10-27 · nodes 4.306, 4.307 · `widgets/directory.py`, `widgets/mensajeria/names.py`, `connectors/messaging/store.py`.
- **CRIT-K38 · A header that stays put is not in the scroller.** A card's own fixed band (title, sub-header, tab bar) is a `flex:none` child of a root that fills the card, and ONE region below it scrolls, starting at the band's bottom edge — never `position:sticky` against the card's padded scroller, whose inset is a window the content scrolls through. That region declares itself (`data-hb-scroller`) and both hosts' `ctx.top()`/`ctx.scroll()` move it (else the card's own scroller); a data repaint keeps its offset. — since 2026-10-27 · nodes 4.309 · `widgets/results/widget.js`, `frontend/app/widgets/desktop.js` (`_scrollerOf`), `frontend/mobile/app/shell/Deck.js` (`scrollerOf`).
- **CRIT-K39 · An app's page says only what its manifest declares, on the desk and on the phone alike.** The launcher lists the catalogue the Apps tab reads (System · Custom) and shows the selected app's page, built ONCE (`apps-catalog.js`) for both shells. Desk: the rail's corner icon opens a window; one click shows the page, a double click or «Open» opens the app and closes the window. Phone: an «Apps» entry in the ☰ menu; a tap shows the page (no double click on touch), «Open» opens the app on the deck and closes the menu; every control ≥ 44px. Opening is `hb:open-card`, which both hosts (desktop.js, Deck.js) listen on. The page is `/widgets/<id>/about`: owner, created, licence, what it does (`widgets.<id>.about` in his language, else the manifest `description`) and the live connectors serving its declared `connector_families` (read with `serves()`); a field the manifest does not declare is absent, never a placeholder. — since 2026-10-27 · nodes 4.315, 4.316, 4.317 · `widgets/about.py`, `frontend/app/components/apps-catalog.js`, `AppsWindow.js`, `frontend/mobile/app/shell/AppsPane.js`.
- **CRIT-K24 · A message to someone has ONE body: its held row.** An action that writes free text on a card declares the field (`text_field`); a card that holds outbound messages declares `claims_text` and answers `claim_text(text, title)`. At the one door (the turn's data door and `server_api._dispatch`) a text that is a version of a held draft — most of its content, or a good part of it while naming the draft's own recipient address; overlap measured, no word read for its meaning — is written to that row (`save_draft`), the draft card comes up through the canvas door, and the redirect is on the timeline. A document that only mentions the address stays a document. — since 2026-10-26 · nodes 4.281 · `widgets/text_home.py`, `widgets/mensajeria/held.py`.
- **CRIT-K25 · A held draft is part of the agent's state while it exists, whichever cards are open.** It reaches the prompt from ONE source, its pending-work row (`pending_rows` → `nucleo/pending_work.py`): recipient, subject, a bounded excerpt and the actions that act on it (`open_draft` / `draft` / `send_draft` / `discard_draft`, only those the card declares) with the payload that names it. The card's digest does not repeat it. — since 2026-10-26 · nodes 4.282 · `nucleo/pending_work.py`, `widgets/mensajeria/data.py`.
- **CRIT-K27 · What was sent is read from the record of what left.** A widget's `recent_facts()` lines reach every turn through `nucleo/pending_work.fact_lines`; the mail card's are its sends of the last half hour as the connector sent them (head and tail of the body, so the signature is there) and what is still leaving, marked as not left yet. The timeline records the body a send of this card left with (`widget/sent` on `mensajeria`, from the connector's echo), never what he typed in his own app. — since 2026-10-26 · nodes 4.283 · `widgets/mensajeria/inbox_read.py`, `widgets/mensajeria/sent.py`, `widgets/mensajeria/owner.py`.
- **CRIT-K28 · Reading a card answers from what its screen holds.** With a draft or one mail open on the mail card, its `read_query` returns that object (recipient, subject, body — a stranger's words fenced) and does not search the inbox; with a list on screen the inbox is searched as before. — since 2026-10-26 · nodes 4.284 · `widgets/mensajeria/inbox_read.py`.
- **CRIT-K26 · A capability no card declares is a «not yet», never a worker; a worker never runs the operator's own controls of a card.** The turn brief asks, over the DECLARED actions of the open cards (or the catalogue's cards), whether he asks one of our cards or connectors for something none of them declares; a sure `missing` (≥0.7) makes the errand portal (`escalate_to_slowbrain`) refuse a turn-born errand (`src` voice/probe, same trace): he hears «not yet» in his language and the request becomes a suggestion row on an engine that already reports to the feedback door (a self-hosted engine sends nothing and points at the button). Unsure, absent or another turn's verdict: today's path. An action a widget declares `"worker": false` (its view navigation and settings) is DENIED to a Brain Worker. An inferred or given errand spec never keeps a term that is only the assistant's name. — since 2026-10-26 · nodes 3.121 · `nucleo/flash/capability_gap.py`, `nucleo/flash/escalate.py`, `nucleo/cli/worker_policy.py`, `nucleo/spec.py`.
- **CRIT-K29 · What he does to the running errand is the turn's verdict, not a word table.** While an errand runs the turn brief asks what THIS turn does to it (`stop_errand`, our previous line beside it): `stop`, `replace` (drop it and do this instead), `steer` (go on, but with this correction) or `keep`. A sure `stop` or `replace` lets the model's `stop_worker` run and repairs a turn whose model called nothing (an escalation it started still starts); a sure `replace` is ONE act — the turn carries the errand that takes its place, the stopped goal beside his words (`start_beside_the_stop`), and `turn_after` lets it through beside the stop, never as a refinement of the dying one; a sure `steer` relays his words to the ONE running errand (not one waiting on him) before any rung or repair pass, both channels; a sure `keep` refuses a stop dragged from an earlier turn; with no sure verdict the grammar keeps today's path. Answering a worker still beats killing it in the same turn. — since 2026-10-27 · nodes 3.134, 3.139 · `nucleo/flash/stop_decision.py`, `nucleo/flash/tool_executor_calls.py`, `nucleo/flash/post_stream_settle.py`, `nucleo/flash/post_stream_acts.py`, `nucleo/flash/probe_after.py`.
- **CRIT-K30 · Only the engine changes the canvas, and every change says who made it.** The browser never opens, closes or moves a card from words (interim, spoken or typed); a card opens from an engine `widget show` (verdict, action map, tool). Each host names a cause for every show/close at its call site (`by`), the canvas report carries it, and only a gesture of his hands keeps `user` provenance — client code is `client:<cause>` (unnamed: `client`) on the timeline and to the arbiter, and no screen obeys either back. The observability stamp is the running build (`update/BUILD`). — since 2026-10-26 · nodes 4.115, 2.813 · `frontend/app/services/sse.js`, `voice/canvas_src.py`, `server/canvas_api.py`, `version.py`.
- **CRIT-K31 · A phone shows every card whole: the shell's touch floor, its two exceptions, and the keyboard.** On the phone every control in a card is at least 44px and a text field 16px (below that iOS zooms); a row that directly holds controls wraps rather than push the card sideways — EXCEPT a row that manages its own width (a tab strip `role="tablist"` that scrolls sideways, a thumbnail rail or a title that ellipsizes beside its close, `data-strip`) and a box that directly holds a text field, which is one control: it never wraps and grows with its field. While a field inside a card has focus and the visual viewport is shorter than the screen, the deck covers only the visible part and the dock steps aside. Hover-only affordances do not hold space on a touch screen, and one tap opens what a double-click opens. Each app is checked in the REAL shell on iPhone 14 (WebKit) and Pixel 7 (Chromium) and its screenshots are looked at. — since 2026-10-26 · nodes 4.300, 4.301 · `frontend/mobile/app/styles.css`, `frontend/mobile/app/shell/keyboard.js`, `tests/browser/e2e/mobile/phone_pass.py`.
- **CRIT-K32 · The phone's deck has a HOME, a top bar and one-finger paging.** Page zero is the home: one tile per open app (the app's monogram on its own colour, its live title, ♪ when producing, × to close, the card he came from ringed), the resting state when nothing is open. Every card wears ⌂ · ‹ · name with k/n · › · × as 44px targets; the pips above the dock count the home plus every card, the current one lit. One finger pages anywhere when the swipe is clearly sideways (48px, 2:1) and did not start on something that scrolls or drags sideways on its own (unless from the screen's edge); two or three fingers still page; a finger that commits to going down first is the widget's. The engine's `minimize` lands on the home; the Android back goes home before it leaves. The dock is 64px plus the safe area once, the orb rises above its edge, and a card ends exactly at the dock's top; with the keyboard up the surface holding the field (card or sheet) covers the visible part and the dock is gone. — since 2026-10-26 · nodes 4.19, 4.87, 4.300 · `frontend/mobile/app/shell/Deck.js`, `frontend/mobile/app/styles.css`, `frontend/mobile/app/shell/keyboard.js`.
- **CRIT-K33 · An errand runs behind the screen.** A card action that a repair pass or the catalogue rung runs instead of a worker brings its card up only when its output exists only on screen (`present.mount`), when it is a lens (`data.read`) over a closed card, or when the turn's verdict says `canvas = show`; otherwise it runs and the visibility flag stays where he left it, and the refusal is emitted. A lens is never such an action for an errand whose deliverable has its own box (a document, pictures — the surface verdict when it is sure, else the `surface` the escalation itself declared) unless the verdict says `canvas = show`: the catalogue rung leaves it to the worker and the promise pass runs nothing (`a_view_is_not_the_deliverable`), so talking about a card's content, or an errand that will read it, does not open it. A browser card — the base one included — with no live task behind it is never restored on reload, on either host. — since 2026-10-27 · nodes 4.302, 4.87, 3.140 · `nucleo/flash/canvas_visibility.py::present_for_call`, `::a_view_is_not_the_deliverable`, `frontend/mobile/app/shell/Deck.js`, `frontend/app/widgets/desktop.js`.
- **CRIT-K34 · A question the state answers is answered, not delegated — when its answer is SAID.** A turn the verdict reads as question · tell · handle_inline annuls its commission and is composed from the turn's state (`escalation_guard.a_question_the_state_answers`, `second_pass.answered_from_state`), unless the verdict's surface is something to LOOK at (`informe`, `lista`, `item`, `imagenes`, `widget`): that goes on to the rung that writes it (a recipe is a document, not «I don't have it stored»). The verdict judges what the model answers: a request his own barge-in cut before its first word is part of the next turn's sentence (`accumulator.whole_turn`), so «…until my style is captured. ¿Te parece bien?» is an order, not a question; and the composed answer IS the reply, never followed by the mute apology. — since 2026-10-27 · nodes 2.759, 3.142 · `nucleo/flash/escalation_guard.py`.

## 4 · Errands and workers

- **CRIT-E1 · The TASK is the unit.** One durable row per errand; the worker reports or the pulse demands it; a
  task is born from four sources only, never from a loop having a tick. — since 2026-09-27 · nodes 3.82, 3.83,
  3.84, 2.18.
- **CRIT-E2 · A message with several tasks is a LIST**: split, queued, run step by step, reported once; the ack of
  a list never blocks its own turn. — since 2026-09-26 · nodes 4.216, 3.90.
- **CRIT-E3 · Resources pinned, reasoning open.** A worker's prompt carries formulas, resources and ways of
  solving, never a script; a fix shaped like the scenario is scaffolding (change one word of the request: does it
  stand?); in doubt it is a RESOURCES problem. — since 2026-08-20 · nodes 2.82, 4.32 ·
  `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`.
- **CRIT-E4 · The rungs, cheapest first**: a declared widget action, then the network (an agent), then the
  browser, which is the LAST resort; a delivered hunt is not re-hunted; one widget per errand, the browser inside
  its process entry in the processes panel (V2-822). — since 2026-09-21 · nodes 2.84, 2.43, 4.109.
- **CRIT-E5 · A report is a DOCUMENT**, and a fast listing pass serves the turn or hands off with its sheet inside
  its budget — a turn is never left mute. — since 2026-09-29 · nodes 4.143, 2.43, 2.171.
- **CRIT-E6 · An errand with a third party offers the model NO tools**: it returns one JSON object and the engine
  executes what the mandate allows — the template of every rail on consequences; a reply the mandate does not cover
  is held for his word (CRIT-C10). — since 2026-09-13 · nodes 3.44, 2.808 · `nucleo/errands/party.py`,
  `nucleo/errands/mandate.py`.
- **CRIT-E7 · A worker's endpoint comes from its spec or the provider chain**, never from the inherited shell; a
  worker never depends on ONE provider. — since 2026-09-19 · nodes 2.82, 4.27.
- **CRIT-E8 · A parked errand is still the errand.** The dedup compares against the errands waiting on his
  yes/no as well as the live ones; a repeat folds into the parked one, the yes carries what he added, and the
  brain repeats the QUESTION, not the work. An audit that comes back after the conversation moved (a turn of
  his, a widget op) may record a finding but never acts or speaks. — since 2026-09-29 · nodes 2.182, 2.180 ·
  `nucleo/dispatch/confirm.py`, `nucleo/susurro/engine.py`.
- **CRIT-E9 · Every request that acts is ONE row, and it ends in a verdict of the one vocabulary**
  (`nucleo/circuit/verdict.py`): its endings are `met` (its end state was attested), `unmet` (attested false after
  its grace, or no tries left — corrected out loud when he ordered it), `unverifiable` (nothing readable could say),
  `undeclared` (the action declares no end state) and `cannot` (nothing could act). Each value declares once whether
  it delivered, its rank, the row state it leaves and its event; a non-ending (`started`, `asked`, `skipped`) never
  settles a row, and every settle emits with the row's trace. A later op never improves a failed row; a worker's
  verdict comes from `circuit.close`, a list step's from its ops; the prompt's recent state reads these rows, facts
  only. An inline row carries its spec, and a live one left by a previous boot is judged once from it (`met`) or
  closed as interrupted, silently. — since 2026-10-28 · nodes 2.194, 2.196, 2.198, 2.829, 3.105, 3.106, 3.113 ·
  `nucleo/circuit/verdict.py`, `nucleo/circuit/` (`settle`, `spec.py`, `ledger.py`), `nucleo/request/model.py`.
- **CRIT-E15 · A collection put together for him is an errand, and it ends in the card that holds it.** The
  escalate question reads «put together several items chosen to fit what he describes» as background work and ONE
  named item into a list as inline (measured live, 22/22); a card that holds such collections declares the op that
  appends several items, mapping each to a usable one through its connected providers in priority order, and the
  end state it leaves (the music card's `add_tracks`); an errand whose end state is rows a card of his declares
  opens no empty sheet (`surfaces.own_card`); the worker delivers into the card its end state names, in batches.
  — since 2026-10-24 · nodes 3.93, 4.263, 2.797 · `nucleo/flash/escalation_guard.py`, `widgets/musica/curated.py`.
- **CRIT-E16 · One errand, one card, and a resumed errand keeps it.** Starting an errand opens no card: its card is its
  deliverable (the sheet; its browser is told in the processes panel, CRIT-E21), opened when the surface is sealed or when the first rows
  land; when he must act in the page (a wall, a login) the errand's sheet is raised — opened then if it had none — and the
  browser's monitor card is only for a tab no errand drives or an errand whose deliverable is not a sheet; a refresh never
  restores an errand's tab beside its card. A resumed or relayed errand reopens the sheet of its DURABLE row (`task_uid`),
  never one named after the new boot, with what it had delivered still in it. — since 2026-10-26 · nodes 4.273, 4.109 ·
  `nucleo/errand_card.py`, `nucleo/sheets.py::row_sheet`.
- **CRIT-E17 · What a source did to one errand is known to the next, with a date, and it expires.** A wall
  (403/CAPTCHA/login), an extract with no named row, a provider's quota and a network agent's timeout, empty answer
  or rows are recorded per SOURCE (host, agent id, `search:<provider>`) by the door that observed them; the newest fact
  wins, a later success resets the repeats, every failure expires on its own clock (a repeat lives up to ×3) and the
  quota at the provider's stated reset. The worker's step 0 carries ONE dated line (≤6 sources) and nothing when nothing
  is current; it orders mesh candidates (a hard failure asked last) and never drops one. — since 2026-10-26 · nodes
  2.804 · `nucleo/workers/source_outcomes.py`, `nucleo/cli/nav.py::_note_source`, `nucleo/mesh_agents.py::_note_answer`.
- **CRIT-E18 · A network agent gets its own time, inside one budget, and only if it is operational.** The skill call
  waits the agent's declared latency ×2, never below 60 s nor above 90 s; one `serve` is bounded by one budget and a
  second candidate gets only what is left; an agent the Oracle or its card states is not online/operational is not
  asked, a learned route to it included, and silence is not a statement; a timeout names the agent and the seconds; zero
  rows with the agent's hint is `ok` with `agent_hint`, never a failure. — since 2026-10-26 · nodes 2.805 ·
  `nucleo/mesh_agents.py::agent_timeout`, `::_ask_in_turn`, `::_is_live`, `::_mark_empty`.
- **CRIT-E19 · What is pending is STATE, and the model resumes it by id.** Pending rows (`nucleo/pending_work.py`: the
  board's live and recently ended errands, errands the energy lease stopped, rows a widget declares with
  `pending_rows()` such as a draft held for his OK) reach the turn prompt as one compact block (ids + names) ONLY when
  any exists, and the model resumes them with `resume_task(ids)` — offered only then; an id that is not a pending row
  is dropped. Each row resumes from itself: a widget row through its own declared action and confirm gate, an ended
  errand from its own brief, sheet and outcome (`task_uid`), a live one not twice. Where the model's commissions
  would be annulled as a fragment or a backstop would rebuild a brief, a verdict over the rows completes it
  (`nucleo/flash/resume_turn.py`), never a phrase table, and no backstop then rebuilds an errand from the window. A
  browser card's title is the errand's name (`navegador.tasks.set_title`). — since 2026-10-26 · nodes 2.807.
- **CRIT-E20 · An errand's process moves with the worker, in ONE place.** Every recorded line, declared plan and step done tells the processes panel (`sheets.notify_process` → SSE `task process`), never a card; the record carries the worker's own plan and how much of it is done — its words, never steps the engine invents. — since 2026-10-27 (V2-820, moved to the panel by V2-822) · nodes 3.141 · `nucleo/sheets.py`, `nucleo/workers/reports.py`.
- **CRIT-E21 · An errand opens only its deliverable; its progress lives in the processes panel.** When the errand's surface names a card (`surfaces.deliverable_card`: the results sheet for `lista`/`item`, the document for `informe`, the viewer for `imagenes`), a worker's `show_widget` of any other card is refused at the one door (`deliverable_gate`, before `_exec_allow`) with the way through — read it without opening it, deliver into the deliverable; reads and writes are untouched. An errand told by voice or done silently (`voz`/`silenciosa`) opens NO card — only one its own end state (`done_when`) names; a question answered inline is no process at all (its request row is `kind=inline`, off the board, the count and pending work). The results sheet has no process tab: its Results tab carries the loader while the errand works and the errand's page shows on it only when the page needs HIM (a wall, a login, a question); the document card shows «being created» (or «not written» when the errand ended without it) and points to the panel. The running process's entry in the processes panel — the desktop's tab and the phone's menu — paints ONE record (`GET /api/tasks/<id>/process`, `nucleo/process_view.py`, derived from the live registry): collapsed, the plan around its step (✓ ▸ ·); expanded by him, the whole plan, the page and its capture, the harvest and the narration newest first; in both, its LAST line says what it waits on him for (signing in, blocked with no window, the page). «Proceso» said to the results sheet opens that panel through the sheet's own `tab` action. — since 2026-10-27 · nodes 3.143, 3.144, 4.310, 4.311, 4.312, 4.143 · `nucleo/deliverable_gate.py`, `nucleo/process_view.py`, `frontend/app/components/ProcessEntry.js`, `widgets/results/widget.js`, `widgets/documento/widget.js`.
- **CRIT-E22 · Where a browser window for him can open is ONE answer, and «nowhere» blocks the process.** `nucleo/browser_window.reach()`: a display here → the window opens here and the process watches it; no display → only through a connected daemon that DECLARES `browser.auth` (registered by its transport, never guessed); neither → a sign-in he must do BLOCKS the process (`needs_input` + `blocked: no_window`, not failed, no question open) and he is told once, in his language, by voice and in the chat, that without the daemon it cannot continue. — since 2026-10-27 (V2-822) · nodes 4.314 · `nucleo/browser_window.py`, `widgets/navegador/owner_login.py`.
- **CRIT-E23 · The count of running processes is one number on every screen.** The desktop's bar and the phone's dock mount ONE component (`ProcessCount.js`) reading ONE number (`store.liveProcessCount`: his live commissions from the engine's board, moved by SSE `task` events and re-read from the board when a process starts or ends); hidden at zero; a tap opens the processes view. — since 2026-10-27 (V2-822) · nodes 4.313 · `frontend/app/components/ProcessCount.js`, `frontend/app/core/store.js`.
- **CRIT-E13 · A worker's request is never his click.** On a self-hosted engine every mutation is the operator's
  unless it is a named worker door (`/api/worker/*`, the agent report, the browser bridge, memory with the per-task
  token, search); it is admitted for his screen's per-boot HttpOnly cookie or a process the engine did not spawn,
  and refused for a worker (engine ancestry, a remembered worker session, worker env), the engine itself or a
  socket nobody here owns. The CSRF/rebinding rules of CRIT-E11 also cover mutations outside `/api/`. — since
  2026-10-14 · nodes 2.620, 2.621, 2.622, 2.623, 2.624 · `server/operator_gate.py`, `server/peer_process.py`,
  `server/ui_session.py`, `nucleo/workers/providers/spawned.py`.
- **CRIT-E12 · What a stranger wrote is data, and it cannot send on its own.** Every body of a mail, a chat or an
  agent's answer reaches the model fenced (⟦ ⟧, unforgeable); with such text in the context, an act that leaves runs
  without a question only when the verdict surely names that send — both channels. — since 2026-10-02 · nodes 2.205 ·
  `nucleo/untrusted.py`, `nucleo/flash/leave_gate.py`.
- **CRIT-E11 · A web page cannot drive the engine.** On a self-hosted engine every `/api/*` call names this engine in
  `Host` and comes from this machine, and a mutation from another site (`Origin`, `Sec-Fetch-Site: cross-site`) is
  refused; `ZAELAR_API_TOKEN` is the only door for a caller elsewhere. On a hosted deployment a mutation comes from the
  deployment's own site. — since 2026-10-02 · nodes 7.62 · `server/api_guard.py`, `server/__init__.py`.
- **CRIT-E10 · A worker that may write writes only inside its own workdir.** Every trusted worker with `Write` gets
  the writes-only jail (a PreToolUse hook: Write/Edit outside the workdir denied, reads free); the dev-worker keeps
  its full jail; a jail that cannot be armed takes the writing tools away, never the jail. — since 2026-10-01 ·
  nodes 3.112, 2.5 · `nucleo/dev_worker_guard.py`, `nucleo/dispatch/session.py`.
- **CRIT-E14 · A worker reaches its own engine behind session admission.** Where every request must carry a
  session, a loopback call to one of the worker doors (`operator_gate.WORKER_DOORS`) is served without one — each
  door verifies the worker itself; off the machine, or to any other route, the session is still required
  (`server/ingress.py::is_own_worker_door`). — since 2026-10-24 · nodes 7.77.

## 5 · Memory and rules

- **CRIT-M1 · Only the rules in play reach the model.** A sentence of his no code applies is a `note` row with a
  scope (`global`, `voice`, `widget:<id>`); the voice turn carries `global` + `voice` inside the budget of the block it
  replaced, a card's notes ride in its row only while it is on screen, named or recent, the worker never carries how
  the voice speaks; a rule code applies never enters as prose (his permissions: one compact line); memory composes
  none. — since 2026-10-26 · nodes 2.172 · `rules/prompt.py`, `rules/notes.py`, `widgets/brief.py`.
- **CRIT-M7 · Every standing rule and preference is ONE row of the `rules` table**, scoped (`global` ·
  `<domain>[/<channel>[/<act>]]` · `widget:<id>[/<action>]` · `item:<id>`, read from declared classes, channels and
  manifests) and read by a cascade over the request's path: the more specific row runs last and wins, at one level
  his row beats the default, an `except` scope is not covered, a row past its `until` is absent. Genesis defaults are
  rows built at read time. `consent.decide` reads the gate; the rails (a missing fact, a doubt, the radius) are code
  no row reaches. The style knobs (`voice`), a widget's preferences (`widget:<id>`) and the autoresponder (scoped to
  its platform) are rows too; each older store is imported once. Every row has an id: «what rules do I have?», «forget
  the email rule» and ⚙ Settings → Rules list, edit, switch off and delete BY ID (a default is overridden, never
  deleted); he never sees an id, a key or a scope — his own words, places named from declared data in his language. — since 2026-10-26 · nodes 2.809, 2.810, 2.811, 2.812 · `rules/`,
  `nucleo/consent.py`, `nucleo/style_policy.py`, `widgets/youtube/prefs.py`.
- **CRIT-M2 · Genesis is per domain** (`style`, `consent`, `library`, `errands`, `playbooks`); what he says over
  `style` and `consent` is a row of the rules table (CRIT-M7), the others keep their override file; a factory reset forgets the spoken rules and keeps credentials, settings and connectors; it never
  deletes under a live server. — since 2026-09-29 · nodes 2.173, 8.4, 3.94.
- **CRIT-M3 · A late recall DEGRADES durable memory, never deletes it**; the memory row says whose fact it
  shows. — since 2026-09-24 · nodes 3.79, 3.33.
- **CRIT-M4 · What the operator said survives a failing turn**, and a spoken correction reaches the pill it
  corrects. — since 2026-09-03 · nodes 2.19.
- **CRIT-M5 · The whole prompt of every turn is on disk**, joined by trace; capture is never switched off. — since
  2026-09-20 · nodes 2.100.
- **CRIT-M6 · The memory state is written only when it changes.** The live-session projection's change key is
  computed with the clock frozen, so no clock-derived field (`age_s`, `unreported_s`…) can rewrite the state — and
  emit a `memory`/`state` event — on a tick where nothing happened (`dispatch.sync_state`). — since 2026-10-24 ·
  nodes 7.78.
- **CRIT-M8 · Memory keeps what HE said, and only that.** The distiller reads a pasted text whole (head and tail)
  and knows its channel (spoken or typed) and the assistant's own name; an identity claim rejected as «not about the
  operator» writes no trusted row (quarantined, like any rejected identity); «I already told you X» is not a fact;
  each row records its real channel; the words before a wake word count only when the paid STT could not hear them,
  so our own voice is never his. — since 2026-10-26 · nodes 1.3, 4.209 · `nucleo/memory_agent/processor/distill.py`,
  `nucleo/memory_agent/`, `voice/engine/pipeline/agent_events.py`.
- **CRIT-M9 · Inbound messages are their own lane, and recall says where each line came from.** A `msg` row is
  never promoted, never in the passive blocks, never ranked with his own facts (`query(lane="own")` is the
  default; `messages` and `all` are asked for); recall returns id, date, level, kind, source and session, and his
  own past conversation has one reader (`memory.conversation`, `mem_cli history`). — since 2026-10-26 · nodes 1.2,
  1.10 · `memory/retriever.py`, `memory/history.py`, `server/memory_routes.py`.
- **CRIT-M10 · The memory viewer never paints more than the device can draw.** The overview shows totals (COUNTs,
  by type and by day) and charts; the «Cards» tab shows the NEWEST memories per layer, capped on the server and each
  text cut; the graph is aggregated on the server and bounded by the device's node budget — past it, only its top
  level (the concepts) is sent. No row list of a store, and nothing about the machine, ever reaches it; its canvas
  is fitted to its own panel. — since 2026-10-26, cards and top level 2026-10-27 · nodes 1.11, 1.12 ·
  `memory/viewer.py`, `server/memory_viewer_api.py`, `frontend/app/components/memory/`.
- **CRIT-M11 · A file added to the chat is a REFERENCE, streamed to disk and read once with bounded work.** The
  kind is decided by its bytes (image, PDF, text); size, files per message and the disk's free-space headroom are
  refused before a byte is written, from ONE declared table (`config/attachments.default.json`, measured); the
  body streams to disk, files are read one at a time, and the turn sees what he just attached as state — the
  reading made at upload, an image read by a model that receives it — and nothing when there is none. — since
  2026-10-26 · nodes 1.13, 2.814, 4.296 · `files/attachments.py`, `server/memory_routes.py`,
  `frontend/app/services/chat-files.js`.

## 6 · Resilience

- **CRIT-R1 · A bug of ours is not a provider outage.** The exception decides (an HTTP status is theirs, a bare
  Python error is ours); the SAME request relays to the stand-in inside the connect loop; the panel names titular
  and stand-in, amber while the substitute serves. — since 2026-09-23 · nodes 2.77, 2.54, 4.27.
- **CRIT-R2 · The voice brain is a non-reasoner, model per invocation, and the provider order is
  CONFIGURATION** (`config/v2.json`, managed by the UI) — never a rule in a document. — since 2026-08-19 · nodes
  2.54.
- **CRIT-R3 · Embeddings have no failover model** (a stand-in answers in another vector space); the fall is made
  visible. — since 2026-09-23 · nodes 10.52.
- **CRIT-R4 · No language, no agent**: until the picker locks a language the agent is stopped; after ANY reset it
  comes up listening. — since 2026-09-24 · nodes 4.217, 8.4.
- **CRIT-R5 · The voice has a stand-in**: the models table's `tts.failover` is built beside the titular; a titular
  that cannot be built (no key) is replaced at boot, and LiveKit's `FallbackAdapter` switches on a synthesis that
  fails for good (a 402); the meter bills the provider that spoke. — since 2026-09-30 · nodes 2.202 ·
  `voice/engine/speech/tts/__init__.py`.
- **CRIT-R6 · With `ZAELAR_USER_ID` set, no torrent client runs** unless `ZAELAR_TORRENT_IN_CLOUD=1` is also
  set; without it, the operator's switch decides. — since 2026-09-30 · nodes 5.61 · `connectors/torrent/service.py`.
- **CRIT-R7 · What leaves the machine is scrubbed.** The feedback evidence never carries `system` events (the
  forensic turn holds the whole prompt) and every string goes through one scrubber (vault detector + token
  shapes; a scrubber failure withholds, never passes); the full prompt capture is scrubbed, under the
  workspace, capped per session, and OFF when `ZAELAR_USER_ID` is set unless `ZAELAR_LOG_PROMPTS=1`. — since 2026-10-01 ·
  nodes 7.61 · `observability/scrub.py`, `server/feedback_api.py`, `voice/observer.py`.
- **CRIT-R8 · Paid work asks the usage lease BEFORE it starts.** If a usage lease is configured and exhausted, a
  paid call is refused (`OutOfEnergy`, never a provider failure: no relay, no light), the fuse stops the agent, and
  the UI shows the exhausted state with a link to `ZAELAR_ACCOUNT_URL` when set; with no lease configured, every
  call is admitted. A boot probe never pays. — since 2026-10-22 · nodes 8.21, 4.247 · `nucleo/energy/lease.py::check`.
- **CRIT-R9 · A device that cannot capture or play is red on the orb, and said.** Each of the microphone and the
  speaker has ONE derived health (`store.micHealth()` / `store.spkHealth()`); a problem (no permission, dead or
  source-muted track, capture error, playback blocked or paused, remote track ended, output lost, the agent
  speaking with no received energy) paints its icon red with the reason in the title, is reported once as a
  `client` event, and clears by itself; a deliberate mute is never red except for a revoked permission.
  — since 2026-10-24 · nodes 3.119 · `frontend/app/services/device-health.js`.
- **CRIT-R10 · A spent lease is not an empty account.** Running the usage lease out — by amount or by clock — asks
  for another at once (bounded backoff) before any stop; only an answer carrying `ok: false` is a verdict (a 5xx,
  a timeout or a body without `ok` is a failed renewal). A stop carries its cause: `energy_denied` (the endpoint
  said no) is the only one told as an empty account with a top-up; `lease_unrenewed` says the agent could not
  confirm its Energy. The cause persists across a restart, boot asks for a fresh lease before any stop decision,
  and the notice never says «empty» next to a battery showing Energy. — since 2026-10-26 · nodes 8.25, 4.247 ·
  `nucleo/energy/lease.py::_renew_or_blow`, `frontend/app/core/account-link.js::noticeKind`.

## 7 · Working here

- **CRIT-W1 · Mechanisms, not rules.** A change that bounds a CONSEQUENCE stays; one that bounds JUDGEMENT is
  removed; a sentence about how to behave is a rail — delete it and find the mechanism it stood for. — since
  2026-09-15 · nodes 7.32 · `.meshkore/context/principles.md`.
- **CRIT-W2 · English everywhere inside `engine/`** — code, tests, logs, docs, commits; product data in the
  user's language; the module logs in the operator's; Castilian comment lines only shrink. — since 2026-10-01 ·
  nodes 7.60.
- **CRIT-W3 · Never restart with someone inside or an errand alive** (recent `transcript`/`brain` events, or a
  non-empty `/api/tasks`). — since 2026-09-15 · ⚠ sin test.
- **CRIT-W4 · Commit with pathspec after `git diff --cached --name-only` is empty; push after every commit;
  never rewrite pushed `main` for an attribution; never touch another session's uncommitted work.** — since
  2026-08-20 · ⚠ sin test.
- **CRIT-W5 · A wide pass runs under `tests/watchdog.py`, never bare `pytest`**; while iterating, the touched
  file and its DISARM; a test is not a test until seen red; a disarm that stays green accuses the TEST; the
  harness clears `__pycache__` on restore. — since 2026-09-20 · nodes 7.53.
- **CRIT-W6 · A test never touches the operator's real state** (the root `conftest.py` sandbox, which pins
  `ZAELAR_WORKSPACE` and fails BY NAME the test after which his consent/style/library config changed); a red that
  does not reproduce alone is contamination, not a bug; no real identity sits in a tracked file; every connector token store follows
  `ZAELAR_WORKSPACE`, so an isolated engine never holds his tokens. — since 2026-09-30 · nodes 3.94, 3.115, 7.10, 7.55.
- **CRIT-W7 · A test outside the map does not exist**; every mechanism ships with its node; a node whose file is
  gone is red, and a file answers one deterministic node. — since 2026-09-30 · nodes 7.32, 7.56.
- **CRIT-W8 · Public and private.** `engine/` describes mechanism, never product; development history and
  planning are not published (planning notes, module logs, test reports stay local and untracked). — since 2026-10-01 · nodes 7.60.
- **CRIT-W10 · Fix the class, never the case.** A red test or a judge finding is the SYMPTOM of a class; the fix is
  named by the class it closes and its test carries a variant the failing case did not (the other language, a
  reworded request, another domain). Never: a word, regex or literal so one recorded case passes; a test id or a
  fixture's string in product code; an assertion weakened to go green (it changes only when the behaviour changed
  on purpose, said in the commit); a ratchet ceiling raised. Reach, in order: a verdict already paid → a declared
  datum (manifest, brief, catalogue) → a structure (one door, one reader) → language data in `i18n/`. Too big for
  the batch: the test stays RED and the class is tracked as open work — an honest red beats a patched green.
  Product regexes and word tables only shrink. — since 2026-10-19 · nodes 7.73 ·
  `.meshkore/context/principles.md` §«Fix the class».
- **CRIT-W9 · Closing a batch:** the node in the map, the WHY in the diary, the operator's words in the module
  log — and a line HERE only when a rule changed. — since 2026-09-29 · ⚠ sin test.

---

## 8 · Search — the service

- **CRIT-S1 · A row on the results sheet is a CANDIDATE or the PAGE that lists candidates, never both.** A
  candidate names one thing and carries a datum of its own (price, rating, its own phone, a fact); a row without one
  whose title counts or ranks a category, or whose url is an article/policy page, goes to Sources with its reason
  and the reply says so. Applied once, at `present`/`append`. — since 2026-10-10 · nodes 12.1 · `search/candidacy.py`.
- **CRIT-S2 · A criterion NO row can show is said missing, never implied met.** When every row carries only a name
  and a link, the sheet's digest and `find().unshown` name the asked criteria (rating, availability, price) as not
  found. — since 2026-10-10 · nodes 12.2.
- **CRIT-S3 · The number the operator said is his breadth.** «A couple» is three and «las tres mejores» is three; a
  request that names none keeps the floor (25 / 10). An article («un piso», «a flat») is not a number. The research
  brief caps the model's own count with it. — since 2026-10-10 · nodes 12.3, 12.8 · `search/criteria.py`.
- **CRIT-S4 · ONE place routes a search request to its module**, by precedence: the brief's sure `search_module`
  verdict → the model's named tool → the unsure verdict → escalate + surface → default fact. No verb tables; a video
  or music request never consults it. Applied in shadow mode: the route is recorded beside the live path before it is allowed to act. — since
  2026-10-10 · nodes 12.4, 12.8 · `search/route.py`, `nucleo/flash/search_routing.py`.
- **CRIT-S5 · Every search provider is declared once, probed with one minimal real call, and reported by key
  NAME**: live · missing · exhausted · blocked · credential; a missing key is missing, never down. The use-case
  harness does not grade a batch when no provider can answer (exit 4, INFRA); the status panel shows the last probe
  and never probes on a poll. — since 2026-10-10 · nodes 12.5, 12.6, 12.9 · `search/providers/`, `search/health.py`.
- **CRIT-S7 · A worker searches with `act use_tool "<query>"`** — a quoted sentence, no JSON, no file: the one form
  the confinement guard lets through — and gets the service's answer (chain dict + route + candidates + pages +
  unshown). The two fact doors of the turn call `find()` too. — since 2026-10-10 · nodes 12.9.
- **CRIT-S6 · The search service owes the turn nothing.** `search/` never imports `nucleo/flash`, `voice` or
  `widgets`; what it needs from the host (status light, timeline) are hooks set at boot; the old `nucleo.*` import
  paths are aliases of the same modules. — since 2026-10-10 · nodes 12.8 · `search/hooks.py`.

## Contradicciones (contradictions — this table must stay empty)

| topic | rule A | rule B | winner |
|---|---|---|---|
