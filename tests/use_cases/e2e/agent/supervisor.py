"""Supervisor: el plató NO PARA. Encadena casos de uso de uno en uno y corta lo que se cuelga.

Encargo del operador (2026-08-27): «que el sistema no se detenga y aprovechemos el tiempo al máximo», con un
listón explícito — *«no podemos estar diez minutos para hacer una búsqueda de una guitarra en Amazon; se supone
que la búsqueda se hace en un minuto, dos o tres máximo»*.

DE UNO EN UNO, y no es una preferencia: hay **un solo navegador** por plató. Dos rondas a la vez se pelean por
la misma pestaña y las dos miden mal — es justo el defecto que el propio arnés reporta como «2 workers para UN
encargo». Así que el ciclo es: ¿hay algo corriendo? → sí: vigilarlo; no: lanzar el siguiente.

QUÉ CUENTA COMO COLGADO, y por qué así: no se mide la DURACIÓN sino el SILENCIO. Una ronda legítima puede
tardar si está pasando cosas (el operador lo aceptó: «si tienes control preciso y observable de cada movimiento
podemos alargarnos»); lo que no puede es dejar de dar señal. Dos cortes, y el segundo existe porque el primero
no basta:

  · SILENCIO — el log de la ronda no crece en `HANG_S`. Es el que caza un proceso muerto, un modelo que no
    responde, un navegador clavado. Barato y sin falsos positivos: el runner imprime cada turno.
  · TECHO — la ronda entera pasa de `CAP_S`. Caza lo contrario: la que sí habla pero no llega a ningún lado,
    que es exactamente la que se comió 21 minutos para entregar cero coches.

Al cortar se APUNTA POR QUÉ. Una ronda matada por el supervisor no es un veredicto del juez y no puede contarse
como si lo fuera: entra en el diario como `hung`/`capped`, con su log, para que quien lo lea sepa que ahí no hay
medición sino una avería.

Lo que este fichero NO hace: arreglar nada. Mide y encadena; las correcciones las hace un humano o un agente
leyendo `diario.jsonl`. Un supervisor que además tocara el motor se estaría midiendo a sí mismo.
"""
from __future__ import annotations

import hashlib as _hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[4]
_SALIDA = _RAIZ / "tests" / "runs" / "use_cases" / "supervisor"
_DIARIO = _SALIDA / "diario.jsonl"

#: Sin señal en el log durante esto → colgado. El runner imprime cada turno, así que tres minutos mudos son
#: una avería, no lentitud.
HANG_S = int(os.getenv("UC_HANG_S", "180"))
#: Techo de la ronda entera. Sale del listón del operador (una búsqueda son 1-3 min) con margen para una
#: conversación de ~20 turnos por encima.
CAP_S = int(os.getenv("UC_CAP_S", "720"))
#: Respiro entre rondas: deja al motor cerrar pestañas y soltar el navegador antes de la siguiente.
PAUSA_S = int(os.getenv("UC_PAUSA_S", "20"))
#: Prórroga cuando la ronda YA ha llegado al veredicto. Medido a la primera: `weekend-adventure-sports-bilbao`
#: (2026-08-27) se comió el techo **dentro de `verifying mechanism`** — la conversación había terminado, el
#: navegador ya no gastaba, y lo único que faltaba era el informe. Matarla ahí tira los doce minutos enteros y
#: no deja ni una medición, que es exactamente lo contrario de para lo que existe el techo. El techo protege
#: del trabajo que no llega a nada; el veredicto SÍ llega, y encima es lo que veníamos a buscar.
VERIFICA_EXTRA_S = int(os.getenv("UC_VERIFICA_EXTRA_S", "300"))
#: Las señales que el runner imprime al pasar a la fase de veredicto. Si aparecen, la parte cara ya se hizo.
_EN_VEREDICTO = ("verifying mechanism", "judging")

#: Lo que imprime `run.stale_engine_refusal` cuando el plató lleva código viejo. El guarda hace lo correcto
#: —se NIEGA a medir— pero después nadie reinicia nada, y ese es el defecto: cada ronda siguiente vuelve a
#: negarse en ~45 s, así que el bucle parece vivo (el diario se llena, los escenarios rotan) y no mide NADA.
#: Medido el 2026-08-27: `search-buy-camera__es` INFRA en 45 s y solo siguió porque yo estaba mirando y
#: reinicié a mano. Con dos agentes empujando motor cada ~20 min, eso es un bucle parado disfrazado de bucle.
_PLATO_RANCIO = "no es el mismo codigo"


