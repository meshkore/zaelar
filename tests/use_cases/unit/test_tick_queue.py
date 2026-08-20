"""The continuous loop must only launch cases that can REACH their own goal.

Written after the loop was re-armed for a 12-hour unattended run (2026-08-20). Step 2 of the tick tops the
queue up from the catalogue, and until this guard existed it pulled from all 125 cases — including the 78 that
cannot finish here (54 need a credential, a payment or a real object only the operator can supply; 24 need a
capability that is not built). Each one costs the same 3-6 minutes and a judge call as a real case and ends the
same way every time, so an unattended night would have filed initiative after initiative that the fixing agent
has no way to act on, while the runnable cases sat untouched.

The failure mode this guards is the expensive kind: nothing goes red, the board just fills with
work nobody can do. So the assertion is on the QUEUE the tick would actually launch, not on the filter helper.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import scenarios as SC, segments as SG, tick as T


def test_the_queue_only_ever_holds_runnable_cases(live_board):
    for s in T._unrun_scenarios():
        assert SG.is_completable(s.id), (
            f"«{s.id}» está en la cola del tick pero su segmento es «{SG.group_of(s.id)}»: "
            f"gastaría una tanda entera para acabar pidiendo algo que no tenemos")


def test_and_the_blocked_ones_are_genuinely_excluded():
    """La otra mitad: sin esto, «filtra» y «la cola está vacía» pasan el mismo test."""
    queued = {s.id for s in T._unrun_scenarios()}
    blocked = [s.id for s in SC.all_scenarios() if not SG.is_completable(s.id)]
    assert blocked, "la tabla de segmentos dice que no hay ningún caso bloqueado — eso ya sería el bug"
    assert not (queued & set(blocked))


def test_the_queue_is_not_empty_while_runnable_cases_remain_untried(live_board):
    """Y que el filtro no se pase de listo: mientras quede un caso ejecutable sin veredicto, la cola lo tiene.

    Si algún día pasan los 47, esto se apaga solo — el catálogo se habría agotado de verdad, que es la
    condición que `_top_up` ya sabe decir.
    """
    from tests.use_cases.e2e.agent import status as statusmod

    led = statusmod.load().get("scenarios") or {}
    judged = {k for k, e in led.items() if (e or {}).get("state") in ("PASS", "FAIL")}
    untried = [s.id for s in SC.all_scenarios() if SG.is_completable(s.id) and s.id not in judged]
    assert len({s.id for s in T._unrun_scenarios()}) == len(untried)


def test_es_and_us_are_never_mixed_in_one_batch():
    """El idioma es de PROCESO (`ZAELAR_LANGUAGE`), así que una tanda mixta puntuaría casos ES contra respuestas
    en inglés — el artefacto que casi produjo informes de bug falsos el 2026-08-18. La cola va ordenada con ES
    delante justo para que el corte por `MAX_PER_TICK` caiga siempre dentro de un solo locale."""
    q = T._unrun_scenarios()
    if not q:
        return
    lang = q[0].locale
    picked = [s for s in q if s.locale == lang][:T.MAX_PER_TICK]
    assert len({s.locale for s in picked}) == 1


def test_a_case_that_only_ever_died_in_INFRA_stays_in_the_queue(live_board):
    """Un `INFRA` no es un veredicto: el arnés se murió antes de juzgar, así que ese caso NO se ha medido.

    Contarlo como probado retiró en silencio `build-workout-tracker-widget` —el único caso ejecutable que
    cubre la generación de widgets— porque murió con un 403 del broker y desde entonces cada tick lo saltaba
    como ya-intentado. Un caso que desaparece de la cola sin que nada se ponga rojo es la clase de fallo que
    solo se nota semanas después, contando por qué la cobertura no sube.
    """
    from tests.use_cases.e2e.agent import status as statusmod

    led = statusmod.load().get("scenarios") or {}
    infra = [k for k, e in led.items() if (e or {}).get("state") == "INFRA" and SG.is_completable(k)]
    queued = {s.id for s in T._unrun_scenarios()}
    for sid in infra:
        assert sid in queued, f"«{sid}» solo tiene un INFRA (nunca se midió) y la cola lo está saltando"


def test_but_a_real_verdict_does_retire_a_case(live_board):
    """La otra mitad: PASS y FAIL sí son mediciones, y re-correrlas es lo que hace el camino de verify."""
    from tests.use_cases.e2e.agent import status as statusmod

    led = statusmod.load().get("scenarios") or {}
    judged = [k for k, e in led.items() if (e or {}).get("state") in ("PASS", "FAIL")]
    assert judged, "el marcador no tiene ni un veredicto — este test no estaría probando nada"
    queued = {s.id for s in T._unrun_scenarios()}
    assert not (queued & set(judged))


def test_a_verify_task_that_points_at_NO_case_is_reported_not_swallowed(monkeypatch):
    """`scenarios_awaiting_verification` promete en su docstring que un slug irresoluble «se REPORTA, nunca se
    salta en silencio». Hasta el 2026-08-20 esa promesa se rompía justo aquí: `_retest_pending` filtraba
    `if p["scenario"]` y dos tareas (`progreso-fabricado`, `progreso-fabricado-idioma`) —que pedían re-probar un
    PATRÓN, no un caso— se quedaron en `status: next` desde el 2026-08-18 esperando una corrida imposible.

    El coste no es un error: es que el agente que arregla espera un re-test que nunca va a correr, y
    «esperando re-test: 4» informa de un número que era mayormente ficción. El tick no puede ACTUAR sobre
    ellas, pero sí decir sus nombres.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod

    logged: list[str] = []
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": None, "slug": "progreso-fabricado",
                                      "task": Path("T326-uc-progreso-fabricado-verify.md")}])
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})

    out = T._retest_pending()
    assert out["retested"] == 0
    assert out.get("orphan") == ["T326-uc-progreso-fabricado-verify.md"]
    said = " ".join(logged)
    assert "T326-uc-progreso-fabricado-verify.md" in said, "tiene que NOMBRAR la tarea que nadie va a correr"
    assert "progreso-fabricado" in said


