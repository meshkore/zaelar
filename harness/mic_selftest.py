#!/usr/bin/env python3
"""
HEADLESS mic self-test — proves the server's mic→STT path WITHOUT a browser or a human talking.

It is the browser's voice client, in Python: connects to zaelar's /api/offer over real WebRTC, pushes a WAV of
real speech (generated with macOS `say`) as the mic track, optionally signals turn start/stop over the data
channel exactly like the browser, then reads /api/debug to report:

  - did inbound audio reach the server with energy?   (AudioProbe rms > 0)
  - did Deepgram transcribe it?                        (transcript events)
  - did the brain reply / TTS start?                   (end-to-end)

This isolates the bug: if rms>0 and a transcript appears here, the SERVER pipeline is fine and the fault is the
BROWSER capture; if not, the fault is server-side and this is where to fix it.

Run:  ./.venv/bin/python harness/mic_selftest.py
Env:  ZAELAR_URL (default http://localhost:43917) · SAY_VOICE (default Monica) · PHRASE · SECS (default 14)
"""
import asyncio
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = os.getenv("ZAELAR_URL", "http://localhost:43917").rstrip("/")
SECS = float(os.getenv("SECS", "14"))
PHRASE = os.getenv("PHRASE", "Hola, ¿me oyes bien? Esto es una prueba de micrófono. Uno, dos, tres, cuatro.")
SAY_VOICE = os.getenv("SAY_VOICE", "Monica")   # a Spanish macOS voice
WAV = os.path.join(HERE, "_selftest_speech.wav")


def make_speech_wav() -> str:
    """Synthesize a real Spanish utterance with macOS `say`, transcoded to 48 kHz mono WAV for aiortc."""
    aiff = WAV.replace(".wav", ".aiff")
    subprocess.run(["say", "-v", SAY_VOICE, "-o", aiff, PHRASE], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff, "-ar", "48000", "-ac", "1", WAV], check=True)
    os.remove(aiff)
    return WAV


def post_json(path: str, payload: dict) -> dict:
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def get_json(path: str) -> dict:
    with urllib.request.urlopen(URL + path, timeout=20) as r:
        return json.loads(r.read().decode())


async def main() -> int:
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaPlayer

    print(f"▶ mic self-test → {URL}")
    print(f"  phrase: “{PHRASE}”  (voice={SAY_VOICE})")
    make_speech_wav()

    pc = RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]))
    player = MediaPlayer(WAV)                     # loops? no — plays once (~4-5s); connection stays up SECS
    pc.addTrack(player.audio)
    pc.addTransceiver("audio", direction="recvonly")   # also receive the bot's audio (so SDP matches the browser)
    dc = pc.createDataChannel("vala-turn")

    @dc.on("open")
    def _open():
        # Tell the server a turn is happening, exactly like assistant.html (RTVI client-message → vala-turn).
        async def signal():
            await asyncio.sleep(0.4)
            dc.send(json.dumps({"label": "rtvi-ai", "type": "client-message", "id": "vt1",
                                "data": {"t": "vala-turn", "d": {"ev": "start"}}}))
            await asyncio.sleep(6.0)
            dc.send(json.dumps({"label": "rtvi-ai", "type": "client-message", "id": "vt2",
                                "data": {"t": "vala-turn", "d": {"ev": "stop"}}}))
        asyncio.ensure_future(signal())

    await pc.setLocalDescription(await pc.createOffer())
    # wait for ICE gathering to complete (mirrors the browser's iceDone)
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.1)

    ans = post_json("/api/offer", {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    print(f"  connected · pushing {SECS:.0f}s of audio…")

    await asyncio.sleep(SECS)
    try:
        post_json("/api/hangup", {})
    except Exception:
        pass
    await pc.close()

    # ---- read what the server saw ----
    dbg = get_json("/api/debug")
    evs = dbg.get("events", [])
    audio = [e for e in evs if e.get("kind") == "audio" and "rms" in e]
    rmss = [e["rms"] for e in audio]
    transcripts = [e for e in evs if e.get("kind") == "transcript"]
    finals = [e for e in transcripts if e.get("label") == "transcript"]
    interims = [e for e in transcripts if e.get("label") == "interim"]
    brain = [e for e in evs if e.get("kind") in ("brain", "assistant", "llm")]
    errors = [e for e in evs if e.get("kind") == "error"]
    boot = next((e for e in evs if e.get("kind") == "boot"), None)

    print("\n──────── RESULT ────────")
    if boot:
        print(f"boot: stt={boot.get('stt')} · filter={boot.get('audio_filter')} · echo={boot.get('echo_suppress')}")
    print(f"audio events: {len(audio)} · rms max={max(rmss) if rmss else 0} · rms mean={round(sum(rmss)/len(rmss),4) if rmss else 0}")
    print(f"transcripts: {len(finals)} final · {len(interims)} interim")
    for t in (interims[:3] + finals):
        print(f"    [{t.get('label')}] “{t.get('text','')}”")
    print(f"brain/llm/assistant events: {len(brain)} · errors: {len(errors)}")
    for e in errors[:3]:
        print(f"    ERROR: {e.get('label')}")

    if os.getenv("TIMELINE", "0") == "1":
        print("\n──────── TIMELINE ────────")
        for e in evs:
            print(f"  {e.get('rel_ms',0)/1000:6.1f}s  {e.get('kind'):10} {e.get('label','')[:70]}  {('“'+e.get('text','')[:50]+'”') if e.get('text') else ''}")

    heard = bool(rmss) and max(rmss) > 0.01
    transcribed = len(finals) > 0 or len(interims) > 0
    print("\n──────── VERDICT ────────")
    print(f"  mic audio reached server with energy: {'✅ YES' if heard else '❌ NO (rms~0)'}")
    print(f"  server transcribed the speech:        {'✅ YES' if transcribed else '❌ NO'}")
    if heard and transcribed:
        print("  → SERVER PIPELINE IS HEALTHY. The fault is the BROWSER capture, not the server.")
    elif heard and not transcribed:
        print("  → audio arrives but STT produced nothing → STT layer (filter/lang/key).")
    else:
        print("  → audio did NOT arrive with energy → transport/filter zeroing it server-side.")
    return 0 if (heard and transcribed) else 2


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"self-test failed to run: {e}")
        sys.exit(1)
