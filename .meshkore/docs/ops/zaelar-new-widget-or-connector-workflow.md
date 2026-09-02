<!--
Canonical workflow for SHIPPING A NEW WIDGET and/or A NEW CONNECTOR, end to end.
Written 2026-09-02 from the V2-557 build (cloud files: Google Drive + OneDrive + the `archivos` explorer),
which is the reference implementation every step here points at. Every trap listed in §11 was hit in that
build — they are not hypothetical, and each one costs more than the step that prevents it.
-->

# Nuevo widget / nuevo conector — el workflow completo

**Trigger:** *«añade un conector de X»*, *«haz un widget de Y»*, *«pasa el workflow de widget nuevo»*.

Lo que sigue son TODAS las acciones, en orden, para que una pieza nueva quede construida, conectada,
probada, documentada y en el contexto. La regla que lo gobierna: **una pieza que no está cableada en TODOS
sus puntos no falla con ruido — sale VACÍA**, y una superficie vacía se diagnostica como otra cosa. Por eso
la mitad de este documento es una lista de sitios que tocar, no de código que escribir.

## 0. ¿Qué workflow es este? (filtro de alcance)

| Si vas a… | Sigue |
|---|---|
| **crear una pieza NUEVA** (widget, conector, o los dos) | **este documento** |
| cambiar el SISTEMA de widgets (contrato de manifest, despacho, storage, gate) | `zaelar-widgets-workflow.md` |
| cambiar un widget que ya existe, dentro de su carpeta | su `notes.md` y nada más |
| cerrar cualquier tanda que cambie comportamiento | `../../../.meshkore/docs/ops/zaelar-initiative-closure.md` (raíz) |

---

## 1. Antes de escribir una línea — cuatro decisiones

Contéstalas por escrito en la iniciativa. Las cuatro tienen una respuesta por defecto, y la respuesta por
defecto es casi siempre la correcta; lo caro es no haberlas hecho.

**1.1 ¿Widget, conector, o los dos?** Un CONECTOR habla con el mundo exterior y no tiene pantalla. Un WIDGET
es una superficie y no debería saber con quién habla. Si necesitas los dos, sepáralos desde el minuto uno con
una **fachada agnóstica del proveedor** que devuelva UNA forma normalizada (`connectors/files/service.py` es
el modelo). La prueba de que la frontera está bien puesta: *añadir un segundo proveedor toca el registro y un
módulo cliente, y CERO líneas del widget*.

**1.2 ¿Hace falta una tool nueva del FlashBrain? Casi siempre NO.** El catálogo de tools viaja ENTERO en cada
turno, incluido el que dice «hola», y tiene techo con test. **Las acciones declaradas de un widget SON sus
skills** — el FlashBrain las ejecuta con la tool genérica `widget_data` que ya existe, y una entrada de
catálogo cuesta UNA línea de prompt, no una plaza de tool (V2-526). Una tool nueva solo se justifica si la
capacidad **no tiene widget** (`web_search`, `recall`). Si añades una, hay que recortar otra: el techo está
en `tests/agent_headless/unit/flash/test_router.py`.

**1.3 ¿Corre en BACKGROUND?** (V2-034 obliga a decidirlo, no a omitirlo.) ¿Cambian sus datos solos, fuera de
pantalla, de forma que el operador podría preguntar por voz sin abrir la tarjeta? Un buzón, un feed, el
tiempo → **sí**: declara `"background": {"every": "…"}` y escribe `tick(ctx)`, volcando a memoria por `ctx`.
Un explorador, un buscador, un gráfico → **no**, y escríbelo con su motivo (en `archivos`: sondear la nube de
alguien gasta cuota de API para contestar una pregunta que nadie ha hecho).

**1.4 ¿PRODUCE algo?** (V2-092.) ¿Sigue haciendo algo cuando el operador deja de mirar — audio, vídeo,
grabación, un proceso vivo? Si sí, declara `runtime{output, produce[], suspend, active_when}` o tu widget
seguirá sonando con el agente PARADO. Si no, no declares nada: un medio *recibido* (una foto, un QR) es
contenido pasivo, no producción.

