"""zaelar voice tester (INI-013) — an agent whose only job is to test zaelar.

It joins zaelar's LiveKit room as a second participant, SPEAKS to it (TTS) and LISTENS (STT), driving
scenarios with a DeepSeek brain and detecting things to improve. Because it speaks via TTS (no human mic),
a full voice conversation with zaelar is reproducible and observable end-to-end. Built on zaelar's own engine
providers + the LiveKit client; reuses the persona/judge/analyze/report logic of the prior sim candidate.
"""