def _apunta(**fila) -> None:
    _SALIDA.mkdir(parents=True, exist_ok=True)
    fila["t"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with _DIARIO.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"[supervisor] {fila.get('escenario')} → {fila.get('resultado')} ({fila.get('segundos')}s)", flush=True)


def _sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_RAIZ,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def plato_de(escenario: str) -> str:
    """QUÉ PLATÓ le toca a este caso. El sufijo del id es la única fuente: `__us` corre en el plató US.

    `main()` no pasaba plató, así que se quedaba el `es` por defecto para TODO — y un caso de San Francisco
    lo conducía Marc, de Madrid, contestando en castellano dentro de un brief inglés. No falla: mide, y mide
    un tester que se contradice a sí mismo. Es la misma familia que el 2026-08-27 dejó 19 escenarios US
    respondiendo con realidad española, y no se ve desde fuera porque la ronda sale verde de infraestructura.
    """
    return "us" if escenario.endswith("__us") else "es"


def una_ronda(escenario: str, lab: str = "es") -> dict:
    """Lanza UNA ronda y la vigila. Devuelve el parte, con el motivo si hubo que cortarla."""
    _SALIDA.mkdir(parents=True, exist_ok=True)
    log = _SALIDA / f"{escenario}.log"
    sha, t0 = _sha(), time.time()
    with log.open("w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [sys.executable, "-m", "tests.use_cases.e2e.agent.run", "--lab", lab,
             "--scenario", escenario, "--rounds", "1", "--fresh"],
            cwd=_RAIZ, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)

    motivo, ultimo_tam, ultimo_cambio = "", -1, time.time()
    while True:
        if p.poll() is not None:
            break
        tam = log.stat().st_size if log.exists() else 0
        if tam != ultimo_tam:
            ultimo_tam, ultimo_cambio = tam, time.time()
        ahora = time.time()
        # ¿Ya está en el veredicto? Se mira solo la COLA del log: leerlo entero cada tres segundos es I/O
        # gratis multiplicado por horas, y estas dos señales salen al final por construcción.
        _cerca = ""
        try:
            with log.open("rb") as fh:
                fh.seek(max(0, tam - 4096))
                _cerca = fh.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        _techo = CAP_S + (VERIFICA_EXTRA_S if any(x in _cerca for x in _EN_VEREDICTO) else 0)
        if ahora - ultimo_cambio > HANG_S:
            motivo = f"hung: {HANG_S}s sin una línea nueva en el log"
        elif ahora - t0 > _techo:
            motivo = f"capped: la ronda pasó de {_techo}s"
        if motivo:
            # El grupo entero: el runner tiene hijos (el motor de plató, el navegador).
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:  # noqa: BLE001
                pass
            try:
                p.wait(timeout=20)
            except Exception:  # noqa: BLE001
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    pass
            break
        time.sleep(3)

    segundos = int(time.time() - t0)
    cola = ""
    try:
        cola = log.read_text(encoding="utf-8", errors="replace")[-2500:]
    except Exception:  # noqa: BLE001
        pass
    resultado = motivo.split(":")[0] if motivo else _veredicto_de_cola(cola)
    parte = {"escenario": escenario, "resultado": resultado, "segundos": segundos, "sha": sha,
             "motivo": motivo, "log": str(log)}
    _apunta(**parte)
    # Fuera del parte que va al diario a propósito: es una señal para el bucle, no un hecho del escenario, y
    # el diario es lo que lee el operador para decidir dónde trabajar.
    return dict(parte, _rancio=(_PLATO_RANCIO in cola))


