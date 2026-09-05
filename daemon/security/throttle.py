"""What happens when a caller keeps being refused.

THE THREAT IS NOT GUESSING THE TOKEN. It is 32 bytes of urandom; nobody is brute-forcing it. The threat is the
two things a rejected caller can still do for free:

  DROWN THE AUDIT LOG. Every refusal is recorded, on purpose — a run of them against the same boundary is the
  signal that something is probing, and it is invisible if only successes are kept. But "every refusal is
  recorded" plus "a local process can send ten thousand a second" is a way to fill the user's disk and, worse,
  to push the interesting line off the end of a rotated log. So refusals from the same source COLLAPSE: the
  first is written in full, the rest of the window become one summary line with a count.

  BURN THE MACHINE. Answering is cheap, but not free. A small delay after a run of failures makes a flood cost
  the sender more than it costs us, and costs a legitimate caller — which fails at most once, while it is being
  paired — nothing at all.

WHAT IT DELIBERATELY DOES NOT DO: lock anybody out. There is no ban, no blocklist, no state that survives a
restart. Every process on this machine already runs as the user, so a lockout would be trivially resettable by
the attacker and permanently annoying for the user — it would only ever fire on the person who mistyped their
own token. The goal is to make a flood boring, not to punish it.
"""
from __future__ import annotations

import threading
import time

# One full record, then a summary per window. Long enough that a probe is one line; short enough that a real
# problem still shows up promptly in the log the user reads.
WINDOW_S = 30.0

# The delay ramps after this many failures inside a window, and is capped so a refusal never becomes a hang.
FREE_FAILURES = 3
DELAY_STEP_S = 0.05
MAX_DELAY_S = 1.0


class _Bucket:
    __slots__ = ("started", "count", "reported")

    def __init__(self, now: float):
        self.started = now
        self.count = 0
        self.reported = False


class Throttle:
    """Per-reason counters. Not per-IP: everything here arrives from loopback, so the peer address distinguishes
    nothing, while the REASON distinguishes a lot — a run of `bad_token` and a run of `browser` are two very
    different stories about what is happening to this machine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    def note(self, reason: str) -> tuple[bool, float, int]:
        """Record one refusal.

        Returns `(should_record, delay_seconds, suppressed_since_last_record)`:
          · `should_record` is True for the first refusal of a window and once per window afterwards, so the log
            keeps the shape of the flood without keeping every line of it;
          · `delay_seconds` is what the caller should sleep BEFORE answering;
          · `suppressed_since_last_record` is how many were collapsed into this one, so the summary line can say
            so rather than under-reporting.
        """
        now = time.monotonic()
        key = reason.split(":", 1)[0]        # `bad_host:evil.example` and `bad_host:other` are one story
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.started > WINDOW_S:
                bucket = _Bucket(now)
                self._buckets[key] = bucket
            bucket.count += 1

            if not bucket.reported:
                bucket.reported = True
                suppressed = 0
                should_record = True
            elif bucket.count % 100 == 0:
                # A very loud window still gets a heartbeat, or a flood that outlives the window looks like it
                # stopped.
                suppressed = 99
                should_record = True
            else:
                suppressed = 0
                should_record = False

            over = max(0, bucket.count - FREE_FAILURES)
            delay = min(MAX_DELAY_S, over * DELAY_STEP_S)
            return should_record, delay, suppressed

    def note_success(self) -> None:
        """A request that was admitted clears the slate: whatever was happening, it is not happening now."""
        with self._lock:
            self._buckets.clear()


# The daemon is one process serving one user, so one instance is the whole story. Held at module level rather
# than on the server object so the CLI and the tests can reach it without building a server.
SHARED = Throttle()
