"""Demo pass 2026-09-28, Z1: «what's on my plate tomorrow» → «your ZAELAR weekly review at 7, the product meeting at
9, the Meshcore architecture session at 1» — every meeting two hours early. The agenda said 9, 11 and 15; the
prompt's proactivity line listed the meetings' own ALERTS («ZAELAR weekly review (2026-09-29 07:00)»), which ring
two hours before, with nothing saying so. The datum now says what its time is."""
from nucleo.flash import live_blocks


def test_a_scheduled_alert_says_its_time_is_when_it_rings(monkeypatch):
    from nucleo import scheduler
    monkeypatch.setattr(scheduler, "list_jobs", lambda active_only=True: [
        {"name": "aviso: ZAELAR weekly review", "schedule": "2026-09-29 07:00"}])
    line = live_blocks._cron_line()
    assert "suena 2026-09-29 07:00" in line, line
    assert "no la de la cita" in line
    assert "ZAELAR weekly review (2026-09-29 07:00)" not in line, "a bare time reads as the meeting's"
