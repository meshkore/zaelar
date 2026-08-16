"""zaelar use-case tester — plays a real, imperfectly-spoken person making an open-ended real-world request
(book a hotel, find a car, coordinate a plan) over the text/probe channel with execute=true, adapting to
whatever zaelar asks back, and verifying not just what zaelar SAID but what actually fired (a Brain Worker
spawned, a browser really navigated, real data came back) via the durable observability flow API.

Sibling of tests/voice/e2e/agent/ (INI-013) — same DRIVE+JUDGE shape, reused deliberately rather than
reinvented. See tests/use_cases/CASES.md for the tier taxonomy and why this suite exists.
"""
