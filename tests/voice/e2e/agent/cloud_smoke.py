"""CLOUD smoke of the voice loop — the same end-to-end LiveKit proof as smoke.py, but against a REAL
Fly demo machine instead of localhost. It bootstraps its OWN demo session on the cloud entry point
(my.zaelar.com), joins that session's LiveKit room as the tester, hears zaelar's greeting, says one
line, and transcribes the reply. This is the seed of the cloud testing profile: the tester carries its
own voice + ears + brain, so the ONLY cloud-specific bits are (a) bootstrapping a demo session and
(b) carrying ?s=<session> so my.zaelar.com's reverse-proxy routes /api/token to that session's machine.

Run (from engine/, no local zaelar needed — it targets the cloud):
    ./.venv/bin/python -m tests.voice.e2e.agent.cloud_smoke
Env knobs:
    TESTER_CLOUD_URL   (default https://my.zaelar.com)
    TESTER_DEMO_EMAIL  (default voice-tester@zaelar.dev)
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from livekit.agents.utils import http_context

from . import config
from .interlocutor import providers
from .interlocutor.voice_link import VoiceLink

CLOUD_URL = os.getenv("TESTER_CLOUD_URL", "https://my.zaelar.com").rstrip("/")
DEMO_EMAIL = os.getenv("TESTER_DEMO_EMAIL", "voice-tester@zaelar.dev")


# Cloudflare (in front of my.zaelar.com) 403s requests whose User-Agent looks like a bot — urllib's
# default "Python-urllib/3.x" is blocked, a browser UA passes. The tester is a legit client, so it
# presents a browser UA (verified: same request 403s with the urllib UA, 200s with this one).
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _post_json(url: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _log(kind: str, label: str, **f) -> None:
    print(f"  ·[{kind}/{label}] {str(f.get('text', ''))[:160]}".rstrip())


async def main() -> None:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== bootstrapping a demo session on {CLOUD_URL} ===")
    sess = _post_json(f"{CLOUD_URL}/api/demo/session", {"email": DEMO_EMAIL, "name": "VoiceTester"})
    sid = sess.get("session_id")
    print(f"session_id={sid} · warm={sess.get('warm')} · reused={sess.get('reused')} · url={sess.get('url')}")
    if not sid:
        raise SystemExit(f"no demo session returned: {sess}")

    # /api/token routed to THIS session's machine via ?s= (my.zaelar.com reverse-proxies + fly-replay).
    # A cold-created demo machine may still be booting, so poll the token until the engine answers.
    tok_url = f"{CLOUD_URL}/api/token?identity={config.TESTER_IDENTITY}&s={sid}"
    tok = None
    for i in range(40):
        try:
            t = _get_json(tok_url, timeout=15)
            if t.get("url") and t.get("token"):
                tok = t
                break
            print(f"  token payload not ready ({i}): {t}")
        except Exception as e:  # noqa: BLE001
            print(f"  engine not up yet ({i}): {e}")
        await asyncio.sleep(4)
    if not tok:
        raise SystemExit("token never became available — the demo engine never came up")
    print(f"token OK · livekit={tok['url']} room={tok['room']} · tts={config.TESTER_TTS} stt={config.TESTER_STT}")

    async with http_context.open():
        tts, stt = providers.build_tts(), providers.build_stt()
        link = VoiceLink(tts, stt, on_event=_log, wav_path=str(config.RUNS_DIR / "cloud_smoke_zaelar.wav"))
        await link.connect(tok["url"], tok["token"])

        print("=== waiting for zaelar's greeting (45s) ===")
        g = await link.wait_reply(timeout=45)
        print(f"GREETING → {g}")

        print("=== the tester speaks ===")
        await link.say("Hola zaelar, ¿me oyes bien? Responde en una frase corta.")
        r = await link.wait_reply(timeout=45)
        print(f"REPLY → text={r.get('text')!r} · latency_ms={r.get('latency_ms')} · timeout={r.get('timeout')}")

        await link.aclose()
    print("=== cloud voice smoke done ===")


if __name__ == "__main__":
    asyncio.run(main())
