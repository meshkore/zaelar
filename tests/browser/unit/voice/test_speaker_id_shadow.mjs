// V2-651 F0 — browser-side speaker fingerprint, shadow measurement.
//
// The operator's directive: the browser carries the cost and sends only a tiny verdict. These drive the REAL
// module (lib/speaker-id.js) — the pure DSP core with synthetic frames, and the SpeakerID adapter through a fake
// AnalyserNode — and assert the session wiring runs it in shadow and stops it with the session.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  rmsOf, pitchOf, centroidOf, frameFeatures, snapshot, buildProfile, matchScore, classify, distancesTo,
  Segmenter, SpeakerID,
} from "../../../../frontend/app/lib/speaker-id.js";

const SR = 48000, N = 2048;

// A clean sine at `hz` — a stand-in for a voiced frame whose fundamental the pitch tracker must find.
function sine(hz, amp = 0.3, n = N, sr = SR) {
  const a = new Float32Array(n);
  for (let i = 0; i < n; i++) a[i] = amp * Math.sin(2 * Math.PI * hz * i / sr);
  return a;
}
// A byte magnitude spectrum with a peak at `peakHz`, so centroidOf ≈ peakHz (a timbre stand-in).
function spectrum(peakHz, bins = N / 2, sr = SR) {
  const fd = new Uint8Array(bins);
  const hzPerBin = sr / (bins * 2);
  const k = Math.round(peakHz / hzPerBin);
  for (let i = 0; i < bins; i++) fd[i] = Math.max(0, 200 - 12 * Math.abs(i - k));
  return fd;
}

// ── the pure math ──
{
  assert.ok(rmsOf(new Float32Array(N)) < 1e-6, "silence has ~zero RMS");
  assert.ok(rmsOf(sine(150)) > 0.15, "a 0.3-amp sine has real RMS");

  const p = pitchOf(sine(150), SR);
  assert.ok(Math.abs(p - 150) < 20, `pitch of a 150 Hz sine ≈ 150 (got ${p.toFixed(1)})`);
  const p2 = pitchOf(sine(240), SR);
  assert.ok(Math.abs(p2 - 240) < 25, `pitch of a 240 Hz sine ≈ 240 (got ${p2.toFixed(1)})`);

  const c = centroidOf(spectrum(1200), SR);
  assert.ok(Math.abs(c - 1200) < 120, `centroid tracks the spectral peak (got ${c.toFixed(0)})`);
}

// ── enroll + classify: the operator vs another voice, and a known household voice ──
{
  // Voice A = the operator (low pitch, low centroid). Voice B = someone else (higher pitch, brighter timbre).
  const featA = () => frameFeatures(sine(120, 0.32), spectrum(900), SR);
  const featB = () => frameFeatures(sine(230, 0.32), spectrum(2400), SR);

  // three enrollment segments per voice → a profile each
  const opProf = buildProfile([0, 1, 2].map(() => snapshot([featA(), featA(), featA()])));
  const kidProf = buildProfile([0, 1, 2].map(() => snapshot([featB(), featB(), featB()])));

  const aSnap = snapshot([featA(), featA(), featA()]);
  const bSnap = snapshot([featB(), featB(), featB()]);

  assert.ok(matchScore(aSnap, opProf) >= 0.5, "the operator's own voice scores high against his profile");
  assert.ok(matchScore(bSnap, opProf) < matchScore(aSnap, opProf),
    "another voice scores lower against the operator's profile than his own does");

  const profiles = { operator: opProf, "known:kid": kidProf };
  assert.equal(classify(aSnap, profiles).id, "operator", "the operator's voice classifies as operator");
  assert.equal(classify(bSnap, profiles).id, "known:kid", "a known household voice classifies as that person");
}