def _veredicto_de_cola(cola: str) -> str:
    """Qué fue de la ronda, leído de lo que imprimió el runner. FUERA de la función que conduce la ronda a
    propósito: ahí dentro haría falta un plató entero para probarlo, y lo que decide es una cadena.

    Cuatro salidas y ninguna es un matiz de otra — cada una manda a mirar a un sitio distinto:

    * **PASS/FAIL** — hubo medida.
    * **BLOQUEADO** (V2-448) — el caso es de FUTURO: sus tareas de roadmap siguen pendientes, así que el
      runner se niega a conducirlo (norma del operador, 2026-08-21) y sale en 3 s. No hay nada roto y no hay
      nada que arreglar hoy.
    * **INFRA** (V2-363) — el instrumento se rompió. El runner imprime «PASSED 0/1» también cuando la ronda se
      corrió entera y el JUEZ no devolvió JSON: 10,7 min de navegador real quedaron apuntados como FAIL en el
      diario, que es la lista con la que se decide dónde trabajar.

    El orden importa: BLOQUEADO va ANTES que INFRA porque la cola de un caso bloqueado no contiene «PASSED»
    de ninguna clase y caería en el `else`, que es INFRA.
    """
    if "PASSED 1/1" in cola:
        return "PASS"
    if "no queda ningún caso conducible" in cola or "no se conducen" in cola:
        return "BLOQUEADO"
    if "INFRA" in cola or "el juez no devolvió JSON" in cola:
        return "INFRA"
    if "PASSED 0/1" in cola:
        return "FAIL"
    return "INFRA"


def _reinicia_plato(lab: str = "es") -> bool:
    """Baja y sube el plató para que corra el árbol de ahora. `True` si volvió a levantarse.

    Conserva puerto, memoria y perfil — es el mismo par de comandos que imprime el propio guarda del runner,
    no una segunda forma de reiniciarlo.
    """
    for cual in ("down", "up"):
        try:
            r = subprocess.run([sys.executable, "-m", "tests.use_cases.lab", cual, lab],
                               cwd=_RAIZ, capture_output=True, text=True, timeout=180)
        except Exception as e:  # noqa: BLE001
            print(f"[supervisor] no pude {cual} el plató: {e}", flush=True)
            return False
        if cual == "up" and r.returncode != 0:
            print(f"[supervisor] el plató no volvió a levantarse: {(r.stderr or r.stdout)[-200:]}", flush=True)
            return False
    return True


def intercala(ids: list[str]) -> list[str]:
    """Alterna los dos platós DENTRO de un grupo de prioridad, conservando el orden de cada uno.

    La prioridad («rotos primero, nunca-medidos después, los que pasan al final») es lo valioso de la
    rotación y no se toca. Lo que se arregla es que dentro de cada grupo el orden salía del diccionario del
    marcador, y ahí los `__us` quedaban en bloque: medido el 2026-08-28, el primer caso US estaba en la
    **posición 21** de 132 — a unas dos horas y tres cuartos de plató. Un bucle que corre toda la noche y no
    llega a tocar la mitad del catálogo no está midiendo esa mitad, aunque la tenga en la lista.

    Alternar y no barajar: barajar haría que dos vueltas seguidas no se puedan comparar, y la rotación es
    justamente lo que hace comparables las vueltas.
    """
    es = [x for x in ids if not x.endswith("__us")]
    us = [x for x in ids if x.endswith("__us")]
    fuera: list[str] = []
    for a, b in zip(es, us):
        fuera += [a, b]
    fuera += es[len(us):] + us[len(es):]      # el más largo termina de tirar solo
    return fuera


