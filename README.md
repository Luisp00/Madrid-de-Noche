# Madrid de Noche

Agregador personal de **todos los eventos nocturnos de Madrid** (clubs, fiestas, conciertos nocturnos, tardeos, afters, bares con DJ) con precio, música, dress code, edad, line-up, estado de entradas y enlace de compra. Una única app con filtros; se actualiza sola una vez al día.

- **App publicada (artifact):** https://claude.ai/artifact/N1LKQtKKWsz2K2xYH1Uc4V (slug `aa1bd110-8301-4d75-8ffa-b7f5e5264d2e`). Requiere sesión en claude.ai; privada hasta que se comparta desde el menú "Compartir" de la propia página. Aquí viven la BD, los favoritos sincronizados y el botón de actualizar.
- **App pública (GitHub Pages):** la misma `index.html` leyendo `data/events.json`, en la rama `gh-pages`. Quedará en https://luisp00.github.io/Madrid-de-Noche/ en cuanto se active Pages en el repo (Settings → Pages → Deploy from a branch → `gh-pages` / root). Sin cuenta de Claude, instalable en el móvil; favoritos solo en el navegador.
- **Base de datos:** la del artifact (capacidad `db`): colección `chunks` (4–8 documentos `chunk-NN` de ≤150 KB con `{i, n, count, updatedAt, events:[…]}`; cada evento lleva `id` = `YYYY-MM-DD-<hash>` y `lastSeen`), documento `meta/status` (lo que muestra la cabecera de la app) y `data/users/<id>/prefs` (favoritos de cada usuario). La colección antigua `events` (981 documentos, un documento por evento) ya no se usa; queda pendiente borrarla.
- **Actualización:** tarea programada de la cuenta de Claude (id `trig_01AYNgQ8ve5WaF1Z4Km75cAV`), diaria a las 22:00 (Europe/Madrid), modelo Opus 5.5, aprobación automática, aviso push. Sigue `RUNBOOK.md`. También a demanda: el propietario tiene en la app un botón ⟳ que lanza esa misma tarea (pide confirmación; tarda 1–2 h), o se le puede pedir a Claude ("actualiza los eventos").
- **Regla de precios:** si varias webs discrepan, se muestra el más barato, el botón principal de la ficha va a esa web y la ficha indica qué web lo tenía más caro.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app completa (HTML/CSS/JS autocontenido, sin `<html>/<head>`: el publicador del artifact añade el esqueleto y `build_site.py` el de la web estática). Con `claude` disponible lee la colección `chunks` con `claude.use("db")`, los favoritos con `claude.use("user")` y lanza la actualización con `claude.use("mcp")` (conector "Claude Code Remote", `fire_trigger`); sin `claude`, lee `data/events.json` y `data/status.json`. |
| `build_site.py` | Genera la web estática: `python3 -I build_site.py out/ site/` → `site/index.html` (con esqueleto y manifest) + `site/data/*.json`. |
| `SPEC.md` | Esquema de cada evento, etiquetas de música, zonas por código postal, salas conocidas, exclusiones y normas de extracción. Lo leen los agentes extractores. |
| `RUNBOOK.md` | Procedimiento de la actualización diaria: 7 agentes de extracción en paralelo (Opus 5.5 high) → descarga de `chunks` con `out_dir` (+ sus 4–8 versiones) → `merge.py` → un `set` por chunk → `meta/status` → (opcional) sesión hija que publica la web en `gh-pages`. Incluye la lista completa de fuentes y URLs. |
| `merge.py` | Normaliza, deduplica y fusiona `data/*.json`; lo cruza con lo existente (`db/chunks/`) y genera `out/chunks/chunk-NN.json`, `out/writes.json` (escrituras para `ArtifactData`), `out/events.json` y `out/status.json`. Precio más barato gana; conserva campos estables del evento existente; quita pasados, duplicados y eventos futuros que llevan 3 extracciones sin aparecer. Deduce la zona por sala o código postal. |
| `data/*.json` | Extracciones crudas de la carga inicial (29 oct–13 nov 2026). Sirven para probar `merge.py`. |
| `out/merged.json` | Resultado fusionado de la carga inicial. |
| `QA.md` | Auditoría de datos de la carga inicial (estructura + 20 eventos contrastados con sus webs). |
| `REVIEW.md` | Revisión del proyecto del 30 oct 2026 (segunda pasada): qué se encontró, qué se arregló y qué queda. |
| `tools/fetch.js` | `node tools/fetch.js URL [--max N] [--links N] [--raw] [--wait ms]`: descarga una página con Chromium headless (proxy del entorno), cierra avisos de cookies, hace scroll y devuelve texto visible + enlaces. Sustituto de WebFetch para los agentes extractores cuando WebFetch no está o la web lo bloquea. |
| `test.js` | Prueba de la app con Playwright: 17 comprobaciones (finde, orden, búsqueda sin tildes, desbordes, foco, teclado, filtros, botón actualizar, modo estático). `node test.js` con datos de ejemplo o `node test.js <events.json>` con datos reales. |

Copias de `SPEC.md`, `RUNBOOK.md` (como `runbook.md`), `merge.py` (como `merge.py.txt`) y `build_site.py` (como `build_site.py.txt`) están publicadas dentro del artifact para que la tarea diaria las lea con la herramienta `Artifact` (action `read` + `path`). **Tras cambiar cualquiera de ellos hay que volver a publicarlos.**

## Estado (30 oct 2026, 08:30)

