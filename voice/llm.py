#
# Cliente LLM compartido (OpenAI-compatible vía router AI/ML API).
#
# Pieza pequeña y autocontenida que usan las ramas async del cerebro (evaluator_rt, planner).
# NO es el hot-path de voz (eso va por Pipecat). Aquí solo peticiones de razonamiento/evaluación.
#
import json
import os
import re
import urllib.request

API_URL = os.environ.get("LLM_API_URL", "https://api.aimlapi.com/v1/chat/completions")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"  # Cloudflare 1010 bloquea el UA de urllib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # repo root (zaelar/)
NO_TEMP = ("opus", "claude", "sonnet")  # rechazan 'temperature'


def load_key() -> str | None:
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("AIMLAPI_KEY="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("AIMLAPI_KEY") or os.environ.get("LLM_API_KEY")


def call_llm(messages, model, temperature=0.0, max_tokens=3500):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None and not any(t in model.lower() for t in NO_TEMP):
        payload["temperature"] = temperature
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={
        "Authorization": f"Bearer {load_key()}", "Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def parse_json(txt):
    txt = txt.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S)
    if m:
        txt = m.group(1).strip()
    i, j = txt.find("{"), txt.rfind("}")
    return json.loads(txt[i:j + 1])
