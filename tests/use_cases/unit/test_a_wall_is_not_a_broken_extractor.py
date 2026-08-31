"""V2-333 — an empty page BEHIND an anti-bot wall is not an extraction failure.

The fact was already carried in the report (`navegador_task.walls_hit` and `last_wall`, with the SITE), and the
judge was only told when there had NOT been a wall. So when faced with an empty page, it concluded the only thing
it could.

MEASURED in `compare-insurance-quotes__es` (2026-08-26 01:39). The round went through rastreator, acierto, kelisto,
lineadirecta, and mutua, ran into anti-bot checks, and the verdict was:

    «the #1 blocker is the serious failure in the browser's extraction mechanism: the system could not read
     a single price or insurer name»   → mechanism 2

The SAME round for the same case, four hours earlier, had produced **eight real options with mechanism 4**. What
changed was not the code: it was what the sites allowed through.

And it was verified that this was NOT a regression on our part: extraction from `acierto.com` returns 9 identical
rows before and after the entire V2-321…V2-326 chain.

⚠️ It does NOT excuse everything, and the block says so: what IS scoreable is what zaelar did with the obstacle —
whether it said so, tried another site, or kept narrating normally. A wall explains the empty page, not the silence.
"""
from tests.use_cases.e2e.agent.judge import mechanism_facts


def test_sin_muros_no_se_menciona():
    txt = mechanism_facts({"navegador_task": {"walls_hit": 0}})
    assert "CERRÓ LA PUERTA" not in txt


def test_con_muros_se_dice_CUÁNTOS_y_DÓNDE():
    txt = mechanism_facts({"navegador_task": {
        "walls_hit": 3, "last_wall": {"site": "rastreator.com",
                                      "reason": "el sitio interpuso una verificación anti-robot"}}})
    assert "3 muro(s)" in txt
    assert "rastreator.com" in txt, "«me bloquearon» es un hecho; «me bloqueó rastreator» es accionable"
    assert "anti-robot" in txt


def test_y_se_le_PROHIBE_puntuarlo_como_fallo_de_extracción():
    txt = mechanism_facts({"navegador_task": {"walls_hit": 1, "last_wall": {"site": "x.com", "reason": "muro"}}})
    low = txt.lower()
    assert "no es un fallo de" in low and "extracción" in low
    assert "no puedes puntuarla" in low


def test_pero_NO_le_exime_de_juzgar_la_conducta():
    """The safeguard that prevents turning this into an amnesty: a wall explains the empty page, not the silence."""
    txt = mechanism_facts({"navegador_task": {"walls_hit": 2, "last_wall": {"site": "y.com", "reason": "muro"}}})
    low = txt.lower()
    assert "sí es puntuable" in low
    assert "otro sitio" in low or "lo dijo" in low


def test_un_walls_hit_ilegible_no_rompe_el_informe():
    for malo in ("", None, "no-es-un-numero", {}):
        mechanism_facts({"navegador_task": {"walls_hit": malo}})


def test_sin_tarea_de_navegador_no_inventa_muros():
    assert "CERRÓ LA PUERTA" not in mechanism_facts({})