def test_but_a_resolvable_task_is_not_reported_as_an_orphan(monkeypatch):
    """La mitad de sensibilidad: sin esto, «reporta las huérfanas» y «reporta todas» pasan igual, y el log del
    tick se llenaría de avisos sobre tareas que sí se están corriendo."""
    from tests.use_cases.e2e.agent import status as statusmod

    logged: list[str] = []
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": "cheapest-monitor", "slug": "cheapest-monitor",
                                      "task": __import__("pathlib").Path("T999-uc-cheapest-monitor-verify.md")}])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, ""))
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    out = T._retest_pending()
    assert out.get("orphan") == []
    assert "no apuntan a ningún caso" not in " ".join(logged)


def test_two_verify_tasks_for_the_SAME_case_are_measured_once(monkeypatch):
    """El 2026-08-20 el agente que arregla respondió `find-theatre-tickets__es` en DOS tareas separadas
    (T434 y T438), y el tick anunció el caso dos veces y recorrió su contabilidad dos veces sobre UN solo
    veredicto: la misma ronda escrita dos veces en el paraguas y un `re-probados` inflado. No es un segundo
    gasto de corrida —`run.py --verify` mide una vez y cierra las dos tareas—, es el libro mayor duplicando.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod

    logged: list[str] = []
    seen_cases: list[str] = []
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification", lambda reg: [
        {"scenario": "find-theatre-tickets__es", "slug": "find-theatre-tickets-es",
         "task": Path("T434-uc-find-theatre-tickets-es-verify.md")},
        {"scenario": "find-theatre-tickets__es", "slug": "find-theatre-tickets-es",
         "task": Path("T438-uc-find-theatre-tickets-es-verify.md")},
    ])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: (seen_cases.append(sid), None)[1])
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, ""))
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    out = T._retest_pending()
    assert out["retested"] == 1, "un caso medido una vez se cuenta una vez, haya 1 o 5 tareas pidiéndolo"
    assert seen_cases == ["find-theatre-tickets__es"], "la contabilidad del caso corrió dos veces"
    said = " ".join(logged)
    assert "T438-uc-find-theatre-tickets-es-verify.md" in said, (
        "colapsar en silencio deja al operador sin saber por qué una tarea `next` no aparece en el log")


def test_but_distinct_cases_are_all_kept(monkeypatch):
    """La mitad de sensibilidad: un dedup por CASO no puede convertirse en «solo se re-prueba el primero»."""
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod

    monkeypatch.setattr(T, "_log", lambda m: None)
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification", lambda reg: [
        {"scenario": "cheapest-monitor", "slug": "cheapest-monitor", "task": Path("T1-verify.md")},
        {"scenario": "remember-and-remind-deadline", "slug": "remember-and-remind-deadline",
         "task": Path("T2-verify.md")},
    ])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, ""))
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    assert T._retest_pending()["retested"] == 2


def test_run_verify_drives_one_case_ONCE_and_closes_BOTH_of_its_tasks():
    """La otra mitad del dedup, en `run.py`. El tick colapsaba su CONTABILIDAD, pero el que conduce la
    conversación es el runner, y ahí el caso duplicado se corría de verdad dos veces.

    Medido el 2026-08-20 10:00: T434 y T438 pedían las dos `find-theatre-tickets__es`, y el paraguas V2-167
    acabó con las rondas 13 y 15 idénticas — misma medición, ~4 minutos del turno tirados, y la evidencia de
    la iniciativa contando el doble de intentos de los que hubo. Y como el mapa era `{caso: tarea}`, de las
    dos tareas solo se cerraba UNA: la otra se quedaba en `next` pidiendo un re-test ya hecho.

    Se afirma sobre el COMPORTAMIENTO de `_verify_batch`, no leyendo el fuente: un test que busca texto en el
    código ya falló una vez en esta suite encontrando lo que buscaba... dentro del comentario que explicaba
    por qué no había que hacerlo.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from tests.use_cases.e2e.agent import run as R

    registry = {"find-theatre": SimpleNamespace(id="find-theatre"), "otro": SimpleNamespace(id="otro")}
    pend = [{"scenario": "find-theatre", "task": Path("T434-verify.md")},
            {"scenario": "find-theatre", "task": Path("T438-verify.md")},
            {"scenario": "otro", "task": Path("T440-verify.md")},
            {"scenario": None, "task": Path("T999-huerfana.md")}]

    chosen, tasks = R._verify_batch(pend, registry)
    assert [c.id for c in chosen] == ["find-theatre", "otro"], (
        "el caso se conduciría dos veces: media conversación y media ronda de más")
    assert [t.name for t in tasks["find-theatre"]] == ["T434-verify.md", "T438-verify.md"], (
        "las DOS tareas tienen que cerrarse; quedarse una en `next` pide un re-test que ya se hizo")


