#
# Shared LLM client (OpenAI-compatible, DeepSeek direct by default).
#
# Small, self-contained component used by the brain's async branches (evaluator_rt, planner).
# It is NOT the voice hot path (that goes through Pipecat). Only reasoning/evaluation requests go here.
#
import json
import os
import re
import urllib.request

API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/chat/completions")
UA = "zaelar-engine"  # a named client: an edge in front of a provider may refuse urllib's default agent
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # repo root (zaelar/)
NO_TEMP = ("opus", "claude", "sonnet")  # reject 'temperature'


def load_key() -> str | None:
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")


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
