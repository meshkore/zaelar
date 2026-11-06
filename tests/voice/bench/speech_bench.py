"""The speech bench — every STT and TTS provider we can build, over FIXED phrases, in numbers (V2-856).

    ./.venv/bin/python -m tests.voice.bench.speech_bench [--only deepgram,cartesia] [--lang es,en]

STT: the same fixed audio (macOS `say`, written once to `tests/voice/bench/_audio/`, gitignored) to each recogniser → word error
rate against the phrase and seconds. TTS: each synthesiser speaks the phrase → seconds to the first audio, seconds in
all, seconds of audio, and the ROUND TRIP — what the reference recogniser hears back from it (WER), which is the
intelligibility number. FAILOVER: the selected TTS built with its key blanked must hand the voice to the table's
stand-in. Real providers with the operator's keys (the credential store); a provider with no key is a row that says
so, never a crash. The report lands in `tests/runs/speech-bench-<stamp>.json`.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
import wave
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
AUDIO = Path(__file__).resolve().parent / "_audio"
#: (lang, macOS voice, phrase) — numbers, a time, a name and a noun the gazetteer does not hold
PHRASES = (
    ("es", "Monica", "Recuérdame el jueves a las cinco y media que llame a Marta por el seguro del coche."),
    ("es", "Monica", "Busca tres monitores de veintisiete pulgadas por menos de cuatrocientos euros."),
    ("en", "Samantha", "Remind me on Thursday at five thirty to call Martha about the car insurance."),
    ("en", "Samantha", "Find three twenty seven inch monitors for less than four hundred dollars."),
)
#: the same phrase as a recogniser may WRITE it (digits, a time, a currency sign): a format is not a mishearing
WRITTEN = {
    PHRASES[0][2]: ("Recuérdame el jueves a las 5 y media que llame a Marta por el seguro del coche.",
                    "Recuérdame el jueves a las 5:30 que llame a Marta por el seguro del coche."),
    PHRASES[1][2]: ("Busca 3 monitores de 27 pulgadas por menos de 400 euros.",
                    "Busca tres monitores de 27 pulgadas por menos de 400 euros."),
    PHRASES[2][2]: ("Remind me on Thursday at 5 30 to call Martha about the car insurance.",),
    PHRASES[3][2]: ("Find 3 27 inch monitors for less than 400 dollars.", "Find three 27 inch monitors for less than 400 dollars."),
}
STT_LANG = {"es": "es", "en": "en"}


def words(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)


def heard(phrase: str, hyp: str) -> float:
    """The WER against the phrase OR any way of writing it (`WRITTEN`), whichever is lowest. Pure."""
    t = re.sub(r"[$]\s*(\d+)", r"\1 dollars", hyp)
    t = re.sub(r"€\s*(\d+)|(\d+)\s*€", lambda m: f"{m.group(1) or m.group(2)} euros", t)
    t = re.sub(r"(\d)[.:,](\d)", r"\1 \2", t)
    return min(wer(ref, t) for ref in (phrase, *WRITTEN.get(phrase, ())))


def wer(ref: str, hyp: str) -> float:
    """Word error rate, edit distance over the reference's words. Pure; 0.0 is a perfect hearing."""
    r, h = words(ref), words(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return round(prev[-1] / len(r), 3)


def fixed_audio(lang: str, voice: str, phrase: str) -> Path:
    """The phrase as 16 kHz mono PCM WAV, made once and kept: the same bytes every run is what makes it a bench."""
    AUDIO.mkdir(exist_ok=True)
    out = AUDIO / f"{lang}-{hashlib.sha1(phrase.encode()).hexdigest()[:8]}.wav"
    if out.exists():
        return out
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-o", str(aiff), phrase], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1",
                    "-c:a", "pcm_s16le", str(out)], check=True)
    aiff.unlink(missing_ok=True)
    return out