def test_and_a_task_naming_an_unknown_case_never_reaches_the_batch():
    """La mitad de sensibilidad: colapsar por caso no puede colarse una clave que no está en el catálogo —
    `registry[sid]` reventaría la tanda entera por una tarea mal nombrada."""
    from pathlib import Path

    from tests.use_cases.e2e.agent import run as R

    chosen, tasks = R._verify_batch([{"scenario": "no-existe", "task": Path("T1.md")}], {})
    assert chosen == [] and tasks == {}


def test_a_verify_task_named_with_the_RAW_scenario_id_still_resolves(monkeypatch):
    """El agente que arregla escribe estos nombres a mano, y el 2026-08-20 CUATRO de sus ocho peticiones de
    re-test eran invisibles: dos llevaban el id crudo (`book-hotel-night-known__es`, donde la convención
    colapsa `__` a `-`) y dos un slug a medias. Rechazarlas es técnicamente correcto e inútil en la práctica
    —el otro agente espera un re-test que nunca corre y este lado informa de una huérfana que en realidad es
    una diferencia de ortografía.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import initiative as I

    monkeypatch.setattr(I, "pending_verifications", lambda: [
        {"slug": "book-hotel-night-known__es", "task": Path("T447-verify.md")},
        {"slug": "cheapest-monitor", "task": Path("T446-verify.md")},
    ])
    got = {p["task"].name: p["scenario"] for p in I.scenarios_awaiting_verification(
        {"book-hotel-night-known__es": object(), "cheapest-monitor": object()})}
    assert got["T447-verify.md"] == "book-hotel-night-known__es"
    assert got["T446-verify.md"] == "cheapest-monitor"


def test_but_an_AMBIGUOUS_slug_is_refused_and_says_between_which(monkeypatch):
    """La mitad que importa: `find-theatre-tickets` casa con __es y __us. Elegir uno da un veredicto que parece
    bueno y no prueba nada —se habría verificado el arreglo contra el otro idioma—, así que no se elige. Pero
    hay que DECIR entre cuáles duda, que es lo único que permite renombrar la tarea y seguir.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import initiative as I

    monkeypatch.setattr(I, "pending_verifications", lambda: [
        {"slug": "find-theatre-tickets", "task": Path("T441-verify.md")}])
    p = I.scenarios_awaiting_verification(
        {"find-theatre-tickets__es": object(), "find-theatre-tickets__us": object()})[0]
    assert p["scenario"] is None
    assert "find-theatre-tickets__es" in p["why"] and "find-theatre-tickets__us" in p["why"]
