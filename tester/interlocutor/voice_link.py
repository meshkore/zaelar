"""VoiceLink — the tester as a native LiveKit participant in zaelar's room.

Speaks to zaelar by publishing TTS audio (rtc.AudioSource) and listens by subscribing to zaelar's audio track
(rtc.AudioStream → STT). Also sends chat/paste text over the data channel. Times zaelar's response latency as
[tester stops speaking] → [zaelar's first audible frame] — isolated to zaelar's pipeline (STT+brain+TTS TTFB),
so it's attributable to zaelar, not to the tester's own thinking. Optionally captures zaelar's audio to WAV for
the voice-vs-transcript diagnostic (the sim candidate's most valuable trick).
"""
from __future__ import annotations

import asyncio
import json
import time
import wave

import numpy as np
from livekit import rtc
from livekit.agents import stt as _stt


class VoiceLink:
    def __init__(self, tts, stt, on_event=None, wav_path: str | None = None):
        self._tts = tts
        self._stt = stt
        self._on = on_event or (lambda *a, **k: None)
        self._room = rtc.Room()
        self._source: rtc.AudioSource | None = None
        self._transcripts: asyncio.Queue[str] = asyncio.Queue()
        self._say_end = 0.0            # monotonic ts of the tester's last spoken frame
        self._bot_first_audio = None   # monotonic ts of zaelar's first audible frame in the current reply window
        self._bot_speaking = False
        self._listening = False
        self._wav_path = wav_path
        self._wav = None

    async def connect(self, url: str, token: str) -> None:
        self._room.on("track_subscribed", self._on_track)
        await self._room.connect(url, token)
        # Big queue so a full utterance (pushed faster than real-time) is never dropped by a small buffer — the
        # 1000ms default silently truncated the tester's speech to ~1s, so zaelar only heard the first word.
        self._source = rtc.AudioSource(self._tts.sample_rate, self._tts.num_channels, queue_size_ms=120_000)
        track = rtc.LocalAudioTrack.create_audio_track("tester-voice", self._source)
        # CRITICAL: source=MICROPHONE. zaelar's AgentSession only feeds MICROPHONE-source tracks into its STT/VAD;
        # an UNKNOWN-source track is published + reaches the server but the agent never listens to it.
        opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self._room.local_participant.publish_track(track, opts)
        self._on("link", "connected", text=f"room={self._room.name}")

    # --- listening (zaelar → tester) --------------------------------------------------------------------------
    def _on_track(self, track, publication, participant):
        try:
            is_audio = track.kind == rtc.TrackKind.KIND_AUDIO
        except Exception:
            is_audio = "AUDIO" in str(getattr(track, "kind", ""))
        if is_audio and not self._listening:
            self._listening = True
            asyncio.create_task(self._listen(track))

    async def _listen(self, track) -> None:
        stream = rtc.AudioStream(track)
        sst = self._stt.stream()
        asyncio.create_task(self._read_stt(sst))
        silent_ms = 0
        async for ev in stream:
            f = ev.frame
            a = np.frombuffer(f.data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt((a * a).mean())) if a.size else 0.0
            frame_ms = (f.samples_per_channel / f.sample_rate) * 1000 if f.sample_rate else 20
            if rms > 0.01:
                silent_ms = 0
                if self._bot_first_audio is None:
                    self._bot_first_audio = time.monotonic()
                if not self._bot_speaking:
                    self._bot_speaking = True
                    self._on("bot_speech", "EMPIEZA")
            else:
                silent_ms += frame_ms
                if self._bot_speaking and silent_ms > 700:
                    self._bot_speaking = False
                    self._on("bot_speech", "PARA")
            try:
                sst.push_frame(f)
            except Exception:
                pass
            self._write_wav(f)
        try:
            await sst.aclose()
        except Exception:
            pass

    async def _read_stt(self, sst) -> None:
        try:
            async for ev in sst:
                if ev.type == _stt.SpeechEventType.FINAL_TRANSCRIPT:
                    txt = (ev.alternatives[0].text if ev.alternatives else "").strip()
                    if txt:
                        self._on("transcript", "zaelar (heard by tester)", text=txt, role="assistant")
                        await self._transcripts.put(txt)
        except Exception as e:
            self._on("error", "tester STT stream", text=f"{type(e).__name__}: {e}")

    def _write_wav(self, f) -> None:
        if not self._wav_path:
            return
        try:
            if self._wav is None:
                self._wav = wave.open(self._wav_path, "wb")
                self._wav.setnchannels(f.num_channels)
                self._wav.setsampwidth(2)
                self._wav.setframerate(f.sample_rate)
            self._wav.writeframes(bytes(f.data))
        except Exception:
            pass

    # --- speaking (tester → zaelar) ---------------------------------------------------------------------------
    async def say(self, text: str) -> dict:
        self._on("say", "tester", text=text, role="user")
        self._bot_first_audio = None                 # open a fresh reply window
        while not self._transcripts.empty():         # drop stale transcripts from the previous turn
            self._transcripts.get_nowait()
        t0 = time.monotonic()
        stream = self._tts.synthesize(text)
        async for sa in stream:
            await self._source.capture_frame(sa.frame)
        await self._source.wait_for_playout()
        self._say_end = time.monotonic()
        # Open the reply window HERE (not at say() start): only zaelar audio arriving AFTER the tester stops
        # counts as the reply. Otherwise leftover/overlapping frames from a prior turn arrive mid-speech and make
        # (first_audio - say_end) negative — the "-5275ms" the judge flagged. (bug fix 2026-07-07)
        self._bot_first_audio = None
        self._on("user_speech", "PARA", text=f"spoke {round(self._say_end - t0, 2)}s")
        return {"said": text, "spoke_s": round(self._say_end - t0, 2)}

    async def wait_reply(self, timeout: float = 25.0, quiet_after: float = 1.6) -> dict:
        """Collect zaelar's transcript until a quiet gap. Returns text + response latency (from the tester's last
        spoken frame to zaelar's first audible frame)."""
        chunks: list[str] = []
        try:
            chunks.append(await asyncio.wait_for(self._transcripts.get(), timeout))
        except asyncio.TimeoutError:
            return {"text": "", "timeout": True, "latency_ms": None}
        while True:
            try:
                chunks.append(await asyncio.wait_for(self._transcripts.get(), quiet_after))
            except asyncio.TimeoutError:
                break
        lat = None
        if self._bot_first_audio and self._say_end:
            lat = round((self._bot_first_audio - self._say_end) * 1000)
            if lat < 0:
                lat = None   # measurement artifact (overlapping audio) — not a real negative latency
        text = " ".join(chunks).strip()
        self._on("zaelar_turn", "reply", text=text, role="assistant", latency_ms=lat)
        return {"text": text, "timeout": False, "latency_ms": lat}

    # --- text channel (chat / paste) --------------------------------------------------------------------------
    async def send_text(self, text: str, *, kind: str = "chat") -> None:
        # Open a reply window like say() does, so wait_reply can MEASURE latency for text channels too
        # (text sent → zaelar's first audible reply). Without this, chat/paste had no latency → the judge
        # scored latencia=1 in EVERY text report. (fix 2026-07-07)
        while not self._transcripts.empty():
            self._transcripts.get_nowait()
        self._bot_first_audio = None
        payload = json.dumps({"t": "zaelar-text", "text": text}).encode("utf-8")
        await self._room.local_participant.publish_data(payload, reliable=True, topic="zaelar-text")
        self._say_end = time.monotonic()   # reference instant for the text→reply latency
        self._on(kind, "tester → zaelar (data)", text=text, role="user")

    async def aclose(self) -> None:
        try:
            if self._wav:
                self._wav.close()
        except Exception:
            pass
        try:
            await self._room.disconnect()
        except Exception:
            pass
