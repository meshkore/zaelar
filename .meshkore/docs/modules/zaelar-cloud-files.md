<!--
Canonical module doc for the cloud-file connectors + the `archivos` explorer (V2-557, 2026-09-02).
PUBLIC repo: this describes the MECHANISM. What the paid product may or may not ship, and what an audit
costs, is business and lives in the workspace root's private `.meshkore/` (INI-027).
-->

# Archivos en la nube — conectores + explorador

Zaelar entra en el disco en la nube del operador (Google Drive, OneDrive) para **leer**: navegar carpetas,
buscar por nombre o contenido, y abrir la ficha de un archivo. Se conduce con el ratón y por voz.

## Las dos piezas y la frontera entre ellas

```
connectors/files/          el mundo exterior            widgets/archivos/        la superficie
├─ providers.py   registro tipado                       ├─ manifest.json   13 acciones declaradas
├─ oauth.py       PKCE, un token por proveedor          ├─ data.py         caché + acciones
├─ gdrive.py      Drive v3                              ├─ widget.js       explorador + asistente
├─ onedrive.py    Microsoft Graph                       └─ notes.md
├─ service.py     ◀── LA FACHADA AGNÓSTICA ──▶
└─ server_api.py  /api/cloudfiles/*
```

**El widget no sabe con quién habla.** `service.py` devuelve UNA forma normalizada y nada más:

```
{id, name, kind: "folder"|"file", mime, size|None, modified, web_url, provider}
```

Un tercer proveedor es un módulo cliente y una fila del registro: **cero líneas en el widget**. Hay un test
que exige que los dos clientes emitan exactamente las mismas claves — sin él la fachada sería una ilusión.

`size` es `None` y no `0` para lo que no tiene tamaño (una carpeta, un documento nativo de Google): «0 B»
junto a un documento real es una afirmación, y es falsa.

## El TRAMO DE PERMISO es el diseño, no una constante

Es lo único que hay que entender antes de tocar nada aquí, y los dos proveedores no están en la misma
situación. Como MECANISMO —lo que la API hace, no lo que nosotros podemos vender:

| proveedor | tramo | qué ve | ¿puede navegar? |
|---|---|---|---|
| Google Drive | `drive.file` | solo lo que la app creó o el usuario eligió a mano | **NO** |
| Google Drive | `drive.readonly` | todo, solo lectura — ámbito **restringido** de Google | sí |
| OneDrive | `Files.Read` + `offline_access` | todo, solo lectura | sí |

Google exige una evaluación de seguridad (CASA) antes de que una app **publicada** pida el ámbito
restringido; quien usa **su propio cliente OAuth** con su propia cuenta no está publicando nada. Por eso el
tramo es una elección **por instalación** y no un valor fijo, viaja pegado al token, y el asistente lo enseña
**antes** de dar el consentimiento y no después de que el disco parezca vacío. Microsoft Graph no pide nada
equivalente para OneDrive personal: un solo tramo.

### Y su consecuencia, que es la decisión más importante del módulo

Un token con el tramo estrecho **contesta 200 con una lista vacía**, que es indistinguible de «esta carpeta
está vacía». Así que `service.py` responde en ese caso `ok: True`, cero entradas **y un `reason`**, y la
tarjeta imprime el motivo. Colapsar esos dos estados es cómo se le enseña «tu Drive está vacío» a quien lo
tiene lleno, y cómo el defecto se diagnostica como un conector roto en vez de como un permiso estrecho.

## Las skills — sin ninguna tool nueva

Las **13 acciones declaradas** del manifest SON las skills; el FlashBrain las ejecuta con la tool genérica
`widget_data` que ya existe. Un catálogo de conectores no puede encarecer un turno que no los menciona
(V2-526): una entrada cuesta una línea de prompt, no una plaza de tool.

| acción | para qué |
|---|---|
| `open_folder` · `go_up` · `go_home` | navegar |
| `search_files` | buscar **y CONTESTAR** — devuelve los que casan en `result.matches` |
| `open_file` | la ficha de uno, con su `web_url` |
| `refresh` · `clear_search` · `set_view` · `set_provider` | estado de la vista |
| `open_connectors` · `close_connectors` · `connect_provider` · `disconnect_provider` | el asistente |

Todas las de navegación llevan `"view": true`, que es lo que hace que «ábreme el Drive» LISTE en vez de
limitarse a levantar la tarjeta (V2-545). `disconnect_provider` es la única con `confirm`.

`ref_index()` da un `field` distinto por clase — `folderId` para carpetas, `fileId` para archivos — o «abre
el presupuesto» entraría en la carpeta que se llama como el fichero. `prompt_digest()` pone el listado
delante del cerebro **mientras la tarjeta está abierta**, así «¿qué hay aquí?» es una pregunta sobre texto
que ya tenemos.

## Dónde ocurre la red

En `apply_action` y en ningún otro sitio. `view_data` corre en cada render **y otra vez en cada push de
SSE**, así que una llamada ahí sería una ida y vuelta HTTP por repintado: sirve la caché y publica
`needs_refresh`, y la tarjeta pide un listado UNA vez al montarse si está rancia. **Sin `tick`**: sondear la
nube de alguien gasta cuota para contestar una pregunta que nadie ha hecho.

`data.py` importa el conector —lo que normalmente está prohibido— porque este widget ES un conector y no hay
equivalente de stdlib para un token que se refresca en el credential store. Está en la lista curada
`widgets/validator.py::_STDLIB_EXEMPT`, junto a `musica`, y el import es **diferido** para que el catálogo no
pague `httpx` en cada turno.

## Las credenciales

El operador registra **su propia** aplicación OAuth una vez (Google Cloud / Microsoft Entra) y pega el
`client_id` en ⚙ → Conectores. Se guarda en el credential store; los tokens viven en
`.meshkore/credentials/files_oauth.json` (chmod 600, gitignoreado) y **no salen del proceso**.

**La voz transporta intención, nunca una credencial** (V2-520): ningún payload de acción admite un
`client_secret` — hay un test que lo prohíbe, porque la voz llega exactamente a esos payloads. Por eso el
asistente de la tarjeta ofrece *conectar* y *desconectar*, y el registro de la app vive en la configuración.

`widget.js` no toca la red: el consentimiento lo arranca una acción declarada que devuelve la URL, y la
tarjeta abre la ventana **síncronamente en el clic** (rellenando su `location` después) o el navegador la
bloquea.

## Lo que NO hace

- **No escribe.** Solo lectura, en los dos proveedores.
- **No habla con otros widgets.** `open_file` devuelve metadatos y `web_url`; si eso acaba siendo un
  documento en el canvas o una página en el navegador **lo decide el cerebro**.
- **No tiene iCloud Drive**, y no es cuestión de esfuerzo: CloudKit solo da acceso al contenedor de la propia
  app, nunca al iCloud Drive del usuario, y no hay API pública de terceros.
- **No descarga por defecto.** `service.download()` existe, con tope, para cuando un turno tenga que entregar
  un fichero a otra superficie; el explorador no lo usa.

## Probarlo

```bash
./.venv/bin/python -m pytest tests/connectors/unit/files tests/browser/unit/archivos \
    tests/browser/e2e/widgets/test_archivos_render.py -q          # 59, deterministas
./.venv/bin/python -m pytest tests/connectors/unit/files/live_cloud_drive_roundtrip.py -v
```

El segundo es el nodo **5.8**, marcado `live`: excluido de CI, **SALTA con los pasos para habilitarlo**
mientras no haya una cuenta conectada con permiso de navegación. Nunca afirma ni imprime un nombre de
fichero — este repo es público.
