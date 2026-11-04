"""The blind bench of the search providers — the same cases to every index, judged without its name (V2-782).

    ./.venv/bin/python -m tests.search.live.bench [--mode fact|leads|local] [--only perplexity,brave] [--repeat 2]

It measures the ENGINE'S OWN ADAPTERS (`search.web._BACKENDS`), so a parser or a header that degrades shows up as a
lower score, not only an outage. The cases are `tests/search/bank/bench_cases.json`; the judge is Claude Code on the
licence (the use-case judge), shown the options under letters in a shuffled order and never a provider's name.
Calls run one at a time: in parallel a fresh account's rate limit turns a third of them into 429s and the scores
measure the limit, not the index. The report lands in `tests/runs/` (local). A few cents per pass.

The provider ORDER of each chain is decided from what this prints (`search/web.py::_ANSWER_ORDER`/`_RESULTS_ORDER`):
quality first, then cost, then speed; the judge moves ±0.7 between passes, so a gap below that is a tie.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
CASES = ENGINE / "tests" / "search" / "bank" / "bench_cases.json"
from tests.use_cases.e2e.agent.llm import JUDGE_MODEL  # noqa: E402 — the one judge of every bench
#: Answer-only indexes cite redirects: they are not asked for pages.
_ANSWER_ONLY = {"gemini"}
_NEED = {
    "fact": "A voice assistant must SPEAK the fact asked for. Judge whether the option gives the exact, correct, "
            "current datum. A snippet that contains the datum counts exactly as much as an answer that states it.",
    "leads": "A personal assistant needs PAGES TO OPEN to act on this request. Judge whether the rows are real, "
             "specific, relevant pages for this exact place or product, with useful detail.",
    "local": "A personal assistant must hand its user BUSINESSES HE CAN CONTACT: real businesses of the right type, in "
             "that place, with a name and a way to reach them and any rating. Directories without named businesses, "
             "the wrong type or the wrong city score low.",
}


def blind(blocks: dict[str, dict], rng: random.Random) -> tuple[str, dict[str, str]]:
    """The options as the judge reads them, and letter → provider. No provider name ever reaches the text. Pure."""
    names = list(blocks)
    rng.shuffle(names)
    letters = {chr(65 + i): n for i, n in enumerate(names)}
    parts = []
    for letter, n in letters.items():
        r = blocks[n]
        lines = ([f"Answer: {r.get('answer')}"] if r.get("answer") else []) + [
            f"- [{str(x.get('url') or '')[:100]}] {' '.join(str(x.get('title') or '').split())} — "
            f"{' '.join(str(x.get('snippet') or '').split())[:300]}" for x in (r.get("results") or [])[:5]]
        parts.append(f"### Option {letter}\n" + ("\n".join(lines) or "(nothing)"))
    return "\n\n".join(parts), letters


def scores_from(text: str, letters: dict[str, str]) -> dict[str, float]:
    """The judge's JSON reply → provider → score; a letter it skipped scores 0. Pure."""
    m = re.search(r"\{.*\}", text or "", re.S)
    got = (json.loads(m.group(0)).get("scores") or {}) if m else {}
    return {n: float(got.get(letter, 0) or 0) for letter, n in letters.items()}


def summary(rows: list[dict]) -> dict[str, dict]:
    """provider → mean score, median latency, errors. Pure."""
    out: dict[str, dict] = {}
    for n in {n for r in rows for n in r["scores"]}:
        sc = [r["scores"].get(n, 0.0) for r in rows]
        lat = sorted(r["lat"][n] for r in rows if n in r["lat"])
        out[n] = {"score": round(sum(sc) / len(sc), 1), "lat_s": round(lat[len(lat) // 2], 1) if lat else None,
                  "errors": sum(n in r["err"] for r in rows)}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["score"]))


def _judge(mode: str, request: str, blocks: dict[str, dict], rng: random.Random) -> dict[str, float]:
    text, letters = blind(blocks, rng)
    prompt = (f"{_NEED[mode]}\nRequest: {request}\n\nScore each option 0-10.\n\n{text}\n\n"
              "Reply ONLY with JSON {\"scores\":{\"A\":n,...}}")
    p = subprocess.run(["claude", "-p", prompt, "--model", JUDGE_MODEL, "--output-format", "json"],
                       capture_output=True, text=True, timeout=300)
    return scores_from(json.loads(p.stdout or "{}").get("result", ""), letters)


def run(mode: str, only: list[str], repeat: int) -> dict:
    from search import web
    from search.health import _load_credentials
    _load_credentials()
    cases = json.loads(CASES.read_text(encoding="utf-8"))[mode]
    names = [n for n in (only or web._BACKENDS) if n != "google" and web._usable(n)
             and not (mode != "fact" and n in _ANSWER_ONLY)]
    rng, rows = random.Random(), []
    for _ in range(repeat):
        for case in cases:
            q = f"{case['q']} {case['near']}" if case.get("near") else case["q"]
            blocks, lat, err = {}, {}, {}
            for n in names:
                t = time.time()
                try:
                    blocks[n] = web._BACKENDS[n](q, 5)
                except Exception as e:  # noqa: BLE001 — an index that fails scores what it brought: nothing
                    blocks[n], err[n] = {"answer": "", "results": []}, f"{type(e).__name__}: {str(e)[:120]}"
                lat[n] = round(time.time() - t, 2)
            rows.append({"q": q, "lang": case["lang"], "scores": _judge(mode, q, blocks, rng), "lat": lat, "err": err})
            print(f"{case['lang']} {q[:50]:50s} " + " ".join(f"{n}={rows[-1]['scores'].get(n)}" for n in names), flush=True)
    return {"mode": mode, "judge": JUDGE_MODEL, "at": time.strftime("%Y-%m-%d %H:%M"), "summary": summary(rows), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=sorted(_NEED), default="fact")
    ap.add_argument("--only", default="", help="comma-separated provider names (default: every usable one)")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    rep = run(a.mode, [s for s in a.only.split(",") if s], max(1, a.repeat))
    out = ENGINE / "tests" / "runs" / f"search-bench-{a.mode}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{a.mode} · {len(rep['rows'])} cases · judge {JUDGE_MODEL}\nprovider       score   lat    errors")
    for n, s in rep["summary"].items():
        print(f"{n:14s} {s['score']:5.1f}  {s['lat_s']}s  {s['errors']}")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
