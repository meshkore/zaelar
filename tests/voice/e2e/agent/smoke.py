"""Smoke test of the voice loop: the tester joins zaelar's room, hears the greeting, says one line, and
transcribes zaelar's reply. Proves the whole LiveKit voice loop end-to-end (and validates INI-012).

Run (with zaelar up on the LiveKit engine):  ./.venv/bin/python -m tester.smoke
"""
from __future__ import annotations

import asyncio
import json
import urllib.request

from livekit.agents.utils import http_context

from . import config
from .interlocutor import providers
from .interlocutor.voice_link import VoiceLink


def _log(kind: str, label: str, **f) -> None:
    txt = str(f.get("text", ""))[:180]
    print(f"  ·[{kind}/{label}] {txt}".rstrip())


async def main() -> None:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{config.ZAELAR_URL}/api/token?identity={config.TESTER_IDENTITY}"
    tok = json.loads(urllib.request.urlopen(url, timeout=10).read())
    print(f"token OK · livekit={tok['url']} room={tok['room']} · tts={config.TESTER_TTS} stt={config.TESTER_STT}")

    # LiveKit plugins (cartesia/deepgram) need an http session context when used outside the agent worker.
    async with http_context.open():
        tts, stt = providers.build_tts(), providers.build_stt()
        link = VoiceLink(tts, stt, on_event=_log, wav_path=str(config.RUNS_DIR / "smoke_zaelar.wav"))
        await link.connect(tok["url"], tok["token"])

        print("=== esperando saludo de zaelar (30s) ===")
        g = await link.wait_reply(timeout=30)
        print(f"GREETING → {g}")

        print("=== el tester habla ===")
        await link.say("Hi zaelar, can you hear me clearly? Answer in one short sentence.")
        r = await link.wait_reply(timeout=30)
        print(f"REPLY → text={r.get('text')!r} · latency_ms={r.get('latency_ms')} · timeout={r.get('timeout')}")

        await link.aclose()
    print("=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
