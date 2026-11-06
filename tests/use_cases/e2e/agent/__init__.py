"""zaelar use-case tester — plays a real, imperfectly-spoken person making an open-ended real-world request
(book a hotel, find a car, coordinate a plan) over the text/probe channel with execute=true, adapting to
whatever zaelar asks back, and verifying not just what zaelar SAID but what actually fired (a Brain Worker
spawned, a browser really navigated, real data came back) via the durable observability flow API.

Born as a sibling of the voice tester (retired 2026-11-05) — same DRIVE+JUDGE shape; its provider clients
live on here in `providers.py`. See tests/use_cases/CASES.md for the tier taxonomy and why this suite exists.
"""
