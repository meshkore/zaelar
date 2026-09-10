// ============================================================================
// speaker-id.js — browser-side speaker recognition (V2-651, phase F0: SHADOW).
//
// WHY THIS LIVES IN THE BROWSER. The operator's architectural directive: the client
// carries the CPU/latency cost, the backend receives only a tiny verdict, never the
// audio-to-analyze. In cloud that matters — the backend runs on the server, the
// browser on the client's laptop — so the fingerprint is computed HERE and only a
// label ("operator" | "other" | "known:<id>") + a score cross the wire. In a local
// self-host run it's all one machine and the split is free.
//
// WHAT F0 DOES. Shadow measurement only, ZERO behaviour change: per speech segment
// it computes an acoustic fingerprint, matches it against the enrolled voices, and
// LOGS the verdict to observability (through the existing client-log seam). Nothing
// is gated, no memory is written, no prompt changes. Its whole job is to produce the
// separability numbers that later phases threshold against — measured on the
// operator's real mic and room, per the "measure, don't deduce" rule.
//
// THE FINGERPRINT is an acoustic descriptor (autocorrelation pitch + spectral
// centroid + loudness), FFT/analyser-free in its math so the core is unit-testable
// with synthetic frames. It separates timbres (you vs a child, you vs another adult)
// reasonably, not perfectly — far-field, short utterances and TV/music voices are the
// hard cases (the reason F0 measures before F3 ever hard-locks). For rock-solid
// identity, swap `frameFeatures`/`matchScore` for an ONNX speaker embedding
// (CAM++ via onnxruntime-web) behind THIS SAME interface — the multi-profile shape
// below is already what an embedding classifier needs.
//
// MULTI-PROFILE FROM THE START (the operator's "environment people"): `classify`
// scores against a MAP of profiles — the operator plus any known household voices —
// so when F2 adds `config/voices.json` (voiceprint + name + relation) this file does
// not change: a known person just becomes another entry, matched the same way.
//
// The DSP core is a hardened descendant of the orphaned lib/speaker-gate.js, restructured
// into pure functions (Node-importable) + a thin AnalyserNode adapter.
// ============================================================================

// ---- pure DSP core (no browser globals; unit-tested with synthetic arrays) ------------------

// RMS of a time-domain frame (Float32Array in [-1,1]).
export function rmsOf(td) {
  let s = 0;
  for (let i = 0; i < td.length; i++) s += td[i] * td[i];
  return Math.sqrt(s / (td.length || 1));
}

// Autocorrelation pitch over the human voice range 70–400 Hz. Returns Hz, or 0 if unvoiced.
export function pitchOf(td, sr) {
  const minLag = Math.floor(sr / 400), maxLag = Math.floor(sr / 70);
  let best = -1, bestVal = 0, prev = 0, going = false;
  for (let lag = minLag; lag <= maxLag && lag < td.length; lag++) {
    let sum = 0;
    for (let i = 0; i < td.length - lag; i++) sum += td[i] * td[i + lag];
    if (sum > prev) going = true;
    if (going && sum < prev && prev > bestVal) { bestVal = prev; best = lag - 1; }
    prev = sum;
  }
  return best > 0 ? sr / best : 0;
}

// Spectral centroid (Hz) from a byte magnitude spectrum (Uint8Array, as getByteFrequencyData gives).
export function centroidOf(fd, sr) {
  let num = 0, den = 0;
  const hzPerBin = sr / (fd.length * 2);
  for (let i = 0; i < fd.length; i++) { num += i * hzPerBin * fd[i]; den += fd[i]; }
  return den ? num / den : 0;
}

// One frame → {pitch, centroid, rms}. `fd` may be null (then centroid is 0 and simply not used).
export function frameFeatures(td, fd, sr) {
  return { pitch: pitchOf(td, sr), centroid: fd ? centroidOf(fd, sr) : 0, rms: rmsOf(td) };
}