def _frame(path: Path):
    from livekit import rtc
    with wave.open(str(path), "rb") as w:
        data, sr, ch = w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
    return rtc.AudioFrame(data=data, sample_rate=sr, num_channels=ch, samples_per_channel=len(data) // (2 * ch))


async def _hear(stt, frame, lang: str) -> tuple[str, float]:
    """Batch when the provider offers it; STREAMING otherwise — a realtime model (Voxtral) and a VAD-wrapped local
    recogniser (whisper_local) only listen the way the voice uses them, frame by frame, and are measured that way."""
    t = time.time()
    if not getattr(getattr(stt, "capabilities", None), "streaming", False) or getattr(stt, "_bench_batch", False):
        ev = await stt.recognize(frame, language=STT_LANG[lang])
        alts = getattr(ev, "alternatives", None) or []
        return (alts[0].text if alts else ""), round(time.time() - t, 2)
    return await _hear_streaming(stt, frame, lang, t)


async def _hear_streaming(stt, frame, lang: str, t: float) -> tuple[str, float]:
    from livekit import rtc
    from livekit.agents import stt as S
    st = stt.stream()
    step = frame.sample_rate // 50                       # 20 ms frames, as the room delivers them
    raw = bytes(frame.data)
    silence = bytes(2 * step * frame.num_channels)

    async def feed():
        for i in range(0, frame.samples_per_channel, step):
            chunk = raw[2 * i * frame.num_channels: 2 * (i + step) * frame.num_channels]
            st.push_frame(rtc.AudioFrame(data=chunk, sample_rate=frame.sample_rate, num_channels=frame.num_channels,
                                         samples_per_channel=len(chunk) // (2 * frame.num_channels)))
            await asyncio.sleep(0.02)
        for _ in range(60):                              # 1.2 s of silence: the VAD closes the turn
            st.push_frame(rtc.AudioFrame(data=silence, sample_rate=frame.sample_rate, num_channels=frame.num_channels,
                                         samples_per_channel=step))
            await asyncio.sleep(0.02)
        st.end_input()

    task = asyncio.create_task(feed())
    finals: list[str] = []
    spoken_end = t + frame.samples_per_channel / frame.sample_rate
    last = None
    events = st.__aiter__()
    try:
        async with asyncio.timeout(40):
            while True:
                # once a final is in and the audio is over, 3 s with nothing new closes the hearing
                wait = 3.0 if (finals and task.done()) else 40.0
                try:
                    ev = await asyncio.wait_for(events.__anext__(), timeout=wait)
                except (StopAsyncIteration, TimeoutError):
                    break
                if ev.type == S.SpeechEventType.FINAL_TRANSCRIPT and ev.alternatives:
                    finals.append(ev.alternatives[0].text)
                    last = time.time()
    except TimeoutError:
        pass
    finally:
        task.cancel()
        await st.aclose()
    # the latency a person feels: from the end of the speech to the last final transcript
    return " ".join(x for x in finals if x).strip(), round(max(0.0, (last or time.time()) - spoken_end), 2)


async def _speak(tts, phrase: str) -> dict:
    from livekit import rtc
    t, first, frames = time.time(), None, []
    async with tts.synthesize(phrase) as stream:
        async for ev in stream:
            if first is None:
                first = time.time() - t
            frames.append(ev.frame)
    total = time.time() - t
    audio = rtc.combine_audio_frames(frames) if frames else None
    return {"ttfb_s": round(first or 0, 2), "total_s": round(total, 2), "frame": audio,
            "audio_s": round(audio.samples_per_channel / audio.sample_rate, 2) if audio else 0.0}


def _build(registry, name: str, lang: str, *, stt: bool = False):
    """Built UNDER the phrase's language: every provider reads it live from `ZAELAR_LANGUAGE` (voice, model, the STT's
    language), and a Spanish phrase spoken by an English-configured voice measures the setting, not the provider."""
    os.environ["ZAELAR_LANGUAGE"] = lang
    try:
        if stt:
            obj = registry.create(name, vad=_vad())
            obj._bench_batch = name == "deepgram"        # deepgram answers in batch; the others only stream
            return obj, ""
        return registry.create(name), ""
    except Exception as e:  # noqa: BLE001 — no key / no model: a row of the report
        return None, f"{type(e).__name__}: {e}"[:160]


_VAD: list = []


def _vad():
    if not _VAD:
        from livekit.plugins import silero
        _VAD.append(silero.VAD.load())
    return _VAD[0]


def failover_row() -> dict:
    """The selected TTS with its key blanked must leave the voice to the table's stand-in (`build_tts`)."""
    from voice.engine.core.config import SETTINGS
    from voice.engine.speech import tts as T
    primary = SETTINGS.tts_provider
    attr, env = f"{primary}_api_key", f"{primary.upper()}_API_KEY"
    if not (hasattr(SETTINGS, attr) or os.getenv(env)):
        return {"check": "tts failover", "ok": None, "why": f"«{primary}» has no key to blank (local provider)"}
    old, old_env = getattr(SETTINGS, attr, None), os.environ.pop(env, None)   # a plugin may read either
    if old is not None:
        object.__setattr__(SETTINGS, attr, "")
    try:
        T.build_tts()
        served = T.active_provider()
        return {"check": "tts failover", "primary": primary, "served": served, "ok": served != primary,
                "why": "" if served != primary else "no stand-in took the voice"}
    except Exception as e:  # noqa: BLE001
        return {"check": "tts failover", "primary": primary, "ok": False, "why": f"{type(e).__name__}: {e}"[:160]}
    finally:
        if old is not None:
            object.__setattr__(SETTINGS, attr, old)
        if old_env is not None:
            os.environ[env] = old_env


async def run(only: set[str], langs: set[str]) -> dict:
    from livekit.agents.utils import http_context
    from voice.engine.speech import stt as S, tts as T
    lang0 = os.environ.get("ZAELAR_LANGUAGE")
    http_context._ContextVar.set(http_context._new_session_ctx())
    phrases = [p for p in PHRASES if p[0] in langs]
    stt_rows, tts_rows = [], []
    try:
        ears: dict[str, object] = {}
        for name in S.available():
            if only and name not in only:
                continue
            for lang, voice, phrase in phrases:
                stt, err = _build(S.registry, name, lang, stt=True)
                if stt is None:
                    stt_rows.append({"provider": name, "lang": lang, "ok": None, "why": err})
                    print(f"stt {name:14s} {lang} not built: {err}")
                    continue
                try:
                    text, s = await _hear(stt, _frame(fixed_audio(lang, voice, phrase)), lang)
                    row = {"provider": name, "lang": lang, "wer": heard(phrase, text), "s": s, "heard": text, "ok": True}
                except Exception as e:  # noqa: BLE001
                    row = {"provider": name, "lang": lang, "ok": False, "why": f"{type(e).__name__}: {e}"[:160]}
                stt_rows.append(row)
                if row["ok"] and "ref" not in ears:
                    ears["ref"] = name          # the first recogniser that hears is the round trip's ear
                print(f"stt {name:14s} {lang} wer={row.get('wer', '-')!s:6s} {row.get('s', '-')!s:6s}s  {row.get('heard', row.get('why', ''))[:70]}", flush=True)
        ref = ears.get("ref")
        for name in T.available():
            if only and name not in only:
                continue
            for lang, _voice, phrase in phrases:
                tts, err = _build(T.registry, name, lang)
                if tts is None:
                    tts_rows.append({"provider": name, "lang": lang, "ok": None, "why": err})
                    print(f"tts {name:14s} {lang} not built: {err}")
                    continue
                try:
                    got = await _speak(tts, phrase)
                    row = {"provider": name, "lang": lang, **{k: v for k, v in got.items() if k != "frame"}, "ok": got["audio_s"] > 0}
                    if ref and got["frame"] is not None:
                        ear, _ = _build(S.registry, str(ref), lang, stt=True)
                        back, _ = await _hear(ear, got["frame"], lang)
                        row.update({"round_trip_wer": heard(phrase, back), "heard_back": back, "ear": ref})
                except Exception as e:  # noqa: BLE001
                    row = {"provider": name, "lang": lang, "ok": False, "why": f"{type(e).__name__}: {e}"[:160]}
                tts_rows.append(row)
                print(f"tts {name:14s} {lang} first={row.get('ttfb_s', '-')!s:5s}s all={row.get('total_s', '-')!s:5s}s "
                      f"audio={row.get('audio_s', '-')!s:5s}s rt-wer={row.get('round_trip_wer', '-')!s:5s} {row.get('why', '')}", flush=True)
    finally:
        await http_context._close_http_ctx()
        os.environ.pop("ZAELAR_LANGUAGE", None) if lang0 is None else os.environ.__setitem__("ZAELAR_LANGUAGE", lang0)
    return {"stt": stt_rows, "tts": tts_rows}


def summary(rep: dict) -> dict:
    """Per provider: mean WER (STT) or mean round-trip WER and first-audio seconds (TTS). Pure."""
    out: dict[str, dict] = {}
    for kind, key in (("stt", "wer"), ("tts", "round_trip_wer")):
        for r in rep.get(kind) or []:
            if not r.get("ok"):
                continue
            d = out.setdefault(f"{kind}:{r['provider']}", {"n": 0, key: 0.0, "s": 0.0})
            d["n"] += 1
            d[key] += float(r.get(key) or 0)
            d["s"] += float(r.get("s") if kind == "stt" else r.get("ttfb_s") or 0)
    for d in out.values():
        for k in list(d):
            if k != "n":
                d[k] = round(d[k] / d["n"], 3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", default="es,en")
    a = ap.parse_args()
    if not (shutil.which("say") and shutil.which("ffmpeg")):
        print("✗ the fixed audio needs macOS `say` and ffmpeg (or a kept tests/voice/bench/_audio/)")
    from search.health import _load_credentials
    _load_credentials()
    rep = asyncio.run(run({s for s in a.only.split(",") if s}, {s for s in a.lang.split(",") if s}))
    rep["failover"] = fo = failover_row()
    if fo.get("ok"):   # a stand-in that was CHOSEN but cannot speak is a mute voice, not a failover
        spoke = [r for r in rep["tts"] if r.get("provider") == fo["served"]]
        if not any(r.get("ok") for r in spoke):
            fo.update(ok=False, why=f"the stand-in «{fo['served']}» was chosen and cannot speak: "
                                    + (next((r.get("why") for r in spoke if r.get("why")), "") or "no row")[:120])
    print(f"failover: {rep['failover']}")
    rep["summary"] = summary(rep)
    rep["at"] = time.strftime("%Y-%m-%d %H:%M")
    out = ENGINE / "tests" / "runs" / f"speech-bench-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep["summary"], indent=1))
    print(f"report: {out}")
    bad = [r for r in rep["stt"] + rep["tts"] if r.get("ok") is False] + ([rep["failover"]] if rep["failover"].get("ok") is False else [])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