def rotacion() -> list[str]:
    """El orden en que se recorren, y el orden IMPORTA porque el tiempo de plató es el recurso escaso.

    `UC_ROTACION` (separado por comas) manda siempre — es el mando para clavar el foco en un caso mientras se
    itera sobre él. Sin ella, la rotación sale del MARCADOR (`status.json`), no del catálogo: de los 135 casos
    del catálogo solo ~32 tienen runner, y recorrer los otros 103 sería gastar el navegador en nada.

    Y dentro de los que corren, primero **los que fallan**, que es donde hay algo que ganar; los que ya pasan
    van detrás para que una regresión se vea, pero sin comerse el turno de los rotos. Los `capped` (les falta
    una credencial del usuario y no hay forma de llegar) quedan FUERA: el operador los excluyó del bucle de
    mejora en 2026-08-20 precisamente para que no le den trabajo que nadie puede cerrar.
    """
    env = (os.getenv("UC_ROTACION") or "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    try:
        import json as _j
        d = _j.loads((_RAIZ / "tests" / "use_cases" / "status.json").read_text(encoding="utf-8"))
        filas = (d.get("scenarios") or {}).items()
        rotos = [k for k, v in filas if str(v.get("state")) in ("FAIL", "INFRA")]
        buenos = [k for k, v in filas if str(v.get("state")) == "PASS"]
        # V2-367 — los que TIENEN runner y NUNCA se han medido. El marcador solo lista lo que ya corrió
        # alguna vez, así que sin esto un escenario nuevo es INVISIBLE para el bucle PARA SIEMPRE: nadie lo
        # corre, así que nunca entra en el marcador, así que nadie lo corre. Medido el 2026-08-27: 135
        # escenarios con runner, 32 en el marcador — **103 fuera del bucle**, y entre ellos los DOS de
        # multimedia (`play-music-and-build-playlist`, `watch-a-video-not-listen-to-it`), o sea dos
        # superficies enteras del producto sin una sola medida. Desde fuera esto no se ve como un hueco:
        # el escenario EXISTE, el catálogo lo lista, y el marcador —que es donde se mira— no dice que
        # falte. Es la familia de «un test fuera del mapa AFIRMA que corrió».
        try:
            # V2-448 — y FUERA los casos de FUTURO. El runner se niega a conducir uno cuyas tareas de roadmap
            # siguen pendientes (operador, 2026-08-21), así que sale en 3 s sin medir nada — pero como nunca
            # llega al marcador, `nunca` lo vuelve a elegir en cada vuelta, para siempre. Medido el
            # 2026-08-28: `repeat-a-finished-search` (pendiente de V2-260) gastando un turno de la rotación y
            # dejando una fila falsa en el diario. Mismo trato que los `capped`: trabajo que nadie puede
            # cerrar hoy no entra en el bucle de mejora. Vuelve solo cuando su iniciativa lo desbloquee.
            from tests.use_cases.e2e.agent import segments as _G
            nunca = [x.id for x in _con_runner()
                     if x.id not in dict(filas) and not _G.blocked_by(x.id)]
        except Exception:  # noqa: BLE001 — un catálogo ilegible NO puede costar la rotación entera
            nunca = []
        if rotos or buenos or nunca:
            # Rotos primero (donde hay algo que ganar y ya sabemos qué mirar), NUNCA MEDIDOS después
            # (información nueva, pero cada uno cuesta una ronda entera de plató), y los que pasan al final
            # para que una regresión se vea sin comerse el turno de nadie.
            # CADA PLATÓ CON SU PROPIA COLA DE PRIORIDAD, y alternando entre las dos.
            #
            # Intercalar DENTRO de cada grupo no bastaba, y se vio en las cifras: 25 rondas ES contra 7 US en
            # las cuatro primeras horas del 24/7. La causa es que ES tiene muchos más casos rotos, así que
            # tras agotar los US del grupo «rotos» quedaban trece ES seguidos ANTES de que empezara el grupo
            # «nunca medidos» —donde viven los 52 US que nadie ha tocado—. La prioridad se respetaba y el
            # operador seguía sin datos de US.
            #
            # Así cada plató recorre rotos → nunca → buenos por su cuenta, y se alternan turno a turno: la
            # prioridad sigue intacta DENTRO de cada locale, que es donde significa algo, y ninguno de los dos
            # puede quedarse esperando a que el otro termine su lista.
            cola_es = [x for x in rotos + nunca + buenos if not x.endswith("__us")]
            cola_us = [x for x in rotos + nunca + buenos if x.endswith("__us")]
            return intercala(cola_es + cola_us)
    except Exception:  # noqa: BLE001
        pass
    return ["search-buy-used-car"]


def _con_runner() -> list:
    """Los escenarios que TIENEN runner, o lista vacía si el catálogo no se puede leer.

    Aparte para que `rotacion()` siga dando la vuelta conocida si esto falla: quedarse sin rotación es peor
    que quedarse sin los nunca-medidos.
    """
    try:
        from tests.use_cases.e2e.agent.scenarios import all_scenarios
        return list(all_scenarios())
    except Exception:  # noqa: BLE001
        return []


# ── V2-372: EL SUPERVISOR SE RECARGA A SÍ MISMO ─────────────────────────────────────────────────────────────
# Un proceso de Python no vuelve a leer su propio fichero. Éste llevaba desde las 08:03 corriendo el código de
# las 07:59, así que DOS arreglos suyos de esa misma mañana estuvieron inertes sin que nada lo dijera:
# V2-363 (una avería del arnés no es un caso que falla — 09:42) y V2-367 (los 103 escenarios que nunca habían
# corrido — 10:12). Medido: la ronda de `things-to-do-nearby-weekend__es` es INFRA en su informe —el juez no
# devolvió JSON tras tres intentos— y el diario la apuntó FAIL, exactamente lo que V2-363 arregló tres horas
# antes. Y la rotación seguía siendo la de 32.
#
# Lo que hace esto MUDO es la asimetría: `una_ronda` lanza la ronda como SUBPROCESO, así que el runner, el
# juez, los escenarios y el motor entero SÍ se recargan cada vez. Solo se queda atrás este fichero — el que
# clasifica el resultado y elige el orden. Desde fuera todo parece al día, y el parte hasta lleva el `sha` de
# HEAD leído al empezar la ronda: el diario AFIRMA haber medido un commit cuyo clasificador no estaba cargado.
#
# Es la cuarta vez de la misma familia («árbol limpio no es proceso al día») y la primera en la que quien lo
# paga es el instrumento con el que se decide dónde trabajar.
_FUENTE = Path(__file__).resolve()


def _huella() -> str:
    try:
        return _hashlib.sha256(_FUENTE.read_bytes()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return ""


def _fuente_utilizable() -> bool:
    """¿El fichero nuevo al menos COMPILA? Re-ejecutar sobre un fichero a medio escribir mataría el bucle, y
    el bucle no puede pararse — es el único requisito que el operador ha repetido. Ante la duda, se sigue con
    el código viejo: medir con algo desfasado es un defecto, quedarse sin medir es peor."""
    try:
        compile(_FUENTE.read_text(encoding="utf-8"), str(_FUENTE), "exec")
        return True
    except Exception:  # noqa: BLE001
        return False


def _recargar_si_cambie(huella_inicial: str) -> None:
    """Entre rondas —nunca a mitad de una— vuelve a arrancarse con el código nuevo. No-op si nada cambió."""
    if not huella_inicial or _huella() in ("", huella_inicial):
        return
    if not _fuente_utilizable():
        print("[supervisor] la fuente cambió pero NO compila — sigo con la cargada", flush=True)
        return
    _apunta(escenario="—", resultado="RECARGA", segundos=0, sha=_sha(),
            motivo=f"supervisor.py cambió ({huella_inicial} → {_huella()}); me reinicio con el código nuevo",
            log="")
    os.execv(sys.executable, [sys.executable, "-m", "tests.use_cases.e2e.agent.supervisor"])


def main() -> int:
    orden = rotacion()
    _mia = _huella()
    print(f"[supervisor] {len(orden)} escenarios · hang={HANG_S}s cap={CAP_S}s · diario={_DIARIO} "
          f"· fuente {_mia} · HEAD {_sha()}", flush=True)
    i = 0
    while True:
        esc = orden[i % len(orden)]
        i += 1
        try:
            parte = una_ronda(esc, plato_de(esc))
            if parte.get("_rancio"):
                # UNA sola vez, y sin bucle: si tras reiniciar sigue rancio, la ronda entra como INFRA y se
                # pasa al siguiente. Reintentar hasta que cuadre convertiría un plató que no arranca en un
                # bucle infinito que no mide — el mismo fallo con otra cara.
                _apunta(escenario=esc, resultado="RECARGA-PLATO", segundos=0, sha=_sha(),
                        motivo="el plató corría código viejo; lo reinicio y repito la ronda", log="")
                if _reinicia_plato(plato_de(esc)):
                    una_ronda(esc, plato_de(esc))
        except Exception as e:  # noqa: BLE001 — el supervisor NUNCA muere por una ronda
            _apunta(escenario=esc, resultado="ERROR", segundos=0, sha=_sha(), motivo=str(e)[:200], log="")
        time.sleep(PAUSA_S)
        _recargar_si_cambie(_mia)


if __name__ == "__main__":
    raise SystemExit(main())