// ── the CONTINUOUS distance: the vote is too coarse to pick a threshold from, the distance is not ──
{
  const featA = () => frameFeatures(sine(120, 0.32), spectrum(900), SR);
  const opProf = buildProfile([0, 1, 2].map(() => snapshot([featA(), featA(), featA()])));

  // measured: across 60 distinct synthetic voices `matchScore` returns only THREE values — useless as a threshold
  const votes = new Set(), dists = new Set();
  for (const hz of [110, 120, 130, 150, 170, 190, 210, 230, 250, 300]) {
    for (const pk of [700, 900, 1200, 1800, 2400, 3000]) {
      const s = snapshot([frameFeatures(sine(hz, 0.32), spectrum(pk), SR),
                          frameFeatures(sine(hz, 0.32), spectrum(pk), SR),
                          frameFeatures(sine(hz, 0.32), spectrum(pk), SR)]);
      votes.add(matchScore(s, opProf).toFixed(3));
      const d = distancesTo(s, opProf);
      if (d && d.mean != null) dists.add(d.mean.toFixed(3));
    }
  }
  assert.ok(votes.size <= 4, "the vote is coarse by construction (3 criteria → at most 4 values)");
  assert.ok(dists.size > 20,
    `the continuous distance actually separates voices (got ${dists.size} distinct values over 60 voices)`);

  // and it points the right way: the operator's own voice is NEARER than a clearly different one
  const near = distancesTo(snapshot([featA(), featA(), featA()]), opProf).mean;
  const far = distancesTo(snapshot([frameFeatures(sine(235, 0.32), spectrum(2500), SR),
                                    frameFeatures(sine(235, 0.32), spectrum(2500), SR),
                                    frameFeatures(sine(235, 0.32), spectrum(2500), SR)]), opProf).mean;
  assert.ok(far > near, `a different voice must be FARTHER from the profile (near=${near}, far=${far})`);
}

// ── the Segmenter opens once on speech and closes once on silence ──
{
  const seg = new Segmenter();
  const evs = [];
  for (let i = 0; i < 5; i++) { const e = seg.feed(0.05); if (e) evs.push(e); }   // speech
  for (let i = 0; i < 15; i++) { const e = seg.feed(0.001); if (e) evs.push(e); } // silence
  assert.deepEqual(evs, ["start", "end"], "one start then one end across a speech→silence run");
}

// ── the SpeakerID ADAPTER end to end, through a fake AnalyserNode (no browser needed) ──
{
  const fake = {
    fftSize: N, frequencyBinCount: N / 2, _td: new Float32Array(N), _fd: new Uint8Array(N / 2),
    getFloatTimeDomainData(a) { a.set(this._td); },
    getByteFrequencyData(a) { a.set(this._fd); },
  };
  const seen = [];
  const spk = new SpeakerID(() => fake, () => SR, { minEnroll: 2, onUtterance: (v) => seen.push(v) });

  // drive one segment: load a voice, feed loud frames, then quiet frames to close it. Throttle skips odd ticks,
  // so feed generously.
  const drive = (td, fd) => {
    fake._td = td; fake._fd = fd;
    for (let i = 0; i < 30; i++) spk.tick();
    fake._td = new Float32Array(N); fake._fd = new Uint8Array(N / 2);
    for (let i = 0; i < 30; i++) spk.tick();
  };

  drive(sine(120, 0.32), spectrum(900));   // operator segment 1 (enroll)
  drive(sine(120, 0.32), spectrum(900));   // operator segment 2 (enroll completes at minEnroll=2)
  assert.ok(spk.enrolled(), "auto-enrollment completes after minEnroll operator segments");
  assert.ok(seen.slice(0, 2).every(v => v.label === "enroll"), "the enrollment segments are labelled enroll");

  drive(sine(120, 0.32), spectrum(900));   // operator again → should classify as operator
  const opTurn = seen[seen.length - 1];
  assert.equal(opTurn.label, "operator", "after enrollment, the operator's own voice is labelled operator");
  assert.ok(typeof opTurn.opScore === "number", "the verdict carries the operator score for shadow measurement");

  drive(sine(235, 0.32), spectrum(2500));  // a different voice → not the operator
  const otherTurn = seen[seen.length - 1];
  assert.equal(otherTurn.label, "other", "a clearly different voice is labelled other, not operator");
  assert.ok(otherTurn.opDist && typeof otherTurn.opDist.mean === "number",
    "every verdict carries the continuous distance F1 will threshold on");
}

// ── SUPPRESSION: the agent's own voice never becomes a segment (it would be enrolled as the operator) ──
{
  const fake = {
    fftSize: N, frequencyBinCount: N / 2, _td: new Float32Array(N), _fd: new Uint8Array(N / 2),
    getFloatTimeDomainData(a) { a.set(this._td); },
    getByteFrequencyData(a) { a.set(this._fd); },
  };
  const seen = [];
  let botTalking = true;
  const spk = new SpeakerID(() => fake, () => SR, {
    minEnroll: 2, onUtterance: (v) => seen.push(v), suppressed: () => botTalking,
  });
  const drive = (td, fd) => {
    fake._td = td; fake._fd = fd;
    for (let i = 0; i < 30; i++) spk.tick();
    fake._td = new Float32Array(N); fake._fd = new Uint8Array(N / 2);
    for (let i = 0; i < 30; i++) spk.tick();
  };

  drive(sine(200, 0.32), spectrum(1800));   // this is the AGENT's own TTS coming back through the mic
  drive(sine(200, 0.32), spectrum(1800));
  assert.deepEqual(seen, [], "nothing is fingerprinted while the agent is speaking");
  assert.ok(!spk.enrolled(), "and the agent's own voice can never be auto-enrolled as the operator");

  botTalking = false;                        // the agent stops; the real person speaks
  drive(sine(120, 0.32), spectrum(900));
  assert.equal(seen.length, 1, "once the agent is quiet, real speech is measured again");
}

