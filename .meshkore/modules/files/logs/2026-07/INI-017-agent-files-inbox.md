---
id: INI-017
title: "Nuevo módulo files/ — inbox de archivos pegados/arrastrados desde el frontend"
status: implemented
priority: medium
owner: ricart
initiative: INI-017
created: 2026-07-07
updated: 2026-07-08
---

# Carpeta de archivos del agente (paste-imagen + drag&drop)

## Qué se pidió

El operador quería poder darle a zaelar una imagen o cualquier archivo sin fricción: **pegar** una imagen
(Ctrl/Cmd+V) en cualquier parte de la interfaz, o **arrastrar** un archivo a la ventana, y que quedara accesible
para que Hermes (y en el futuro el frontend/otros brains) pudieran trabajar con él — leerlo, resumirlo, analizar
capturas de pantalla, y a futuro reenviarlo (p. ej. por email). Explícitamente NO quería tener que abrir nada
para lograrlo ("aunque no se abra"), y pidió que de momento la carpeta de archivos fuera **plana y sin
organización**, dejando cualquier widget de navegación para más adelante.

## Decisiones tomadas (con el operador, antes de programar)

1. Visión de Hermes sobre archivos/imágenes: **guardar + que Hermes lea el fichero con sus propias tools**
   (ya auto-aprobadas en turnos de voz/chat), en vez de intentar verificar/forzar soporte de adjuntos en el
   protocolo ACP (no está implementado ni verificado en este repo).
2. Sin widget de gestión por ahora — se creará dinámicamente en el futuro si hace falta navegar/presentar los
   archivos.
3. Alcance: paste-imagen y drag&drop de archivos, **juntos**, en una sola entrega.
4. Aclaración posterior del operador: la carpeta va **dentro del repo**, se llama `files/`, plana, sin
   organización — Hermes y el frontend deben poder leer lo que hay ahí.

Detalle completo de la investigación (por qué NO multimodal, qué soporta livekit-agents/ACP/duo hoy) y la
arquitectura en `.meshkore/roadmap/initiatives/INI-017-agent-files-inbox.md` y en
`.meshkore/docs/modules/zaelar-modules.md §Files module`.

## Qué se hizo

- **Módulo nuevo `files/`** (declarado en `cluster.yaml`): `store.py` (guardado con nombre saneado, resolución
  de colisiones por sufijo numérico, escritura atómica `tmp`+`os.replace`, `list_files()`) + `server_api.py`
  (`POST /api/files/upload` multipart, `GET /api/files`), montado sin condición en `server/__init__.py`.
- **Aviso al brain**: cada subida encola una nota `[SISTEMA]` en el mailbox existente `voice/brain_notes.py`
  (mismo mecanismo que ya usan las terminaciones asíncronas de widgets) — cero cambios en `hermes.py`/`duo.py`.
- **Frontend** (`frontend/app/main.js`): el listener global de `paste` (que ya alimentaba el chat de texto) se
  extendió para detectar imágenes en el portapapeles y subirlas; nuevos listeners globales `dragover`/`drop`
  para cualquier archivo soltado en la ventana. Confirmación visual como línea de sistema en el chat (nuevo rol
  `sys` en `ChatWall.js` + estilo en `styles.css`).
- **Docs**: `cluster.yaml` (módulo declarado), `CLAUDE.md` (módulo + decisión clave), `zaelar-modules.md`
  (sección `§Files` completa, incluyendo el razonamiento de por qué NO se hizo multimodal), iniciativa
  `INI-017` con el registro de diseño completo.

## Ficheros tocados

Nuevos: `files/__init__.py`, `files/store.py`, `files/server_api.py`,
`.meshkore/roadmap/initiatives/INI-017-agent-files-inbox.md`, este diario.
Editados: `server/__init__.py`, `.gitignore`, `frontend/app/main.js`, `frontend/app/components/ChatWall.js`,
`frontend/app/styles.css`, `.meshkore/public/cluster.yaml`, `CLAUDE.md`,
`.meshkore/docs/modules/zaelar-modules.md`.

## Verificación

- Import limpio de `server.create_app()` tras registrar el router nuevo (sin excepciones).
- `app.openapi()["paths"]` confirma `POST /api/files/upload` y `GET /api/files` montados.
- `TestClient`: subida con `source=paste` → 200 `{name,path,size}`; segunda subida con el MISMO nombre
  (`source=drop`) → resuelta a `captura_1.png` sin pisar la primera; `GET /api/files` lista ambas con
  `size`/`mtime` correctos; el log confirma las dos notas `[SISTEMA]` encoladas en `brain_notes`.
- Reinicio del stack en vivo: el proceso ya corría (`make run-duo`, BRAIN=duo) de una sesión anterior; se paró
  limpio (SIGTERM y, al persistir, SIGKILL sobre el proceso web colgado) y se relanzó con el MISMO comando
  (`make run-duo`, respetando el brain que ya tenía el operador); `GET /api/files` respondió `{"files":[]}`
  desde el proceso recién arrancado, confirmando que el código nuevo es el que corre en `:8473`.
- **Pendiente de verificar por el operador**: pegar/arrastrar de verdad desde el navegador, y un turno de voz/
  chat real pidiéndole a Hermes que lea un archivo subido.

## Fuera de alcance (deferred)

Widget de navegación/gestión de archivos, endpoint de borrado, visión multimodal en el mismo turno (ACP/
`ImageContent`), y acciones futuras sobre los archivos (p. ej. reenviar por email) — todo documentado como
"fuera de alcance" en la iniciativa `INI-017`.
