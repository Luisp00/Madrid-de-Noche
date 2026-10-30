# Madrid de Noche

Agregador personal de **todos los eventos nocturnos de Madrid** (clubs, fiestas, conciertos nocturnos, tardeos, afters, bares con DJ) con precio, música, dress code, edad, line-up, estado de entradas y enlace de compra. Una única app con filtros; se actualiza sola una vez al día.

- **App publicada:** https://claude.ai/artifact/N1LKQtKKWsz2K2xYH1Uc4V (artifact slug `aa1bd110-8301-4d75-8ffa-b7f5e5264d2e`). Privada hasta que se comparta desde el menú "Compartir" de la propia página.
- **Base de datos:** la del propio artifact (capacidad `db`): colección `events` (un documento por evento, id `YYYY-MM-DD-<hash>`), documento `meta/status` (lo que muestra la cabecera de la app), documento `meta/seen` (id → última fecha en que cada evento apareció en alguna fuente) y `data/users/<id>/prefs` (favoritos de cada usuario).
- **Actualización:** tarea programada de la cuenta de Claude (id `trig_01AYNgQ8ve5WaF1Z4Km75cAV`), diaria a las 22:00 (Europe/Madrid), modelo Opus 5.5, aprobación automática, aviso push. Sigue `RUNBOOK.md`. También a demanda: el propietario tiene en la app un botón ⟳ que lanza esa misma tarea (pide confirmación; tarda 1–2 h), o se le puede pedir a Claude ("actualiza los eventos").
- **Regla de precios:** si varias webs discrepan, se muestra el más barato, el botón principal de la ficha va a esa web y la ficha indica qué web lo tenía más caro.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app completa (HTML/CSS/JS autocontenido, sin `<html>/<head>`: el publicador del artifact añade el esqueleto). Lee la BD con `claude.use("db")` en 4 tramos de fechas, los favoritos con `claude.use("user")` y lanza la actualización con `claude.use("mcp")` (conector "Claude Code Remote", herramienta `fire_trigger`). |
| `SPEC.md` | Esquema de cada evento, etiquetas de música, zonas por código postal, salas conocidas, exclusiones y normas de extracción. Lo leen los agentes extractores. |
| `RUNBOOK.md` | Procedimiento de la actualización diaria: 7 agentes de extracción en paralelo (Opus 5.5 high) → descarga de la BD con `out_dir` + `versions.txt` → `merge.py` → subida por lotes con `ArtifactData batch` → `meta/seen` y `meta/status`. Incluye la lista completa de fuentes y URLs. |
| `merge.py` | Normaliza, deduplica y fusiona `data/*.json`; compara con la BD (`db/`) y genera `out/batchf_NN.json` / `out/batch_NN.json` (lotes de ≤50 escrituras para `ArtifactData`), `out/seen.json` y `out/status.json`. Precio más barato gana; conserva campos estables del documento existente; borra pasados, duplicados y eventos futuros que llevan 3 extracciones sin aparecer. Deduce la zona por sala o código postal. |
| `data/*.json` | Extracciones crudas de la carga inicial (29 oct–13 nov 2026). Sirven para probar `merge.py`. |
| `out/merged.json` | Resultado fusionado de la carga inicial. |
| `QA.md` | Auditoría de datos de la carga inicial (estructura + 20 eventos contrastados con sus webs). |
| `REVIEW.md` | Revisión del proyecto del 30 oct 2026 (segunda pasada): qué se encontró, qué se arregló y qué queda. |
| `test.js` | Prueba de la app con Playwright: 15 comprobaciones (finde, orden, búsqueda sin tildes, desbordes, foco, teclado, filtros, botón actualizar). `node test.js` con datos de ejemplo o `node test.js <dir>` con un volcado de la BD. |

Copias de `SPEC.md`, `RUNBOOK.md` (como `runbook.md`) y `merge.py` (como `merge.py.txt`) están publicadas dentro del artifact para que la tarea diaria las lea con la herramienta `Artifact` (action `read` + `path`). **Tras cambiar cualquiera de los tres hay que volver a publicarlos.**

## Estado (30 oct 2026, 08:15)

