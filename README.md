# Madrid de Noche

Agregador personal de **todos los eventos nocturnos de Madrid** (clubs, fiestas, conciertos nocturnos, tardeos, afters, bares con DJ) con precio, música, dress code, edad, line-up, estado de entradas y enlace de compra. Una única app con filtros; se actualiza sola una vez al día.

- **Web pública:** https://luisp00.github.io/Madrid-de-Noche/ (GitHub Pages, rama `gh-pages`). Sin cuenta de Claude, instalable en el móvil; favoritos solo en el navegador.
- **App en claude.ai (artifact):** https://claude.ai/artifact/N1LKQtKKWsz2K2xYH1Uc4V (slug `aa1bd110-8301-4d75-8ffa-b7f5e5264d2e`). Misma app leyendo la base de datos del artifact; favoritos sincronizados entre dispositivos y botón ⟳ para que el propietario lance la actualización a mano. Privada hasta que se comparta desde su menú "Compartir".
- **Datos:** 25 parsers en Python (`scrape/sources/`) leen las webs cada noche; los agentes de Claude solo entran como respaldo cuando un parser falla y, dos veces por semana, para la cola larga de salas sin parser. Fusión y deduplicación en `merge.py`. Regla de precios: si varias webs discrepan, se muestra el más barato, el botón principal de la ficha va a esa web y la ficha indica qué web lo tenía más caro.
- **Actualización diaria:** tarea programada `trig_01GikgephvtpzwEE5KEfSYiX` (22:00 Europe/Madrid, Sonnet 5.5, esfuerzo high en los agentes) que despierta la sesión de ejecución `session_01JqbzdECTVzMVd3MhM3bLR2` (entorno cloud "Madrid de Noche", clon de `gh-pages`, modo `auto`); esa sesión clona el código, ejecuta `RUNBOOK.md`, escribe la BD del artifact y publica la web. La tarea antigua con 7 agentes Opus (`trig_01AYNgQ8ve5WaF1Z4Km75cAV`) está desactivada.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app (HTML/CSS/JS autocontenido, sin `<html>/<head>`: el publicador del artifact añade el esqueleto y `build_site.py` el de la web estática). Con `claude` disponible lee la colección `chunks` con `claude.use("db")`, los favoritos con `claude.use("user")` y lanza la actualización con `claude.use("mcp")` (conector "Claude Code Remote", `fire_trigger`); sin `claude`, lee `data/events.json` y `data/status.json`. |
| `scrape.py` | Ejecuta todos los parsers de `scrape/sources/` en paralelo, valida la salida y deja `data/<fuente>.json` y `data/_scrape_report.json` con la lista `failed` (parsers con error o por debajo de su `MIN_EVENTS`). |
| `scrape/common.py` | Biblioteca de los parsers: `get` (requests con proxy, reintentos y caché de 1 h), `browser` (Chromium headless vía `tools/fetch.js`), JSON-LD, fechas/horas/precios en español, `event()` con el esquema de SPEC.md, `validate()`. |
| `scrape/CONTRATO.md` | Lo que debe cumplir cada parser. |
| `scrape/sources/*.py` | Un parser por fuente: Applinkers, All Madrid Nightlife, Bynova, Nightlife Madrid, Fever, Fulltechno, Technoparty, Techno Airlines, DICE, Xceed, WHAN, Taquilla.com, Notikumi, Dondego, Discotech, AllEvents, Conciertos.club, La Ganzúa, Madrid en Vivo, esMadrid, Siroco, Sala El Sol, La Riviera, Wurlitzer Ballroom, Sala Galileo Galilei. Los `_*.py` son helpers compartidos. |
| `scrape/disabled/ra.py` | Parser de Resident Advisor por su API GraphQL. **Desactivado**: funciona saltándose la protección anti-bot de RA. Techno Airlines replica la mayoría de sus eventos. |
| `merge.py` | Normaliza, deduplica y fusiona `data/*.json`; lo cruza con lo existente (`db/chunks/`) y genera `out/chunks/chunk-NN.json` (≤150 KB cada uno), `out/writes.json` (escrituras para `ArtifactData`), `out/events.json` y `out/status.json`. Conserva campos estables del evento existente; quita pasados, duplicados y eventos futuros que llevan 3 extracciones sin aparecer; deduce la zona por sala o código postal; une carteles de la misma sala, noche y hora; descarta entradas semanales genéricas cuando hay evento con nombre; excluye Madrid Lux. |
| `build_site.py` | Genera la web estática: `python3 -I build_site.py out/ site/`. |
| `tools/fetch.js` | Descarga una página con Chromium headless (proxy del entorno): texto visible + enlaces, o `--raw`. Lo usan los parsers que lo necesitan y los agentes cuando WebFetch no está o la web lo bloquea. |
| `SPEC.md` | Esquema de cada evento, etiquetas de música, zonas, salas conocidas, exclusiones y normas. Lo leen los agentes de respaldo. |
| `RUNBOOK.md` | Procedimiento diario (v2): código fresco → estado de la BD → `scrape.py` → respaldo/cola larga con agentes → `merge.py` → escrituras en el artifact → `meta/status` → web en `gh-pages`. Incluye los prompts de los agentes por fuente. |
| `FUENTES.md` | Evaluación de fuentes nuevas (30 oct 2026): qué hay, cómo se accede, volumen, prioridad. |
| `test.js` | Prueba de la app con Playwright: 17 comprobaciones. `node test.js` o `node test.js <events.json>`. |
| `data/*.json`, `out/merged.json` | Extracciones y fusión de la carga inicial (29 oct), útiles para probar `merge.py`. |
| `QA.md`, `REVIEW.md` | Auditoría de la carga inicial y revisión del proyecto. |

