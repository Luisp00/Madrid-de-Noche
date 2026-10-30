# Madrid de Noche

Agregador personal de **todos los eventos nocturnos de Madrid** (clubs, fiestas, conciertos nocturnos, tardeos, afters, bares con DJ) con precio, música, dress code, edad, line-up, estado de entradas y enlace de compra. Una única app con filtros; se actualiza sola una vez al día.

- **Web pública:** https://luisp00.github.io/Madrid-de-Noche/ (GitHub Pages, rama `gh-pages`). Sin cuenta de Claude, instalable en el móvil; favoritos solo en el navegador.
- **App en claude.ai (artifact):** https://claude.ai/artifact/N1LKQtKKWsz2K2xYH1Uc4V (slug `aa1bd110-8301-4d75-8ffa-b7f5e5264d2e`). Misma app leyendo la base de datos del artifact; favoritos sincronizados entre dispositivos y botón ⟳ para que el propietario lance la actualización a mano. Privada hasta que se comparta desde su menú "Compartir".
- **Datos:** 39 parsers en Python (`scrape/sources/`) leen las webs cada noche y `enrich.py` visita la página de compra de los eventos que quedan sin precio; los agentes de Claude solo entran como respaldo cuando un parser falla y, dos veces por semana, para la cola larga de salas sin parser. Fusión y deduplicación en `merge.py`. Regla de precios: la página propia de la ticketera manda sobre los agregadores; entre ticketeras, el más barato gana, el botón principal de la ficha va a esa web y la ficha indica qué web lo tenía más caro. Las fuentes se nombran por la ticketera del enlace (Fourvenues, Xceed, DICE, Fever, WHAN…).
- **Actualización diaria del artifact:** tarea programada `trig_01Vfxn2eyLAwrGVNHx7wYBfW` (22:00 Europe/Madrid, aviso push, Sonnet 5.5 con esfuerzo high en los agentes; Opus 5.5 high si hay que reparar un parser) que arranca una sesión nueva en el entorno cloud "Madrid de Noche", clona `main`, ejecuta `RUNBOOK.md` y escribe la BD del artifact. Esa sesión no puede hacer push al repo (comprobado: 403 del proxy git, sin `add_repo` ni `create_session`), así que **la web pública la publica GitHub Actions** (`.github/workflows/update.yml`, mismo pipeline, 22:20 Madrid). La tarea antigua con 7 agentes Opus (`trig_01AYNgQ8ve5WaF1Z4Km75cAV`) está desactivada y se puede borrar.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app (HTML/CSS/JS autocontenido, sin `<html>/<head>`: el publicador del artifact añade el esqueleto y `build_site.py` el de la web estática). Con `claude` disponible lee la colección `chunks` con `claude.use("db")`, los favoritos con `claude.use("user")` y lanza la actualización con `claude.use("mcp")` (conector "Claude Code Remote", `fire_trigger`); sin `claude`, lee `data/events.json` y `data/status.json`. |
| `enrich.py` | `python3 enrich.py run/data [--max 250]`: para los eventos sin precio cuyo enlace es de una ticketera con página pública (Xceed, DICE, WHAN, Fever, Taquilla, PATT…) visita la página y rellena precio, estado y, si faltan, hora/dirección/edad. Escribe `_enrich_report.json`. |
| `scrape.py` | Ejecuta todos los parsers de `scrape/sources/` en paralelo, valida la salida y deja `data/<fuente>.json` y `data/_scrape_report.json` con la lista `failed` (parsers con error o por debajo de su `MIN_EVENTS`). |
| `scrape/common.py` | Biblioteca de los parsers: `get` (requests con proxy, reintentos y caché de 1 h), `browser` (Chromium headless vía `tools/fetch.js`), JSON-LD, fechas/horas/precios en español, `event()` con el esquema de SPEC.md, `validate()`. |
| `scrape/CONTRATO.md` | Lo que debe cumplir cada parser. |
| `scrape/venues.json` | Directorio de salas (227; 151 verificadas en su web o en la fuente): nombre canónico, alias, tipo de local (`discoteca`, `sala`, `bar`, `recinto`, `rooftop`, `pubcrawl` = punto de salida de pub crawls, `otro`, `marca` = promotora sin local), dirección, código postal y zona. `merge.py` lo usa para corregir nombre, dirección y zona y para el campo `venueKind` (filtro "Local" de la app). Para arreglar una ubicación o un tipo, se edita aquí. |
| `scrape/sources/*.py` | Un parser por fuente: Applinkers, All Madrid Nightlife, Bynova, Nightlife Madrid, Fever, Fulltechno, Technoparty, Techno Airlines, DICE, Xceed, WHAN, Taquilla.com, Notikumi, Dondego, Discotech, AllEvents, Conciertos.club, La Ganzúa, Madrid en Vivo, esMadrid, Siroco, Sala El Sol, La Riviera, Wurlitzer Ballroom, Sala Galileo Galilei. Los `_*.py` son helpers compartidos. Notikumi lee precio y estado de la API pública de su checkout (`api2.notikumi.com`, pide JSON con `Accept`). Webs de salas (30 oct, con `_salas.py` como ayudante para nombre, dirección y zona desde `venues.json`): Shoko (Shopify), Teatro Kapital (calendario de Ticketclub), LAB theCLUB, Independance, Café Berlín, Moby Dick, Ochoymedio (promotora: conciertos en varias salas), Changó, Mondo Disko, Sala But/Mon/Copérnico (`grupomon.py`), Gruta 77, Clamores, Teatro Barceló (sesiones semanales de su web), Maravillas. |
| `scrape/disabled/ra.py` | Parser de Resident Advisor por su API GraphQL. **Desactivado**: funciona saltándose la protección anti-bot de RA. Techno Airlines replica la mayoría de sus eventos. |
| `merge.py` | Normaliza, deduplica y fusiona `data/*.json`; lo cruza con lo existente (`db/chunks/`) y genera `out/chunks/chunk-NN.json` (≤150 KB cada uno), `out/writes.json` (escrituras para `ArtifactData`), `out/events.json` y `out/status.json`. Conserva campos estables del evento existente; quita pasados, duplicados y eventos futuros que llevan 3 extracciones sin aparecer; aplica el directorio `scrape/venues.json` (nombre canónico, dirección verificada, zona y tipo de local `venueKind`; si la sala no está, deduce la zona por código postal y el tipo por el nombre); une carteles de la misma sala, noche y hora; descarta entradas semanales genéricas cuando hay evento con nombre; excluye Madrid Lux. |
| `build_site.py` | Genera la web estática: `python3 -I build_site.py out/ site/`. |
| `tools/fetch.js` | Descarga una página con Chromium headless (proxy del entorno): texto visible + enlaces, o `--raw`. Lo usan los parsers que lo necesitan y los agentes cuando WebFetch no está o la web lo bloquea. |
| `SPEC.md` | Esquema de cada evento, etiquetas de música, zonas, salas conocidas, exclusiones y normas. Lo leen los agentes de respaldo. |
| `RUNBOOK.md` | Procedimiento diario (v2): código fresco → estado de la BD → `scrape.py` → `enrich.py` → respaldo/cola larga con agentes → `merge.py` → escrituras en el artifact → `meta/status`. Incluye los prompts de los agentes por fuente. |
| `.github/workflows/update.yml` | Workflow nocturno de GitHub Actions: mismo pipeline (scrape → enrich → merge contra `gh-pages/data/events.json` → build_site) y push a `gh-pages`. También se puede lanzar a mano desde la pestaña Actions. |
| `FUENTES.md` | Evaluación de fuentes nuevas (30 oct 2026): qué hay, cómo se accede, volumen, prioridad. |
| `test.js` | Prueba de la app con Playwright: 25 comprobaciones. `node test.js` o `node test.js <events.json>`. |
| `data/*.json`, `out/merged.json` | Extracciones y fusión de la carga inicial (29 oct), útiles para probar `merge.py`. |
| `QA.md`, `REVIEW.md` | Auditoría de la carga inicial y revisión del proyecto. |

