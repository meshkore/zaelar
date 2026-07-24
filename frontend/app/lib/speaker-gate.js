// SpeakerGate — browser-side "owner voice" gate (iteration 1, no key, no model download).
//
// Sits between the mic VAD and the turn signal: it LEARNS the owner's voice in the first speech segments
// (enrollment) and then only lets segments that match the owner open a turn to the orchestrator — so kids /
// background voices / "Alexa" across the room don't talk to the assistant.
//
// It's an acoustic fingerprint (pitch via autocorrelation + spectral centroid + loudness), which separates
// different timbres (adult vs child, you vs someone else) reasonably well. For rock-solid speaker identity,
// swap verify()/enroll() for Picovoice Eagle or an ONNX speaker-embedding behind the SAME interface.
//
// Usage:
//   const gate = new SpeakerGate(analyserNode, audioCtx.sampleRate);
//   // each animation frame while the mic is live:  gate.update();
//   // at VAD speech start:  const d = gate.decide();  if(d.pass) sendTurn("start");
//   gate.reset();  gate.enabled = true|false;  gate.onState = (s)=>{...}

export class SpeakerGate {
  constructor(analyser, sampleRate, opts = {}) {
    this.an = analyser;                 // an AnalyserNode on the mic (fftSize >= 2048 for pitch)
    this.sr = sampleRate || 48000;
    this.enabled = opts.enabled !== false;
    this.minEnroll = opts.minEnroll || 5;      // owner speech snapshots needed to finish enrollment
    this.tol = opts.tol || { pitch: 2.6, centroid: 2.6 };   // std multipliers (lenient by default)
    this.onState = opts.onState || (() => {});
    this._td = new Float32Array(analyser.fftSize);
    this._fd = new Uint8Array(analyser.frequencyBinCount);
    this._ring = [];                    // rolling recent frame features
    this._enroll = [];                  // collected owner snapshots
    this._profile = null;               // {pitch:{m,s}, centroid:{m,s}, rms:{m}}
    this._tick = 0;
  }

  reset() { this._ring = []; this._enroll = []; this._profile = null; this._emit(); }

  // ---- per-frame feature capture (call from the render loop) ----
  update() {
    if (++this._tick % 2) return;       // throttle to ~every other frame
    this.an.getFloatTimeDomainData(this._td);
    const rms = this._rms(this._td);
    if (rms < 0.012) return;            // ignore near-silence frames
    this.an.getByteFrequencyData(this._fd);
    const f = { pitch: this._pitch(this._td), centroid: this._centroid(this._fd), rms };
    this._ring.push(f);
    if (this._ring.length > 24) this._ring.shift();
  }

  // ---- decision at speech start ----
  decide() {
    if (!this.enabled) return { pass: true, enrolling: false, reason: "off" };
    const f = this._snapshot();
    if (!f) return { pass: true, enrolling: !this._profile, reason: "no-audio" };  // don't block if unsure
    if (!this._profile) {               // ENROLLMENT: collect the owner's first segments (always pass)
      this._enroll.push(f);
      if (this._enroll.length >= this.minEnroll) this._finalize();
      this._emit();
      return { pass: true, enrolling: !this._profile, reason: "enroll", count: this._enroll.length };
    }
    const score = this._match(f);       // 0..1, higher = more like the owner
    return { pass: score >= 0.5, enrolling: false, score, reason: score >= 0.5 ? "owner" : "other" };
  }

  retrain() { this.reset(); }
  enrolled() { return !!this._profile; }

  // ---- internals ----
  _snapshot() {
    if (this._ring.length < 3) return null;
    const n = this._ring.length, avg = k => this._ring.reduce((s, x) => s + x[k], 0) / n;
    return { pitch: this._median("pitch"), centroid: avg("centroid"), rms: avg("rms") };
  }
  _median(k) { const a = this._ring.map(x => x[k]).filter(v => v > 0).sort((x, y) => x - y);
    return a.length ? a[Math.floor(a.length / 2)] : 0; }

  _finalize() {
    const ms = (k) => { const v = this._enroll.map(x => x[k]).filter(x => x > 0);
      const m = v.reduce((s, x) => s + x, 0) / (v.length || 1);
      const s = Math.sqrt(v.reduce((a, x) => a + (x - m) ** 2, 0) / (v.length || 1)) || 1;
      return { m, s }; };
    this._profile = { pitch: ms("pitch"), centroid: ms("centroid"),
                      rms: { m: this._enroll.reduce((s, x) => s + x.rms, 0) / this._enroll.length } };
  }

  _match(f) {
    const p = this._profile; let ok = 0, tot = 0;
    if (f.pitch > 0 && p.pitch.m > 0) { tot++; if (Math.abs(f.pitch - p.pitch.m) <= this.tol.pitch * p.pitch.s) ok++; }
    tot++; if (Math.abs(f.centroid - p.centroid.m) <= this.tol.centroid * p.centroid.s) ok++;
    // loudness floor: a faint far-away voice is likely not the owner at the mic
    tot++; if (f.rms >= 0.35 * p.rms.m) ok++;
    return tot ? ok / tot : 1;
  }

  _emit() { this.onState({ enrolled: !!this._profile, enrollCount: this._enroll.length, need: this.minEnroll }); }

  _rms(td) { let s = 0; for (let i = 0; i < td.length; i++) s += td[i] * td[i]; return Math.sqrt(s / td.length); }

  _centroid(fd) { let num = 0, den = 0; const hzPerBin = this.sr / (fd.length * 2);
    for (let i = 0; i < fd.length; i++) { num += i * hzPerBin * fd[i]; den += fd[i]; } return den ? num / den : 0; }

  // autocorrelation pitch (fundamental freq) over the voice range 70–400 Hz
  _pitch(td) {
    const sr = this.sr, minLag = Math.floor(sr / 400), maxLag = Math.floor(sr / 70);
    let best = -1, bestVal = 0, prev = 0, going = false;
    for (let lag = minLag; lag <= maxLag && lag < td.length; lag++) {
      let sum = 0; for (let i = 0; i < td.length - lag; i++) sum += td[i] * td[i + lag];
      if (sum > prev) going = true;
      if (going && sum < prev && prev > bestVal) { bestVal = prev; best = lag - 1; }
      prev = sum;
    }
    return best > 0 ? sr / best : 0;
  }
}