- 981 eventos en la BD (29 oct → 13 nov) de 35 fuentes que aportan datos. La tarea diaria **aún no se ha ejecutado nunca**; la primera es hoy a las 22:00.
- Hecho hoy (ver `REVIEW.md`): corregidos los 9 errores conocidos de la app y varios más; botón "actualizar ahora" para el propietario; favoritos guardados también en la BD; `merge.py` reescrito para el formato real de `ArtifactData` (lotes con `file_path`, versiones, `meta/seen`, borrado de cancelados, zonas por código postal); `RUNBOOK.md` reescrito y verificado con una sesión programada de prueba; prompt de la tarea actualizado (espera de 60 min, herramientas correctas).
- Comprobado desde una sesión programada real (30 oct, 07:57): existen `WebFetch`, `WebSearch`, `Agent`, `Artifact`, `ArtifactData`; `python3` 3.11; `/home/claude/madrid-noche` escribible; `ArtifactData query` con `out_dir` y `batch` con `file_path` funcionan.

## Avisos importantes

- **Red del entorno cloud.** El entorno "Madrid de Noche" de Claude Code (anthropic_cloud, `env_011iohJDNuqisdiyXfRcwZbg`) tiene la red limitada: desde él ni `WebFetch` ni `curl` llegan a ra.co, feverup.com, conciertos.club, etc. La tarea diaria no corre ahí (su autotest del 29 oct dio `webfetchOk: true`), pero **cualquier sesión de Claude Code que quiera extraer eventos desde ese entorno fallará** hasta que en Ajustes del entorno → Network access se amplíe el acceso o se añadan los dominios de `RUNBOOK.md`.
- Las correcciones manuales en la BD (como las de `QA.md`) duran hasta la siguiente extracción: si la web sigue mostrando el dato erróneo, vuelve. Lo permanente se arregla en `SPEC.md`/`merge.py`.
- La herramienta de BD guarda los documentos en archivos pero no sus versiones; sin `db/versions.txt` `merge.py` se niega a generar lotes (las escrituras sobre documentos existentes exigen `if_version`).

## Pendiente

1. **Primera ejecución de la tarea (hoy 22:00):** revisar su informe y `meta/status.run`; comprobar que `versions.txt` se creó bien y que los lotes con `file_path` subieron. Si algo falla, el fallback está en `RUNBOOK.md` §4.
2. **Cobertura:** 3 de los 7 agentes de la carga inicial no llegaron a ejecutarse (RA, DICE, Shotgun, Techno Airlines, ma.to, Madrid Lux, Clubbable, Discomadrid, Discoruta, Taquilla.com, Eventbrite, Atrapalo, Discotech). La tarea diaria los incluye. Salas sin eventos el finde de Halloween: Teatro Barceló, Gabana, Specka, Caracol, Marula, Medias Puri, Uñas Chung Lee, Toni 2, Stardust, Liberty, Villa Panthera, Istar (el agente C tiene instrucción de buscarlas expresamente).
3. **Calidad:** 28 % de los eventos enlazan a un listado y no a la página del evento; 33 % sin precio; 75 % sin estado de entradas. `SPEC.md` ya exige la página propia del evento; medir tras la primera ejecución.
4. Compartir la app (menú Compartir del artifact). Los favoritos de otras personas se guardan en su propio documento privado si tienen nivel Contributor o superior; con nivel Viewer solo en su navegador.

## Cómo trabajar desde Claude Code

- Herramientas del artifact en una sesión de Claude Code: `Artifact` (publish/read/list con `url`) y `ArtifactData` (get/query/set/update/batch). La tarea programada: `mcp__claude-code-remote__get_trigger` / `update_trigger` / `fire_trigger`, id `trig_01AYNgQ8ve5WaF1Z4Km75cAV`. Desde un terminal local sin esos conectores se puede editar el código pero no publicar ni tocar la BD.
- Republicar la app: `Artifact` publish con `url` del artifact, `file_path: index.html` y `files: {"spec.md": "SPEC.md", "runbook.md": "RUNBOOK.md", "merge.py.txt": "merge.py.txt"}` (`cp merge.py merge.py.txt` antes). No pasar `capabilities` salvo que cambien (se conservan: `db` con 2 reglas, `user`, `mcp` con `fire_trigger`).
- Probar la app en local: `node test.js` (Playwright preinstalado en el entorno de Claude; en local, `npm i playwright`). Con datos reales: `ArtifactData query events limit 1000 out_dir <dir>` y `node test.js <dir>`.
- Fusionar: `python3 -I merge.py data/ db/ out/ [--today YYYY-MM-DD]` (`db/` = volcado de `ArtifactData` con `out_dir` + `versions.txt`).