// Collapse a set of per-frame features (one speech segment) into a stable snapshot:
// pitch by MEDIAN (robust to octave errors), the rest by mean, near-silent frames dropped.
export function snapshot(frames) {
  const voiced = frames.filter(f => f.rms >= 0.012);
  if (voiced.length < 3) return null;
  const pitches = voiced.map(f => f.pitch).filter(p => p > 0).sort((a, b) => a - b);
  const mean = k => voiced.reduce((s, f) => s + f[k], 0) / voiced.length;
  return {
    pitch: pitches.length ? pitches[Math.floor(pitches.length / 2)] : 0,
    centroid: mean("centroid"),
    rms: mean("rms"),
  };
}

// Build a voice PROFILE from a list of enrollment snapshots (mean + std per feature).
export function buildProfile(snaps) {
  const stat = k => {
    const v = snaps.map(s => s[k]).filter(x => x > 0);
    const m = v.reduce((s, x) => s + x, 0) / (v.length || 1);
    const sd = Math.sqrt(v.reduce((a, x) => a + (x - m) ** 2, 0) / (v.length || 1)) || 1;
    return { m, s: sd };
  };
  return {
    pitch: stat("pitch"),
    centroid: stat("centroid"),
    rms: { m: snaps.reduce((s, x) => s + x.rms, 0) / (snaps.length || 1) },
  };
}

// Score a snapshot against a profile, 0..1 (higher = more like this voice).
export function matchScore(f, p) {
  if (!f || !p) return 0;
  let ok = 0, tot = 0;
  if (f.pitch > 0 && p.pitch.m > 0) { tot++; if (Math.abs(f.pitch - p.pitch.m) <= 2.6 * p.pitch.s) ok++; }
  if (p.centroid && p.centroid.m > 0) { tot++; if (Math.abs(f.centroid - p.centroid.m) <= 2.6 * p.centroid.s) ok++; }
  // Loudness floor: a faint far-away voice at the mic is likely not the person enrolled up close.
  if (p.rms && p.rms.m > 0) { tot++; if (f.rms >= 0.35 * p.rms.m) ok++; }
  return tot ? ok / tot : 0;
}

// Classify a snapshot against a MAP {id: profile}. Returns the best {id, score} and the runner-up gap.
// This is the seam the "environment people" feature and a future ONNX classifier both plug into.
export function classify(f, profiles) {
  let best = { id: null, score: 0 }, second = 0;
  for (const [id, p] of Object.entries(profiles || {})) {
    const s = matchScore(f, p);
    if (s > best.score) { second = best.score; best = { id, score: s }; }
    else if (s > second) { second = s; }
  }
  return { id: best.id, score: best.score, gap: best.score - second };
}

// Energy segmenter (pure): feed per-frame rms, get "speech started / ended" transitions. This replaces the
// server-side VAD FOR THE PURPOSE OF THE FINGERPRINT — on the LiveKit engine the browser has no VAD signal,
// and running our own tiny energy gate here keeps the whole cost client-side.
export class Segmenter {
  constructor(opts = {}) {
    this.on = opts.onFloor ?? 0.02;     // rms to start counting speech
    this.off = opts.offFloor ?? 0.012;  // rms below which we count silence
    this.startFrames = opts.startFrames ?? 3;   // consecutive loud frames to open a segment
    this.hangFrames = opts.hangFrames ?? 10;    // consecutive quiet frames to close it
    this._loud = 0; this._quiet = 0; this._in = false;
  }
  // Returns "start" | "end" | null for this frame.
  feed(rms) {
    if (!this._in) {
      if (rms >= this.on) { if (++this._loud >= this.startFrames) { this._in = true; this._loud = 0; this._quiet = 0; return "start"; } }
      else this._loud = 0;
      return null;
    }
    if (rms < this.off) { if (++this._quiet >= this.hangFrames) { this._in = false; this._quiet = 0; return "end"; } }
    else this._quiet = 0;
    return null;
  }
  active() { return this._in; }
  reset() { this._loud = 0; this._quiet = 0; this._in = false; }
}