// ── the level check: a mic quieter than the start floor must be REPORTABLE, not a mystery ──
{
  const fake = {
    fftSize: N, frequencyBinCount: N / 2, _td: new Float32Array(N), _fd: new Uint8Array(N / 2),
    getFloatTimeDomainData(a) { a.set(this._td); },
    getByteFrequencyData(a) { a.set(this._fd); },
  };
  const seen = [];
  const spk = new SpeakerID(() => fake, () => SR, { minEnroll: 2, onUtterance: (v) => seen.push(v) });

  // a mic far below the start floor: speech-like, but too quiet to ever open a segment
  fake._td = sine(120, 0.004); fake._fd = spectrum(900);
  for (let i = 0; i < 60; i++) spk.tick();

  assert.deepEqual(seen, [], "too quiet to segment: no verdicts, as expected");
  assert.ok(spk.peakRms() > 0, "but the peak level was still observed");
  assert.ok(spk.peakRms() < spk.startFloor(),
    `and it is measurably BELOW the start floor (peak=${spk.peakRms().toFixed(4)} < ${spk.startFloor()}) — `
    + "which is what turns 'nothing is logged' into a diagnosis");
}

// ── the wiring: session-lk.js runs the shadow and stops it with the session, log-only and killable ──
{
  const src = readFileSync(new URL("../../../../frontend/app/services/session-lk.js", import.meta.url), "utf8");
  assert.ok(src.includes('from "../lib/speaker-id.js'), "session-lk imports the speaker module");
  // Anchor the CALL SITE, not two independent substrings. The first version of this asserted
  // `includes("_startSpeakerShadow();") && includes("audio.initMic(stream);")`, which stayed GREEN with the two
  // lines swapped — it verified nothing about where the shadow is started. (The lazy analyser getter means the
  // order is not crash-critical, but a start that drifts out of the session's startup IS a regression.)
  assert.ok(/audio\.initMic\(stream\);[^\n]*\n\s*_startSpeakerShadow\(\);/.test(src),
    "the shadow is started inside start(), right after the mic analyser is built");
  // anchor on the CALL site inside stop() (after _stopHeartbeat), not the function definition — a disarm that
  // removes the call must go red.
  assert.ok(/_stopHeartbeat\(\);[\s\S]{0,200}?_stopSpeakerShadow\(\);/.test(src),
    "the shadow loop is stopped inside stop(), right after the heartbeat");
  assert.ok(src.includes('api.clientLog("🎙️ speaker"'), "the verdict is logged to observability (shadow), not gated");
  assert.ok(src.includes("zaelar_spk_shadow") && src.includes('"nospk"'), "the shadow is killable");
  assert.ok(/suppressed:\s*\(\)\s*=>[^\n]*botSpeaking/.test(src),
    "the agent's own voice is suppressed — an unsuppressed TTS segment could be enrolled as the operator");
  assert.ok(src.includes("d_mean") && src.includes("d_pitch"),
    "the continuous distances F1 will threshold on are logged, not just the coarse vote");
  // DIAGNOSABILITY: measured 2026-09-10 — real sessions with the mic open produced zero verdicts, and with
  // everything in silent try/catch a stale tab, a throwing constructor and a too-high floor all looked the same.
  assert.ok(src.includes('"🎙️ speaker: armado"'), "arming says so, or its absence cannot be read");
  assert.ok(src.includes('"⚠️ speaker: no arrancó"'), "a failure to arm is reported, never swallowed");
  assert.ok(src.includes("peakRms()") && src.includes("startFloor()"),
    "the level check reports the loudest frame against the start floor");
  // F0 must not touch behaviour: no gate/turn/close call in the shadow path.
  assert.ok(!/_startSpeakerShadow[\s\S]{0,600}(sendText|setGate|publishData)/.test(src),
    "the shadow path neither gates nor sends turns — it only measures");
}

console.log("ok — speaker-id shadow (9 groups)");