---

## 2. El conector — los ficheros y su orden

Se construye **de abajo arriba**, y cada capa se prueba antes de escribir la de encima.

```
connectors/<familia>/
├─ providers.py    ①  el REGISTRO tipado: un entry por proveedor con endpoints, ámbitos y capacidades
├─ oauth.py        ②  el flujo (si lleva OAuth) — reutiliza connectors/oauth_pkce.py + secure_json_store.py
├─ <proveedor>.py  ③  un cliente por proveedor: habla HTTP, devuelve la FORMA NORMALIZADA, nada más
├─ service.py      ④  la fachada AGNÓSTICA — lo único que ve el resto del sistema
├─ server_api.py   ⑤  el plano de control (`/api/<algo>/*`): status · connect · callback · disconnect
└─ __init__.py
```

- **① `providers.py`** — todo lo que distingue a un proveedor va aquí como DATO, nunca como `if` repartido.
  Si un proveedor tiene tramos de permiso con consecuencias distintas, **eso es un campo**, no una constante
  (en V2-557 el tramo decide si el árbol se puede listar siquiera). `public_list()` devuelve la vista
  redactada para el frontend: etiquetas y notas, **jamás endpoints ni credenciales**.
- **② `oauth.py`** — PKCE S256 desde `connectors/oauth_pkce.py`; tokens por `SecureJsonStore` (escritura
  atómica + chmod 600) en `.meshkore/credentials/<x>.json`, **gitignoreado**. Guarda junto al token **qué
  permiso se concedió**: el callback solo trae `code` y `state`, así que lo que elija el operador tiene que
  viajar en el `state`. Un `refresh` que no devuelve `refresh_token` **conserva el anterior** o desconectas al
  operador horas después.
- **③ los clientes** — que devuelvan las MISMAS claves. Hay un test que lo exige; sin él la fachada es una
  ilusión. Escapa lo que el operador escribe antes de meterlo en el lenguaje de consulta del proveedor.
- **④ `service.py`** — **fail-safe siempre**: `{"ok": False, "error": "…"}`, nunca una excepción hacia
  arriba. Un proveedor caído degrada a una tarjeta que lo dice; jamás se lleva por delante un turno de voz.
  Y **distingue lo que no es un error**: si una respuesta legítima produce el mismo vacío que un fallo,
  devuelve `ok` **con un `reason`** — ver §11-T1, que es el trap más caro de esta familia.
- **⑤ `server_api.py`** — **comprueba que el prefijo está libre antes de elegirlo**
  (`grep -rn '"/api/<algo>' server/ connectors/`). Dos routers en un prefijo los resuelve FastAPI por orden de
  montaje, en silencio.

---

## 3. El widget — los ficheros y su orden

```
widgets/<id>/
├─ manifest.json   identidad, acciones declaradas, alias, tamaño
├─ data.py         view_data · apply_action · ref_index · prompt_digest
├─ widget.js       render(el, data, ctx)
├─ notes.md        el registro de decisiones de ESTE widget (léelo antes de tocarlo, escríbelo después)
├─ golden.json     lo graba el harness solo — bórralo si cambias la forma de view_data a propósito
└─ __init__.py     vacío
```

- **`view_data(q)` es la ruta CALIENTE**: corre en cada render Y otra vez en cada push de SSE. Sirve la
  CACHÉ. Nada de red ahí dentro. Toda llamada al mundo exterior vive en `apply_action`, que corre una vez por
  intención del operador.
- **`apply_action` DEVUELVE lo que encuentra.** Una acción que solo repinta deja al turno sin nada que decir:
  «¿tengo un contrato de Axa?» es una PREGUNTA (V2-541). Devuelve `matches` y el turno puede nombrarlos.
- **Un error de acción ENSEÑA la forma del reintento** — qué campo falta, qué acciones existen — y nombra la
  salida. Un «no» que no dice cómo salir se diagnostica como una avería (V2-473, V2-463).
- **`ref_index()`** si alguna acción apunta a un item por id: el modelo NUNCA inventa ids (V2-026). Da un
  `field` DISTINTO por clase de item, o «abre el presupuesto» entrará en la carpeta que se llama como el
  fichero.
- **`prompt_digest()`** si con la tarjeta abierta tiene sentido contestar sobre su contenido sin ida y vuelta.
  Acótalo y **di que está acotado** («y 12 más»): un listado truncado que no lo dice se lee como el total.

---

## 4. El cableado — la lista de sitios que fallan VACÍOS

**Esta es la sección que más tiempo ahorra.** Ninguno de estos puntos da error si se olvida; todos producen
una superficie vacía o una capacidad invisible.

| # | Toca | Si lo olvidas |
|---|---|---|
| 1 | `connectors/registry.py` → añade `_<familia>()` **y mételo en `descriptors()`** | el conector no existe para el ⚙ ni para nadie |
| 2 | `server/__init__.py` → import + **la lista `routers`** | el plano de control contesta 404 y parece un bug de red |
| 3 | `widgets/registry.py::_BUILTINS` | el widget se marca «tuyo» en vez de «de serie» |
| 4 | `ConfigPanel.js` → tarjeta del conector **y la lista `fams`** | las tarjetas existen y NADIE las renderiza |
| 5 | `frontend/app/services/api.js` | el botón del panel no tiene a quién llamar |
| 6 | `i18n/bundles/en.json` **y** `es.json` | `t()` devuelve la CLAVE, que es truthy: sale `config.cx.fam_files` en pantalla |
| 7 | `widgets/validator.py::_STDLIB_EXEMPT` si `data.py` importa un conector | `make test-widgets` en rojo para todo el mundo |
| 8 | `tests/run_testmap.py` | los tests existen y **no los corre nadie** |

**Regla de oro del cableado:** cada vez que una capa LEE un campo, comprueba que la capa que lo escribe lo
manda. En V2-557 esto falló **tres veces seguidas** con la misma forma — el panel del widget leía `tiers`, la
tarjeta del ⚙ leía `tiers`, y el registro no los mandaba. La comprobación es de diez segundos:
`grep -n "<campo>"` en el productor y en el consumidor.

---

## 5. Las skills del FlashBrain — cómo se declara la capacidad

Todo esto vive en `manifest.json`, y todo esto es lo que el modelo ve.

- **`actions`**: una entrada por acción, **ni una más ni una menos** que las que maneja `apply_action`. El
  gate de validación RECHAZA cualquiera de los dos descuadres. Una acción no declarada es INVISIBLE aunque
  funcione; una declarada que nadie maneja es una entrada muerta.
- **`"view": true`** en toda acción que solo cambia lo que se ve. Es lo que permite que «ábreme el Drive»
  *liste* en vez de limitarse a levantar la tarjeta (V2-545). ⚠️ **La primera pregunta al marcarlas no es
  cuáles son lentes, sino CUÁL CONTESTA LA FRASE PARA LA QUE EXISTE EL WIDGET** — esa es justo la que una
  pasada opt-in se salta, y saltársela deja la tarjeta abierta y vacía (V2-547).
- **`"confirm": true`** solo si es irreversible de verdad (pagar, enviar, publicar, borrar). Lo reversible va
  desnudo.
- **`usage`**: cómo conducir el widget — qué acción para qué intención. Va al prompt; que sea corto.
- **`whenToUse`**: la línea de ENRUTADO. **Tiene presupuesto: 300 caracteres** (`widgets/brief._PURPOSE_CAP`),
  y lo que se corta es el final, que es donde está la cláusula FRONTERA. Escríbela para CABER y compruébalo
  con un test contra `brief._purpose`, no a ojo (V2-547).
- **`keywords` / `aliases`**: precisos y no solapados. El harness avisa de colisiones; la validación rechaza
  un manifest cuyas keywords sean TODAS de otros.
- **`worker_guide`** si un Brain Worker debe entregar aquí: dile los DOS pasos (escribe el JSON a un fichero
  relativo con Write, después `python -m nucleo.widget_cli data <id> <acción> @fichero`). Pegar JSON en la
  línea de comandos lo bloquean las comillas y el guarda del shell.

---

## 6. Las fronteras que no se cruzan

1. **La voz transporta INTENCIÓN, nunca una credencial** (V2-520). Ningún `payload` de acción lleva
   `client_secret`, `token` ni `password`. El registro de la app se hace UNA vez en ⚙ → Conectores. Ponlo bajo
   test: la voz llega exactamente a esos payloads.
2. **`widget.js` no toca la red.** Ni `fetch`, ni WebSocket, ni `import()` dinámico. Si hace falta arrancar
   algo exterior (un consentimiento OAuth), lo hace una **acción declarada** que devuelve la URL y el card la
   abre. Abre la ventana SÍNCRONAMENTE en el clic y rellena su `location` después, o el navegador la bloquea.
3. **Todo texto de fuera es UNTRUSTED**: `textContent` y `createElement`, nunca `innerHTML`. Un fichero
   llamado `<img onerror=…>` es un nombre legal en todos los proveedores.
4. **Los widgets no se hablan entre sí.** Devuelve los datos y que decida el CEREBRO. Nada de importar otro
   widget desde el tuyo.
5. **`data.py` es stdlib.** Si tu widget ES un conector y no hay equivalente de stdlib, entra en la lista
   curada `_STDLIB_EXEMPT` **con su motivo escrito**, y deja el import DIFERIDO dentro de las funciones para
   que el import del módulo —y por tanto el catálogo, y por tanto cada prompt— no pague `httpx`.
6. **Cada widget escribe solo en `widgets/_data/<su-id>/`.** Nunca fuera.
7. **Frontera público/privado**: `engine/` es PÚBLICO. Aquí se describe el MECANISMO; los precios, las
   políticas de cuenta y lo que la nube puede o no contratar van al `.meshkore/` de la RAÍZ.

---

## 7. Los tests — el set completo

Son **cuatro clases** y la cuarta es la que casi siempre falta.

| clase | dónde | qué prueba |
|---|---|---|
| **conector** | `tests/connectors/unit/<familia>/` | el RAZONAMIENTO alrededor del HTTP: los estados que se parecen, los fallos de proveedor, la normalización |
| **contrato del widget** | `tests/browser/unit/<id>/` | declarado==manejado · `view` · sin credenciales en payloads · `whenToUse` cabe · `view_data` no toca la red |
| **renderizado** | `tests/browser/e2e/widgets/test_<id>_render.py` | lo que ninguna lectura del fuente puede dar (ver abajo) |
| **VIVO** | el mismo directorio, nodo `live: True` | la ida y vuelta real contra la cuenta del operador |

**El renderizado no es decoración.** `t()` devuelve la CLAVE cuando falta una traducción y la clave es
truthy; un handle de DOM escrito como `cond ? a : b` deja un canvas desconectado sin ningún error; un aviso
puede existir en el DOM con altura CERO. Nada de eso lo ve un test de fuente. Y si tu widget pinta texto de
fuera, **renderiza un nombre hostil y afirma que no nació ningún elemento**.

**El test VIVO** — cuando la pieza necesita una cuenta real:
- Va en un nodo **`"live": True`**, que `deterministic_paths()` excluye: no corre en CI y no se pone rojo en
  una máquina sin cuenta.
- **SALTA con los pasos exactos para habilitarlo.** *Pendiente* es un estado legítimo; lo que no vale es pasar
  en vacío y confundirse con cobertura.
- **Nunca afirma ni imprime contenido del operador.** Este repo es público y sus informes ya filtraron datos
  personales una vez. Se afirma FORMA e INVARIANTES, jamás lo que la persona tiene.
- Aunque no se pueda ejecutar, **el circuito se construye entero**: el día que haya credencial no hay que
  escribir nada.

**Los desarmes son obligatorios.** Por cada decisión, rompe el código y comprueba que el test se pone ROJO —
y **AFIRMA que la mutación se aplicó** antes de medir: un desarme verde es una mutación mal hecha hasta que
se demuestre lo contrario. Cuenta cuántos tests corrieron; en zsh un parámetro sin comillas no se parte en
palabras y `pytest $T` con dos rutas dentro corre *«no tests ran»* mientras parece verde.

**Registra los ficheros en `tests/run_testmap.py`.** Un fichero nuevo necesita su línea **aunque el directorio
ya esté cubierto**: el mapa lista rutas explícitas, no hace glob. Comprueba después:

```bash
./.venv/bin/python -c "from tests.platform import catalog; p=set(catalog.deterministic_paths('all')); \
  print('unit', '<ruta unit>' in p); print('live excluido', '<ruta live>' not in p)"
```

---

## 8. La documentación — tres sitios, nunca dos de tres

1. **Doc de módulo** — `engine/.meshkore/docs/modules/zaelar-<pieza>.md`: anatomía, contrato, las decisiones
   con su porqué. Público → solo mecanismo.
2. **Iniciativa** — `engine/.meshkore/roadmap/initiatives/V2-NNN-….md`. **Reserva el número al cogerlo**
   (`git log --all --oneline -15 | grep -oE "V2-[0-9]+"`, y anúncialo en el cluster): dos agentes con el mismo
   número se pisan los ficheros.
3. **`engine/CLAUDE.md`** — la decisión, en «Decisiones clave», con lo que se midió y lo que quedó abierto. Un
   trinquete (`test_roadmap_closure.py`) exige que toda iniciativa entregada esté citada y viceversa: cualquiera
   de las dos mitades sola deja el contexto contando media historia.
4. Más el **`notes.md`** del widget, que es lo que impide que la próxima sesión deshaga una decisión ya tomada.
5. Si la pieza cruza a la nube o al negocio, **parte en dos**: el mecanismo aquí, el producto en
   `.meshkore/roadmap/initiatives/INI-xxx` de la RAÍZ.

---

## 9. Commit y push — con varios agentes en el mismo árbol

El árbol lo comparten varias sesiones y **el índice de git es COMPARTIDO**.

```bash
git status --short                       # ¿de quién es cada cosa?
git diff --cached --name-only            # si trae ficheros ajenos, alguien llenó el índice
git diff <fichero>                       # el pathspec limita FICHEROS, no HUNKS
git add <rutas nuevas> && git commit -m "…" -- <rutas>    # ⚠️ EN UN SOLO COMANDO
git push origin main
```

- **`git commit` a secas commitea el ÍNDICE ENTERO.** Usa siempre `git commit -m "…" -- <rutas>`.
- ⚠️ **Los ficheros NUEVOS necesitan `git add`, y ese `add` abre una ventana** en la que un `git commit` a
  secas de OTRA sesión se los lleva dentro de su commit. Pasó en V2-557. Haz `add` y `commit` **en el mismo
  comando** y no dejes nada preparado entre medias.
- Las opciones van ANTES de `--`; después de `--` todo es una ruta.
- Si ya está pusheado y la atribución quedó mal: **no se reescribe `main`**. El código no se pierde; avisa al
  peer y sigue.
- **Commitea pronto**, incluso antes de probar. Perder código no es reversible.

---

## 10. Verificación en vivo

Un test verde no es un producto que funciona.

```bash
./zaelar status                          # ¿corre HEAD?
./zaelar restart                         # NUNCA con voz viva ni con una batería midiendo
```

- Comprueba las rutas con una **petición real** (`TestClient` o `curl`), no leyendo `app.routes`: en esta
  versión de FastAPI los routers incluidos se guardan envueltos y **parece que no hay rutas** (§11-T5).
- Abre la tarjeta y MÍRALA.
- Escribe qué quedó **sin verificar en vivo**. Es la mitad honesta del informe.

---

## 11. Los traps — todos medidos en V2-557

| | Trap | Qué cuesta |
|---|---|---|
| **T1** | Un estado legítimo que produce el MISMO vacío que un fallo | «tu Drive está vacío» a quien lo tiene lleno, y el defecto se diagnostica como conector roto. **Devuelve `ok` + `reason`.** |
| **T2** | Un consumidor lee un campo que su productor no manda | La superficie sale vacía, sin error. Pasó **3 veces** en un solo build. `grep` el campo en ambos lados. |
| **T3** | Añadir la tarjeta y olvidar la lista de familias del ⚙ | La tarjeta existe y no la renderiza nadie |
| **T4** | `whenToUse` > 300 chars | Se corta la cláusula FRONTERA y el enrutado se pierde justo donde importa |
| **T5** | Verificar el montaje leyendo `app.routes` | Da `[]` con las rutas perfectamente montadas → «arreglas» algo que funciona |
| **T6** | Un test que escanea el fuente y casa con sus propios COMENTARIOS | Rojo eterno en un fichero que documenta la regla. Afirma el PATRÓN (`.innerHTML =`), no la palabra |
| **T7** | Un doble de test demasiado generoso | Mi `breadcrumb` falso devolvía 2 niveles para todo, así que el test de «subir desde 1 nivel» afirmaba el padre equivocado |
| **T8** | `git add` en un árbol compartido | Otra sesión se lleva tus ficheros en SU commit |
| **T9** | Fichero de test nuevo sin línea en el testmap | Verde y **nadie lo ejecuta** |
| **T10** | Elegir un prefijo `/api/` ya usado | Dos routers, uno gana por orden de montaje, en silencio |

---

## 12. La checklist (para copiar y pegar al cerrar)

```
CONECTOR
[ ] providers.py: los proveedores son DATO; las diferencias, campos
[ ] oauth.py: PKCE compartido · tokens en el credential store (600, gitignored) · el permiso viaja con el token
[ ] cliente por proveedor → MISMA forma normalizada (con test)
[ ] service.py: fail-safe · lo-que-no-es-un-error devuelve ok+reason
[ ] server_api.py: prefijo /api libre (comprobado con grep)

WIDGET
[ ] manifest: acciones == apply_action · view en la que CONTESTA · confirm solo si es irreversible
[ ] whenToUse cabe en 300 (test contra brief._purpose) · usage · alias · keywords sin colisión total
[ ] view_data barato (sin red) · apply_action devuelve lo que encuentra · errores que enseñan la forma
[ ] ref_index si hay ids · prompt_digest si procede (acotado y diciendo que lo está)
[ ] background: decidido y escrito · runtime{} si produce
[ ] widget.js: sin fetch · sin innerHTML · textContent · clases con prefijo propio · tema por --hb-*

CABLEADO  (los 8 puntos de §4, uno a uno)
[ ] registry conectores + descriptors()   [ ] server routers      [ ] _BUILTINS
[ ] ConfigPanel tarjeta + fams            [ ] api.js              [ ] i18n en+es
[ ] _STDLIB_EXEMPT si procede             [ ] run_testmap.py

TESTS
[ ] conector · contrato · RENDERIZADO · vivo (live:True, salta con instrucciones)
[ ] desarmes con la mutación AFIRMADA, y cuántos tests corrieron
[ ] make test-widgets verde · el nodo nuevo en deterministic_paths, el live fuera

DOCS
[ ] doc de módulo   [ ] iniciativa V2-NNN (número reservado)   [ ] CLAUDE.md   [ ] notes.md
[ ] mecanismo aquí / producto en la raíz privada

CIERRE
[ ] add+commit en UN comando, con pathspec · push
[ ] verificado en vivo, y escrito lo que NO se pudo verificar
```