Copias de `SPEC.md`, `RUNBOOK.md`, `merge.py`, `build_site.py` y `tools/fetch.js` están publicadas dentro del artifact (`spec.md`, `runbook.md`, `merge.py.txt`, `build_site.py.txt`, `fetch.js.txt`) por compatibilidad; la sesión diaria usa las del repo.

## Estado (30 oct 2026, 11:20)

- **BD y web:** 1580 eventos (29 oct → 13 nov) de 24 fuentes, en 9 chunks. Cobertura: 80 % con precio (antes 74 %), 96 % con hora, 37 % con estado de entradas, 41 % con edad, 28 % con dress code.
- **Pipeline Python:** 25 parsers pasan (`failed: []`) en unos 5 minutos; `enrich.py` recuperó 135 precios en 150 páginas (Xceed, DICE, WHAN sobre todo). Las ejecuciones de prueba de la tarea programada (09:41 y 09:51) hicieron todo el recorrido salvo el push a la web.
- **App:** filtros con modo excluir (tres estados por chip), calendario propio con rangos de noches, botón "Ver resultados" accesible, paneles más altos en escritorio, un botón por fuente en la ficha.
- **Fuentes nuevas incorporadas hoy:** WHAN, Xceed, Techno Airlines, DICE por páginas de ciudad, feeds de Siroco / El Sol / La Riviera, Wurlitzer, Galileo. Madrid Lux eliminada a petición del usuario. Resident Advisor apartado (su API exige saltarse el anti-bot).