- 981 eventos (29 oct → 13 nov) de 35 fuentes, ahora en 4 documentos `chunk-NN`. La tarea diaria **aún no se ha ejecutado nunca**; la primera es hoy a las 22:00.
- Hecho hoy (detalle en `REVIEW.md`): corregidos los 9 errores conocidos de la app y varios más; botón "actualizar ahora" para el propietario; favoritos también en la BD; almacenamiento cambiado de 1000 documentos a pocos chunks (sin versiones por evento ni lotes); `merge.py` reescrito (chunks, borrado de cancelados, campos estables, zonas por código postal); `RUNBOOK.md` reescrito y su formato de escritura verificado con una sesión programada de prueba; prompt de la tarea actualizado; web estática en `gh-pages` lista para activar Pages.
- Comprobado desde una sesión programada real (30 oct, 07:57): existen `WebFetch`, `WebSearch`, `Agent`, `Artifact`, `ArtifactData`; `python3` 3.11; `/home/claude/madrid-noche` escribible; `ArtifactData query` con `out_dir` y escrituras con `file_path` funcionan.

## Avisos importantes

- **Red del entorno cloud.** El entorno "Madrid de Noche" de Claude Code (`env_011iohJDNuqisdiyXfRcwZbg`) tenía la red limitada; el 30 oct se abrió. Una sesión ya abierta no recoge el cambio para `WebFetch` (sigue sin resolver dominios), pero `curl`/Node a través del proxy sí; las sesiones nuevas deberían tener `WebFetch`. Para extraer desde una sesión sin `WebFetch` está `tools/fetch.js` (Chromium headless a través del proxy; devuelve texto visible y enlaces). ra.co y shotgun.live bloquean a cualquier navegador de centro de datos (403/429).
- Las correcciones manuales en la BD (como las de `QA.md`) duran hasta la siguiente extracción: si la web sigue mostrando el dato erróneo, vuelve. Lo permanente se arregla en `SPEC.md`/`merge.py`.
- La herramienta de BD guarda los documentos en archivos pero no sus versiones; la tarea apunta las 4–8 versiones de los chunks en `db/versions.txt` (las escrituras sobre documentos existentes exigen `if_version`).
- La web pública se actualiza con una sesión hija (paso 6 del runbook) que corre en el entorno cloud "Madrid de Noche" porque es el que tiene acceso al repo; si ese paso falla, el artifact sigue al día y la web se queda con los datos del día anterior.

## Pendiente

1. **Primera ejecución de la tarea (hoy 22:00):** revisar su informe y `meta/status.run`; comprobar que los chunks se reescribieron (versión 2) y si el paso 6 publicó en `gh-pages`.
2. **Activar GitHub Pages** (Settings → Pages → Deploy from a branch → `gh-pages`, carpeta `/ (root)`). Hasta entonces la web pública no existe aunque la rama ya tenga los datos.
3. **Borrar la colección antigua `events`** (981 documentos; exige leerlos por páginas para conocer sus versiones). No molesta, solo ocupa.
4. **Cobertura:** 3 de los 7 agentes de la carga inicial no llegaron a ejecutarse (RA, DICE, Shotgun, Techno Airlines, ma.to, Madrid Lux, Clubbable, Discomadrid, Discoruta, Taquilla.com, Eventbrite, Atrapalo, Discotech). La tarea diaria los incluye. Salas sin eventos el finde de Halloween: Teatro Barceló, Gabana, Specka, Caracol, Marula, Medias Puri, Uñas Chung Lee, Toni 2, Stardust, Liberty, Villa Panthera, Istar (el agente C tiene instrucción de buscarlas expresamente).
5. **Calidad:** 28 % de los eventos enlazan a un listado y no a la página del evento; 33 % sin precio; 75 % sin estado de entradas. `SPEC.md` ya exige la página propia del evento; medir tras la primera ejecución.

## Cómo trabajar desde Claude Code

- Herramientas del artifact en una sesión de Claude Code: `Artifact` (publish/read/list con `url`) y `ArtifactData` (get/query/set/update/batch). La tarea programada: `mcp__claude-code-remote__get_trigger` / `update_trigger` / `fire_trigger`, id `trig_01AYNgQ8ve5WaF1Z4Km75cAV`. Desde un terminal local sin esos conectores se puede editar el código pero no publicar ni tocar la BD.
- Republicar la app: `Artifact` publish con `url` del artifact, `file_path: index.html` y `files: {"spec.md": "SPEC.md", "runbook.md": "RUNBOOK.md", "merge.py.txt": "merge.py.txt", "build_site.py.txt": "build_site.py.txt"}` (`cp merge.py merge.py.txt; cp build_site.py build_site.py.txt` antes). No pasar `capabilities` salvo que cambien (se conservan: `db` con 2 reglas, `user`, `mcp` con `fire_trigger`).
- Probar la app en local: `node test.js` (Playwright preinstalado en el entorno de Claude; en local, `npm i playwright`). Con datos reales: `ArtifactData query chunks out_dir <dir>`, `python3 -I merge.py - <dir> out/` y `node test.js out/events.json`.
- Fusionar: `python3 -I merge.py data/ db/ out/ [--today YYYY-MM-DD]` (`db/` = volcado de `ArtifactData` con `out_dir` + `versions.txt` con las versiones de los chunks).
- Publicar la web a mano: `python3 -I build_site.py out/ site/`, copiar `site/` a la rama `gh-pages` y hacer push.
