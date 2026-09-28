"""The scheduled-notice line in the prompt says it is not the day's agenda (demo pass 2026-09-28, full25 Z1).

«what's on my plate tomorrow» was answered from this line — two of the four meetings: six notices, unsorted, is not
a calendar. It is sorted soonest first and says, in so many words, that a day is read on the agenda."""
from nucleo.flash import live_blocks


def test_the_line_is_marked_partial_and_sorted(monkeypatch):
    from nucleo import scheduler
    jobs = [{"name": "aviso: Later", "prompt": "Remind «Later» on 2026-09-30 at 10:00", "next_run": "2026-09-30 08:00",
             "schedule": "2026-09-30 08:00"},
            {"name": "aviso: Sooner", "prompt": "Remind «Sooner» on 2026-09-29 at 09:00", "next_run": "2026-09-29 07:00",
             "schedule": "2026-09-29 07:00"}]
    monkeypatch.setattr(scheduler, "list_jobs", lambda active_only=True: jobs)
    line = live_blocks._cron_line()
    assert "PARCIAL" in line and "NO la agenda" in line and "read_widget" in line
    assert line.index("Sooner") < line.index("Later"), "soonest first"
