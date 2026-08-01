#!/usr/bin/env python3
"""
HEADLESS mic self-test — proves the server's mic→STT path WITHOUT a browser or a human talking.

It is the browser's voice client, in Python: requests a fresh `/api/token`, joins the real LiveKit room, publishes
a SOURCE_MICROPHONE track containing speech generated with macOS `say`, then reads `/api/debug` to report:

  - did the generated source contain energy?           (local WAV RMS)
  - did inbound audio reach the server?                (server VAD edge)
  - did Deepgram transcribe it?                        (transcript events)
  - did the brain reply / TTS start?                   (end-to-end)

This isolates the bug: if rms>0 and a transcript appears here, the SERVER pipeline is fine and the fault is the
BROWSER capture; if not, the fault is server-side and this is where to fix it.

Run:  ./.venv/bin/python -m tests.voice.e2e.mic.mic_selftest
Env:  ZAELAR_URL (default http://localhost:43917) · SAY_VOICE (default Monica) · PHRASE · SECS (default 14)
"""
import asyncio
from array import array
import json
import os
import subprocess
import sys
import time
import urllib.request
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
URL = os.getenv("ZAELAR_URL", "http://localhost:43917").rstrip("/")
SECS = float(os.getenv("SECS", "14"))
PHRASE = os.getenv("PHRASE", "Hola, ¿me oyes bien? Esto es una prueba de micrófono. Uno, dos, tres, cuatro.")
SAY_VOICE = os.getenv("SAY_VOICE", "Monica")   # a Spanish macOS voice
WAV = os.path.join(HERE, "_selftest_speech.wav")


def make_speech_wav() -> str:
    """Synthesize a real Spanish utterance as 48 kHz mono signed-16 PCM for LiveKit."""
    aiff = WAV.replace(".wav", ".aiff")
    subprocess.run(["say", "-v", SAY_VOICE, "-o", aiff, PHRASE], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff, "-ar", "48000", "-ac", "1",
                    "-c:a", "pcm_s16le", WAV], check=True)
    os.remove(aiff)
    return WAV


def get_json(path: str) -> dict:
    with urllib.request.urlopen(URL + path, timeout=20) as r:
        return json.loads(r.read().decode())


async def main() -> int:
    from livekit import rtc

    print(f"▶ mic self-test → {URL}")
    print(f"  phrase: “{PHRASE}”  (voice={SAY_VOICE})")
    make_speech_wav()
    started_ms = time.time() * 1000
    auth = get_json("/api/token?identity=mic-selftest&name=MicSelfTest")
    room = rtc.Room()
    source = rtc.AudioSource(48_000, 1, queue_size_ms=120_000)
    track = rtc.LocalAudioTrack.create_audio_track("mic-selftest", source)
    await room.connect(auth["url"], auth["token"])
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    print(f"  connected · room={auth.get('room')} · waiting for agent kickoff…")
    await asyncio.sleep(5)

    samples = array("h")
    with wave.open(WAV, "rb") as wav:
        if wav.getnchannels() != 1 or wav.getframerate() != 48_000 or wav.getsampwidth() != 2:
            raise RuntimeError("generated WAV is not 48 kHz mono pcm_s16le")
        raw = wav.readframes(wav.getnframes())
        samples.frombytes(raw)
    local_rms = (sum((sample / 32768.0) ** 2 for sample in samples) / len(samples)) ** 0.5 if samples else 0.0
    print(f"  publishing {len(samples) / 48_000:.1f}s microphone audio · local rms={local_rms:.4f}")
    with wave.open(WAV, "rb") as wav:
        while pcm := wav.readframes(480):  # 10 ms frames, same cadence/format as a browser mic
            frame = rtc.AudioFrame(data=pcm, sample_rate=48_000, num_channels=1,
                                   samples_per_channel=len(pcm) // 2)
            await source.capture_frame(frame)
    await source.wait_for_playout()
    print(f"  audio sent · observing pipeline for up to {SECS:.0f}s…")
    await asyncio.sleep(SECS)
    await room.disconnect()

    # ---- read what the server saw ----
    dbg = get_json("/api/debug")
    evs = [event for event in dbg.get("events", []) if float(event.get("t_ms") or 0) >= started_ms]
    vad = [event for event in evs if event.get("kind") == "vad"]
    finals = [event for event in evs if event.get("kind") == "transcript" and event.get("role") == "user"]
    interims = [event for event in evs if event.get("kind") == "interim" and event.get("role") == "user"]
    assistant = [event for event in evs if event.get("kind") == "transcript" and event.get("role") == "assistant"]
    brain = [e for e in evs if e.get("kind") in ("brain", "assistant", "llm")]
    errors = [e for e in evs if e.get("kind") == "error"]
    boot = next((e for e in evs if e.get("kind") == "boot"), None)

    print("\n──────── RESULT ────────")
    if boot:
        print(f"boot: stt={boot.get('stt')} · filter={boot.get('audio_filter')} · echo={boot.get('echo_suppress')}")
    print(f"local source rms: {local_rms:.4f} · server VAD edges: {len(vad)}")
    print(f"transcripts: {len(finals)} final · {len(interims)} interim")
    for t in (interims[:3] + finals):
        print(f"    [{t.get('label')}] “{t.get('text','')}”")
    for event in assistant[-1:]:
        print(f"    [zaelar] “{event.get('text', '')}”")
    print(f"brain/llm/assistant events: {len(brain)} · errors: {len(errors)}")
    for e in errors[:3]:
        print(f"    ERROR: {e.get('label')}")

    if os.getenv("TIMELINE", "0") == "1":
        print("\n──────── TIMELINE ────────")
        for e in evs:
            print(f"  {e.get('rel_ms',0)/1000:6.1f}s  {e.get('kind'):10} {e.get('label','')[:70]}  {('“'+e.get('text','')[:50]+'”') if e.get('text') else ''}")

    energetic = local_rms > 0.01
    heard = bool(vad) or bool(finals) or bool(interims)
    transcribed = len(finals) > 0 or len(interims) > 0
    print("\n──────── VERDICT ────────")
    print(f"  generated mic source has energy:      {'✅ YES' if energetic else '❌ NO (local rms~0)'}")
    print(f"  mic audio reached server/VAD:         {'✅ YES' if heard else '❌ NO'}")
    print(f"  server transcribed the speech:        {'✅ YES' if transcribed else '❌ NO'}")
    if energetic and heard and transcribed:
        print("  → SERVER PIPELINE IS HEALTHY. The fault is the BROWSER capture, not the server.")
    elif heard and not transcribed:
        print("  → audio arrives but STT produced nothing → STT layer (filter/lang/key).")
    else:
        print("  → audio did NOT arrive with energy → transport/filter zeroing it server-side.")
    return 0 if (energetic and heard and transcribed) else 2


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"self-test failed to run: {e}")
        sys.exit(1)
