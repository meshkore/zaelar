"""V2-597 — the LIVE round trip against a real YouTube account. Credential-gated: SKIPS until one is connected.

Everything below the facade seam is HTTP against somebody's real Google account, and a fake that answers the
way we THINK the Data API answers proves only that we agree with ourselves («integración viva no se da por
buena con mocks»). Built WHOLE even while nothing can run it — the workflow's rule: the circuit exists, and
enabling it is one connection away.

## Why it is a `live` node and not a skipped unit test

A `live` node is excluded from `deterministic_paths()`: it never runs in CI and never turns red on a machine
with no account. Running it is an explicit act, and PENDING is a real state said out loud with the exact
steps to enable it.

## What it deliberately does NOT do

It never asserts or prints a subscription name, a video title or any content — this repository is public and
its test reports have leaked personal data before. Every assertion is about SHAPE and INVARIANTS: that the
rows are normalized, that the ordering is newest-first, that counts are coherent. Never about what the
operator happens to watch.

## To run it

    1. Google Cloud: create an OAuth client (Desktop app) and enable the YouTube Data API v3.
    2. ⚙ → Conectores → YouTube: paste the client_id (and client_secret) and connect.
    3. cd engine && ./.venv/bin/python -m pytest tests/connectors/unit/video/live_video_account_roundtrip.py -v
"""
from __future__ import annotations

import pytest

from connectors.video import oauth, providers, service

_SKIP = ("no YouTube account connected — create an OAuth client (Desktop app) with the YouTube Data API v3 "
         "enabled, paste its client_id in ⚙ → Conectores → YouTube, connect, and re-run")


def _connected() -> str:
    for pid in providers.ids():
        if oauth.tokens_present(pid):
            return pid
    return ""


@pytest.mark.skipif(not _connected(), reason=_SKIP)
def test_the_live_suggestions_pull_answers_in_the_normalized_shape():
    r = service.suggestions(_connected())
    assert r["ok"] is True, r.get("error")
    # ok may legitimately come with zero items (an account with no subscriptions) — then it must SAY so.
    if not r["items"]:
        assert r.get("reason"), "empty without a reason is the drive-looks-empty confound"
        return
    assert r["channels"] >= 1 and r["fetched_at"] > 0
    for it in r["items"]:
        for key in ("videoId", "title", "channel", "published", "url"):
            assert it.get(key) is not None, key
        assert len(it["videoId"]) == 11
        assert it["url"].startswith("https://www.youtube.com/watch?v=")
    published = [it["published"] for it in r["items"] if it["published"]]
    assert published == sorted(published, reverse=True), "suggestions must arrive newest first"


@pytest.mark.skipif(not _connected(), reason=_SKIP)
def test_the_live_status_is_redacted():
    st = service.status()
    assert st["ok"] and st["providers"]
    import json
    txt = json.dumps(st).lower()
    for secret_shaped in ("access_token", "refresh_token", "client_secret"):
        assert secret_shaped not in txt
