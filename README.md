# Madrid de Noche

Agregador personal de **todos los eventos nocturnos de Madrid** (clubs, fiestas, conciertos nocturnos, tardeos, afters, bares con DJ) con precio, música, dress code, edad, line-up, estado de entradas y enlace de compra. Una única app con filtros; se actualiza sola una vez al día.

- **App publicada:** https://claude.ai/artifact/N1LKQtKKWsz2K2xYH1Uc4V (artifact slug `aa1bd110-8301-4d75-8ffa-b7f5e5264d2e`). Privada hasta que se comparta.
- **Base de datos:** la del propio artifact (capacidad `db`): colección `events` (un documento por evento, id `YYYY-MM-DD-<hash>`) y documento `meta/status`.
- **Actualización:** tarea programada en la cuenta de Claude, diaria a las 22:00 (Europe/Madrid), modelo Opus 5.5, aprobación automática, aviso push. Sigue `RUNBOOK.md`. También a demanda pidiéndoselo a Claude ("actualiza los eventos").
- **Regla de precios:** si varias webs discrepan, se muestra el más barato, el enlace principal va a esa web y la ficha indica qué web lo tenía más caro.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La app completa (HTML/CSS/JS autocontenido). Lee la base de datos del artifact con `claude.use("db")` en 4 tramos de fechas. |
| `SPEC.md` | Esquema de cada evento, etiquetas de música, zonas por código postal, salas conocidas, exclusiones y normas de extracción. Lo leen los agentes extractores. |
| `RUNBOOK.md` | Procedimiento de la actualización diaria: 7 agentes de extracción en paralelo (Opus 5.5 high) → lectura del estado de la BD → `merge.py` → subida por lotes → `meta/status`. Incluye la lista completa de fuentes y URLs. |
| `merge.py` | Normaliza, deduplica y fusiona `data/*.json`; compara con `existing.json` (estado de la BD) y genera `out/ops_NN.json` (lotes de ≤50 ops para `db_write`, con `ifVersion`). Precio más barato gana. |
| `data/*.json` | Extracciones crudas de la carga inicial (29 oct–13 nov 2026). |
| `out/merged.json` | Resultado fusionado de la carga inicial (1031 eventos antes de las correcciones QA). |
| `existing.json` | Índice id/version/date/venue/title de lo que había en la BD al fusionar. |
| `QA.md` | Auditoría de datos (estructura + 20 eventos contrastados con sus webs). |
| `REVIEW.md` | Revisión independiente de todo el proyecto con errores detectados y próximos pasos priorizados. |
| `test.js` | Prueba de render de la app con Playwright y datos simulados. |

Copias de `SPEC.md`, `RUNBOOK.md` (como `runbook.md`) y `merge.py` (como `merge.py.txt`) están publicadas dentro del artifact para que la tarea diaria las lea con la herramienta `Artifact`/`read_file`.

## Estado (30 oct 2026, 06:40)

- 981 eventos en la BD (29 oct → 13 nov) de 35 fuentes que aportan datos.
- Hecho: app, carga inicial, auditoría QA y correcciones (duplicados, no-nocturnos y productos "sin esperas" borrados; precios/horas/estados corregidos), `merge.py` endurecido, tarea diaria creada y verificada (una sesión programada puede leer y escribir la BD; allí las herramientas se llaman `Artifact` y `ArtifactData`).
- La tarea diaria **aún no se ha ejecutado nunca**; la primera es hoy a las 22:00.

## Pendiente (ver `REVIEW.md` para el detalle)

1. **Antes de las 22:00**: en `RUNBOOK.md` subir la espera de agentes a 60 min; leer la BD por tramos (`db_query` con `where date` por rangos y guardando solo id/version/date/venue/title); hacer que `merge.py` borre eventos futuros que ya no aparezcan en ninguna fuente (cancelados); probar una subida por lotes desde una sesión programada.
2. **App** (`index.html`): chip "Finde" devuelve 0 (`Math.max` sobre strings, ~línea 262); orden dentro de la noche (las 00:00–05:59 deben contar como +24 h, ~línea 338); búsqueda insensible a tildes; precio desborda en móvil (caso "Gratis" usa `priceText` sin recortar, `.price` con `flex:none`); `.dayhead` sticky queda bajo la cabecera (~165 px); cerrar filtros tocando fuera no llama a `render()`; el botón principal de la ficha debe usar `ticketUrl` y no `sources[0]`; accesibilidad (teclado/foco/contraste); etiqueta "tardeo" sin traducir en `TYPE_LABELS`.
3. **Cobertura**: 3 de los 7 agentes de la carga inicial no llegaron a ejecutarse (RA, DICE, Shotgun, Techno Airlines, ma.to, Madrid Lux, Clubbable, Discomadrid, Discoruta, Taquilla.com, Eventbrite, Atrapalo, Discotech). La tarea diaria los incluye. Salas sin eventos el finde de Halloween: Teatro Barceló, Gabana, Specka, Caracol, Marula, Medias Puri, Uñas Chung Lee, Toni 2, Stardust/Sala Cool, Liberty, Villa Panthera, Istar. Opium y Oh My Club cerraron en 2026.
4. 287 eventos enlazan a un listado y no a la página del evento; 33 % sin precio; 75 % sin estado de entradas.
5. Botón "actualizar ahora" en la app y compartirla.

## Cómo trabajar desde Claude Code

- Las herramientas del artifact (`mcp__claude-artifacts__*`: `read_artifact`, `publish_files`, `db_query`, `db_get`, `db_write`, `declare_capabilities`) y la tarea programada (`mcp__claude-code-remote__list_triggers` / `update_trigger`, id `trig_01AYNgQ8ve5WaF1Z4Km75cAV`) están disponibles en sesiones de Claude con esos conectores; desde un terminal local sin ellos se puede editar el código pero no publicar ni tocar la BD.
- Para republicar la app: `publish_files` con `slug`, `base_version` (de `get_artifact`) y `index.html`; tras cualquier cambio en `SPEC.md`/`RUNBOOK.md`/`merge.py`, volver a publicar `spec.md`, `runbook.md` y `merge.py.txt` en el artifact.
- Probar la app en local: `node test.js` (Playwright preinstalado en el entorno de Claude; en local, `npm i playwright`).
- Fusionar: `python3 -I merge.py data/ existing.json out/`.