Copias de `SPEC.md`, `RUNBOOK.md`, `merge.py`, `build_site.py` y `tools/fetch.js` están publicadas dentro del artifact (`spec.md`, `runbook.md`, `merge.py.txt`, `build_site.py.txt`, `fetch.js.txt`) por compatibilidad; la sesión diaria usa las del repo.

## Estado (30 oct 2026, 09:45)

- **BD y web:** 1663 eventos (1571 de hoy en adelante, 29 oct → 13 nov) de 25 fuentes, en 9 chunks. Cobertura: 74 % con precio, 96 % con hora, 39 % con edad, 27 % con dress code, 31 % con estado de entradas.
- **Pipeline Python:** los 25 parsers pasan (`failed: []`) en unos 5 minutos; la primera ejecución completa dio 1295 eventos únicos. El coste por ejecución es el de la coordinación de la sesión (Sonnet), no el de leer webs con modelos.
- **Ejecución de la tarea:** la sesión de ejecución ha verificado el entorno (repo, dependencias, Playwright, lectura de la BD). A las 09:40 se lanzó a mano una ejecución de prueba completa; la primera nocturna es hoy a las 22:00.
- **Comparativa de coste:** la extracción con 7 agentes Opus de esta mañana consumió ~1,7 M tokens de subagentes en 22 min (muy por debajo de los 25–40 M estimados para la carga inicial, pero aun así ~50 veces más que el pipeline Python).

## Avisos

- **Bloqueos:** ra.co (403), shotgun.live (429), Fourvenues directo (403), Atrápalo (challenge). Bynova limita a veces las páginas de club (429), por eso su dirección y dress code salen incompletos.
- **Permisos de la sesión de ejecución (modo `auto`):** puede escribir en la BD y hacer push a su propia rama `gh-pages`; no puede hacer push a otras ramas. Por eso trabaja sobre `gh-pages` y clona el código aparte. En modo `acceptEdits` ocurre lo contrario (push sí, `ArtifactData` pide permiso).
- **Red:** el entorno cloud "Madrid de Noche" tiene la red abierta desde el 30 oct. Una sesión abierta antes del cambio no recupera `WebFetch`; `curl`, `requests` y Chromium sí funcionan a través del proxy.
- **Correcciones manuales** en la BD duran hasta la siguiente extracción; lo permanente se arregla en los parsers, `SPEC.md` o `merge.py`.
- **Rama de código:** la sesión diaria clona `main` y, si allí no está `scrape.py`, la rama `ccr-7f46cbaa-sonpg4`. Al fusionar a `main`, nada que cambiar.

## Pendiente

1. Revisar el informe de la ejecución de prueba de las 09:40 y el de la nocturna de las 22:00 (`meta/status.run` y la sesión de ejecución).
2. Fusionar la rama `ccr-7f46cbaa-sonpg4` en `main` cuando te parezca.
3. Borrar la colección antigua `events` (981 documentos; exige leerlos por páginas). No molesta.
4. Calidad: zona "Otros" en 275 eventos (salas sin dirección; ampliar `VENUE_ZONE` en `merge.py` con las que más se repitan), precios en Techno Airlines/Technoparty/Discotech (no los publican), direcciones de WHAN.
5. Fuentes nuevas de prioridad media en `FUENTES.md` (Wegow, Clubs In Madrid…) y los agentes de cola larga para las salas sin parser.

## Cómo trabajar desde Claude Code

- Herramientas del artifact: `Artifact` (publish/read/list con `url`) y `ArtifactData` (get/query/set/update/delete). Tareas programadas: `mcp__claude-code-remote__list_triggers` / `update_trigger` / `fire_trigger`; sesión de ejecución: `get_session` / `send_message`.
- Republicar la app: `Artifact` publish con `url` del artifact, `file_path: index.html` y `files` con `spec.md`, `runbook.md`, `merge.py.txt`, `build_site.py.txt`, `fetch.js.txt` (copiar antes con `cp`). No pasar `capabilities` salvo que cambien (`db` con 2 reglas, `user`, `mcp` con `fire_trigger`).
- Probar la app: `node test.js` (Playwright preinstalado en el entorno de Claude; en local, `npm i playwright`).
- Probar un parser: `python3 scrape.py --only fever --out run/scrape_test`; todos: `python3 scrape.py --out run/data` (~5 min; caché de 1 h en `run/cache`).
- Fusionar y publicar a mano: `ArtifactData query chunks out_dir run/db` + `run/db/versions.txt` → `python3 -I merge.py run/data run/db run/out` → un `set` por chunk → `python3 -I build_site.py run/out run/site` → copiar a `gh-pages`.