## Avisos

- **Bloqueos:** ra.co (403), shotgun.live (429), Fourvenues directo (403), Atrápalo (challenge). Bynova limita a veces las páginas de club (429), por eso su dirección y dress code salen incompletos.
- **Permisos de las sesiones programadas:** una sesión lanzada por tarea puede usar Python, Chromium, `WebFetch` y `ArtifactData`, pero no tiene el repo entre sus fuentes y el proxy git le niega el push (403); tampoco tiene `add_repo` ni `create_session`. Una tarea con `persistent_session_id` no entregó en la sesión indicada sino en una nueva. Por eso la web la publica GitHub Actions.
- **Red:** el entorno cloud "Madrid de Noche" tiene la red abierta desde el 30 oct. Una sesión abierta antes del cambio no recupera `WebFetch`; `curl`, `requests` y Chromium sí funcionan a través del proxy.
- **Correcciones manuales** en la BD duran hasta la siguiente extracción; lo permanente se arregla en los parsers, `SPEC.md` o `merge.py`.
- **Rama de código:** `main` está al día con la rama de trabajo `ccr-7f46cbaa-sonpg4`; la tarea diaria y GitHub Actions clonan `main`.

## Pendiente

1. Revisar la primera ejecución nocturna (22:00) en `meta/status.run` y el aviso push de la tarea, y la primera ejecución del workflow de GitHub Actions (22:20) en la pestaña Actions.
2. Borrar la colección antigua `events` (981 documentos; exige leerlos por páginas) y los documentos `meta/selftest*` de las pruebas. No molestan.
3. Precios que siguen faltando (~270): Conciertos.club, Technoparty y Techno Airlines no los publican (Notikumi y Shoko ya salen por la API del checkout de Notikumi y la de PATT); Fourvenues (403) y RA (vetada) no se pueden visitar. `enrich.py` llega a su tope de 150 páginas: subirlo si hace falta.
4. Zona "Otros" en ~60 eventos y 54 sin dirección: añadir esas salas a `scrape/venues.json` (con `verified: true` si se comprueba en su web).
5. Fuentes de prioridad media en `FUENTES.md` (Wegow, Clubs In Madrid…) y los agentes de cola larga para las salas sin parser.

## Cómo trabajar desde Claude Code

- Herramientas del artifact: `Artifact` (publish/read/list con `url`) y `ArtifactData` (get/query/set/update/delete). Tareas programadas: `mcp__claude-code-remote__list_triggers` / `update_trigger` / `fire_trigger`; sesión de ejecución: `get_session` / `send_message`.
- Republicar la app: `Artifact` publish con `url` del artifact, `file_path: index.html` y `files` con `spec.md`, `runbook.md`, `merge.py.txt`, `build_site.py.txt`, `fetch.js.txt` (copiar antes con `cp`). No pasar `capabilities` salvo que cambien (`db` con 2 reglas, `user`, `mcp` con `fire_trigger`).
- Probar la app: `node test.js` (Playwright preinstalado en el entorno de Claude; en local, `npm i playwright`).
- Probar un parser: `python3 scrape.py --only fever --out run/scrape_test`; todos: `python3 scrape.py --out run/data` (~5 min; caché de 1 h en `run/cache`).
- Fusionar y publicar a mano: `ArtifactData query chunks out_dir run/db` + `run/db/versions.txt` → `python3 -I merge.py run/data run/db run/out` → un `set` por chunk → `python3 -I build_site.py run/out run/site` → copiar a `gh-pages`.