// ---- thin AnalyserNode adapter (browser only; not exercised by the Node core test) ----------

// SpeakerID drives the pure core off a live mic AnalyserNode. It self-segments, auto-enrolls the operator's
// first speech segments, classifies every later segment, and hands each verdict to `onUtterance`. It NEVER
// gates or blocks anything — F0 is measurement. The caller (session-lk.js) logs the verdict to observability.
export class SpeakerID {
  // getAnalyser: () => AnalyserNode|null   ·   getSampleRate: () => number
  constructor(getAnalyser, getSampleRate, opts = {}) {
    this.getAnalyser = getAnalyser;
    this.getSampleRate = getSampleRate;
    this.minEnroll = opts.minEnroll ?? 4;        // operator segments to finish auto-enrollment
    this.operatorThreshold = opts.operatorThreshold ?? 0.5;
    this.onUtterance = opts.onUtterance || (() => {});
    this.onState = opts.onState || (() => {});
    this.isEnrollable = opts.isEnrollable || (() => true);   // F2 will gate this to DIRECTED turns
    this.profiles = opts.profiles || {};         // {operator: profile, "known:<id>": profile, ...}
    this._seg = new Segmenter(opts);
    this._ring = [];                             // per-frame features of the current segment
    this._enroll = [];                           // operator enrollment snapshots
    this._td = null; this._fd = null;
    this._tick = 0;
  }

  enrolled() { return !!this.profiles.operator; }

  // Call from a render loop while the mic is live. Cheap on silence; the heavy pitch pass runs on speech frames.
  tick() {
    const an = this.getAnalyser && this.getAnalyser();
    if (!an) return;
    if (++this._tick % 2) return;                // throttle to ~every other frame
    if (!this._td || this._td.length !== an.fftSize) {
      this._td = new Float32Array(an.fftSize);
      this._fd = new Uint8Array(an.frequencyBinCount);
    }
    an.getFloatTimeDomainData(this._td);
    const rms = rmsOf(this._td);
    const ev = this._seg.feed(rms);
    if (ev === "start") { this._ring = []; }
    if (this._seg.active() && rms >= 0.012) {
      an.getByteFrequencyData(this._fd);
      this._ring.push(frameFeatures(this._td, this._fd, this.getSampleRate()));
      if (this._ring.length > 40) this._ring.shift();
    }
    if (ev === "end") this._closeSegment();
  }

  _closeSegment() {
    const f = snapshot(this._ring);
    this._ring = [];
    if (!f) return;                              // too little voiced audio to describe
    if (!this.profiles.operator) {               // ENROLLMENT (auto, F0): learn the operator's first segments
      if (!this.isEnrollable()) return;
      this._enroll.push(f);
      this.onState({ enrolling: true, count: this._enroll.length, need: this.minEnroll });
      if (this._enroll.length >= this.minEnroll) {
        this.profiles.operator = buildProfile(this._enroll);
        this.onState({ enrolling: false, enrolled: true });
      }
      this.onUtterance({ label: "enroll", score: 0, features: f });
      return;
    }
    const best = classify(f, this.profiles);
    let label;
    if (best.id === "operator" && best.score >= this.operatorThreshold) label = "operator";
    else if (best.id && best.id !== "operator" && best.score >= this.operatorThreshold) label = best.id;
    else label = "other";
    // ALWAYS report the operator's own score too, so the shadow log measures operator separability directly.
    const opScore = matchScore(f, this.profiles.operator);
    this.onUtterance({ label, score: best.score, opScore, matched: best.id, gap: best.gap, features: f });
  }

  addProfile(id, profile) { this.profiles[id] = profile; }
  reset() { this._enroll = []; this._ring = []; this._seg.reset(); this.profiles = {}; }
}
