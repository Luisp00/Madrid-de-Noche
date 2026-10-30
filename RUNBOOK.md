# Madrid de Noche — procedimiento de actualización diaria (v2: Python primero, agentes de respaldo)

Artifact: https://claude.ai/artifact/N1LKQtKKWsz2K2xYH1Uc4V (slug `aa1bd110-8301-4d75-8ffa-b7f5e5264d2e`).
Base de datos del artifact: colección `chunks` (documentos `chunk-00`, `chunk-01`, … de ≤150 KB, cada uno `{i, n, count, updatedAt, events:[…]}`; entre todos contienen todos los eventos) y documento `meta/status` (lo que muestra la app). La colección antigua `events` no se usa: no la leas ni la escribas.
Web pública: https://luisp00.github.io/Madrid-de-Noche/ (rama `gh-pages` del repo https://github.com/Luisp00/Madrid-de-Noche: `index.html` + `data/events.json` + `data/status.json`).
Repo de código: rama `main` (o la rama de trabajo que te indiquen) con `scrape.py`, `scrape/`, `merge.py`, `build_site.py`, `tools/fetch.js`, `SPEC.md` y este runbook.

Herramientas:
- `Artifact` → action `read` con `url` y `path` (por si hay que leer archivos del artifact).
- `ArtifactData` → `get`, `query`, `set`, `update`, `delete`, siempre con `url`. `query` admite `out_dir`; `set` admite `file_path`. Toda escritura sobre un documento existente exige `if_version`.
- Bash con Python 3.11 (`requests`, `bs4`, `lxml`), Node con Playwright y Chromium, `git` con acceso al repo. Red abierta (proxy del entorno: `curl`, `requests` y Chromium funcionan; `WebFetch` puede no funcionar en una sesión abierta antes de que se abriera la red).
- Agentes `Agent` (`general-purpose`, `model: "sonnet"`, `effort: "high"`): SOLO para las fuentes que fallen en Python (paso 2) y para la extracción semanal de la cola larga (paso 2b).

Principio: **el script hace el trabajo; los agentes solo entran cuando el script falla.** Un día normal no debería lanzar ningún agente.

## 0. Preparación
La sesión programada arranca vacía (sin repo): clona el código en `/tmp/code` y trabaja ahí. Si en cambio estás en una sesión normal con el repo de código, trabaja en él.
1. Código: `rm -rf /tmp/code && git clone -q --depth 1 -b main https://github.com/Luisp00/Madrid-de-Noche.git /tmp/code`. Todo lo que sigue se ejecuta con `cd /tmp/code`.
2. `pip install -q requests beautifulsoup4 lxml` (un contenedor nuevo no las trae) y comprueba `node -e "require('playwright')"`.
3. `mkdir -p run/data run/db run/out run/site`.
4. HOY = fecha en Europe/Madrid (si son las 00:00–05:59, el día anterior). `scrape.py` y `merge.py` la calculan solos; solo pásala con `--today` si quieres forzarla.
5. Marca el inicio: `ArtifactData` get `meta/status` (anota `version`) y `update` con `if_version` y data `{"running": true, "runStartedAt": "<ISO UTC ahora>"}`.

## 1. Estado actual de la base de datos
`ArtifactData` action `query`, collection `chunks`, query `{"limit": 100}`, `out_dir` = `<repo>/run/db`. Apunta la versión de cada chunk que imprime el resultado en `run/db/versions.txt`, una por línea (`chunk-00 3`, `chunk-01 3`, …). Son 5–10 líneas.

## 2. Extracción con Python
`python3 scrape.py --out run/data` (tarda 3–8 min; ejecuta todos los parsers de `scrape/sources/` en paralelo, con caché de 1 h). Imprime por fuente el nº de eventos o el error, y deja `run/data/_scrape_report.json` con la lista `failed` (parsers con error o con menos eventos que su `MIN_EVENTS`).
- **Enriquecimiento de precios:** `python3 enrich.py run/data` visita la página de compra de los eventos que han quedado sin precio (Xceed, DICE, Fever, WHAN, Taquilla…) y rellena precio/estado. Deja `run/data/_enrich_report.json`.
- Si `failed` está vacío → paso 3.
- Si hay fallos, reintenta una vez solo esos: `python3 scrape.py --out run/data --only mod1,mod2`. Si un parser falla por **error de código** (excepción, no por bloqueo de la web), lanza un agente `Agent` con `model: "opus"`, `effort: "high"` para que lo diagnostique y lo arregle en `/tmp/code` (el usuario quiere que la revisión y reparación de los scripts la haga Opus 5.5 en high); vuelve a ejecutar ese parser y, si el arreglo funciona, guarda el parche (`git -C /tmp/code diff > run/out/patch_<modulo>.diff`) y cópialo a `data/patches/` de la web (paso 6) para aplicarlo al repo. Lo que siga fallando pasa al respaldo:

### 2a. Respaldo con agentes (solo fuentes fallidas)
Para cada módulo fallido, lanza un agente `Agent` (`model: "sonnet"`, `effort: "high"`, en background) con el prompt estándar del apéndice (cabecera común + el bloque de la fuente correspondiente, **solo esa fuente**), pidiéndole que guarde en `run/data/agente_<modulo>.json`. Correspondencia módulo → bloque del apéndice: `fever`→A; `technoairlines`, `dice`, `fulltechno`, `technoparty`, `xceed` (https://xceed.me/es/madrid/events), `whan` (https://app.whan.es/explore)→B; `bynova`, `nightlifemadrid`→C; `taquilla`, `notikumi`, `dondego`, `discotech`, `allevents`→D; `siroco`, `salaelsol`, `lariviera`, `wurlitzer`, `galileo`→E (solo esa sala); `applinkers`, `allmadridnightlife`→F; `conciertos_club`, `laganzua`, `madridenvivo`, `esmadrid`→G. Resident Advisor no tiene parser activo (`scrape/disabled/ra.py` usa su API saltándose la protección anti-bot y se ha dejado fuera; Techno Airlines replica la mayoría de sus eventos). Acceso a la web en el agente: WebFetch si funciona; si no, `node tools/fetch.js URL` por Bash. Espera como mucho 40 min; si no llega, sigue sin esa fuente.

### 2b. Cola larga con agentes (lunes y jueves, o si el `meta/status` anterior tiene `longTailAt` de hace más de 4 días)
Fuentes sin parser: webs de salas (bloque E, menos Siroco, El Sol y La Riviera, que ya tienen parser), listas de clubs sin parser (Clubbable, Discomadrid, Discoruta, Discotecas Gratis, Salir Madrid: bloque C sin Bynova/Nightlife Madrid) y agregadores menores (Tardeo Madrid, Yass Party, Songkick, Hoy Madrid: bloque F sin Applinkers/All Madrid Nightlife). Lanza esos 3 agentes (`model: "sonnet"`, `effort: "high"`, background) con salida en `run/data/agente_salas.json`, `run/data/agente_listas.json`, `run/data/agente_extra.json`. Espera hasta 60 min. Añade `"longTailAt": "<ISO>"` al status final. Los días que no toca, los eventos de esas fuentes se conservan de la última vez (merge.py mantiene lo no visto hasta 3 extracciones).

## 3. Fusión
`python3 -I merge.py run/data run/db run/out`
- Imprime `unicos` (eventos de hoy), `eventosTotales` (lo que quedará), `nuevos`, `actualizados`, `sinCambios`, `quitados…`, `porFuente`; también en `run/out/summary.json`.
- Genera `run/out/chunks/chunk-NN.json`, `run/out/writes.json`, `run/out/events.json`, `run/out/status.json`.
- Si avisa de chunks sin versión conocida, falta `run/db/versions.txt` (paso 1).
- **Si `unicos` < 300**, algo grave ha fallado (un día normal da 900–1300): no subas; escribe `meta/status` con `running:false` y `lastError` y termina explicándolo.

## 4. Subida al artifact
Ejecuta cada entrada de `run/out/writes.json` con `ArtifactData`: `set` (collection `chunks`, doc_id, `file_path`, `if_version` tal como vienen) o `delete`. Si una falla por versión, `get` de ese chunk (con `out_dir` para no llenar el contexto) y repite con la versión correcta. Si falla por tamaño, baja `CHUNK_BYTES` en merge.py a 120000 y repite 3 y 4.

## 5. Meta
Añade a `run/out/status.json` (con python) `"failedSources": [nombres de las fuentes que no dieron datos hoy]` y, si tocaba cola larga, `"longTailAt"`. Luego `ArtifactData` get `meta/status` (versión) y `set` con `file_path` = `run/out/status.json` e `if_version`.

## 6. Web pública
`python3 -I build_site.py run/out run/site` genera `run/site/` (index.html, data/events.json, data/status.json, .nojekyll). La publicación en la rama `gh-pages` **no la hace la sesión programada**: una sesión lanzada por tarea no tiene permiso de push al repo (comprobado el 30 oct: 403 del proxy git, sin `add_repo` ni `create_session`). La publica el workflow de GitHub Actions `.github/workflows/update.yml` (ejecuta este mismo pipeline cada noche) o una sesión interactiva de Claude Code con el repo:
```
git fetch origin gh-pages && git worktree add --detach /tmp/ghp origin/gh-pages && cd /tmp/ghp && git checkout -B gh-pages && cp -r <repo>/run/site/. . && git add -A && git -c user.name=mdn-bot -c user.email=bot@madrid-de-noche commit -m "Datos $(date -u +%F)" && git push origin gh-pages; cd - && git worktree remove --force /tmp/ghp
```
Si eres la sesión programada, no intentes el push y no lo cuentes como fallo.

## 7. Informe
3–5 líneas: eventos únicos y totales, nuevos/actualizados/quitados, fuentes que fallaron en Python y si el respaldo las cubrió, si se hizo la cola larga, y si la web pública se publicó. Si una fuente lleva dos días fallando (compara con `failedSources` del status anterior), dilo.

---

## Apéndice: prompts de los agentes de extracción (respaldo y cola larga)

Cabecera común de cada prompt (sustituye `{HOY}`, `{FIN}` = HOY+14, `{RUTA}`):

> *Lee <repo>/SPEC.md primero y síguelo exactamente. Hoy es {HOY} (Europe/Madrid). Ventana: {HOY} a {FIN}. Para abrir webs usa WebFetch/WebSearch; si WebFetch falla o la web lo bloquea, usa por Bash `node <repo>/tools/fetch.js "URL"` (texto visible + enlaces; `--max 60000`, `--links 400`, `--raw`). Nada de curl ni python contra webs externas. Presupuesto ~70 páginas. Deduplica dentro del archivo por sala+fecha+título parecido fusionando fuentes. Nada inventado; solo Madrid y la ventana. Guarda el resultado en {RUTA} (array JSON con el formato de SPEC.md) y valida con `python3 -I -c "import json;d=json.load(open('{RUTA}'));print(len(d))"`. Informa en <120 palabras: eventos por fuente y qué falló.*

### Agente A → data/fever.json — fuente "Fever"
Listados: https://feverup.com/madrid/vida-nocturna-clubs · https://feverup.com/en/madrid/night-clubs · https://feverup.com/en/madrid/themed-parties · https://feverup.com/en/madrid/pub-crawl · venue pages https://feverup.com/es/madrid/venue/fabrik , /en/madrid/venue/teatro-kapital , /en/madrid/venue/teatro-eslava , /en/madrid/venue/enbabia-infused , /es/madrid/venue/vg-fuenlabrada , /en/madrid/venue/independance-club . Detalle: https://feverup.com/m/{ID}/en (fechas con año, horas, dirección, tramos de precio, música, edad, agotado). Recurrentes (p. ej. Kapital https://feverup.com/m/121772/en): un objeto por noche con sesión/precio en el calendario. Descarta bingo, shisha, karaoke, escape rooms, cenas-espectáculo y los productos "Fiesta VIP sin esperas". Pub crawls: tipo "otro", solo las próximas 3 noches. Presupuesto 60 fetches.

### Agente B → data/electronica.json — fuentes "Resident Advisor", "Techno Airlines", "ma.to", "Shotgun", "DICE", "Fulltechno", "Technoparty"
https://technoairlines.com/events/madrid (descubrimiento masivo; detalle https://technoairlines.com/event/{slug} da enlace RA/DICE) · https://ra.co/guide/es/madrid y https://ra.co/events/es/madrid (+ /techno) para IDs; detalle https://ra.co/events/{id} (precio "Cost", lineup, género, edad, dirección); usar ra.co, no de.ra.co; ignorar páginas con fechas antiguas · ma.to (buscar "ma.to madrid techno") · https://shotgun.live/es/cities/madrid (+ detalle /es/events/{slug}: dirección, edad, dress code) · DICE: buscar "dice.fm madrid tickets {mes}" / "dice.fm specka" / "dice.fm mondo" / "dice.fm cadavra" y leer https://dice.fm/event/... (precio poco fiable → null salvo claro) · https://fulltechno.club/eventos-techno-madrid-hoy/ y https://fulltechno.club/poblacion/madrid/ · https://technoparty.es/agenda/madrid/ .

### Agente C → data/listas.json — fuentes "Clubbable", "Discomadrid", "Discoruta", "Salir Madrid", "Discotecas Gratis", "Bynova", "Nightlife Madrid"
https://www.clubbable.com/Madrid (+ /Madrid/{Club}/{DD-Mon-YYYY}: horas, dirección, edad mínima, mesas) · https://discomadrid.com/discoteca/panda-club/ , /discoteca/club-graf/ , /listas/precios-mitty/ y otras /discoteca/... · https://www.discoruta.com/discotecas/liberata-madrid/ y otras · https://salirmadrid.es/en/boite-live y otras salas · https://discotecasgratis.com/discotecas/stardust (solo datos fijos) · https://bynovanightlife.com/en/madrid-this-weekend/ , /en/nightclubs-madrid/ , /en/whats-on/ (listas por día de semana con precio-desde, edad, zona, dress code → un objeto por sala y noche dentro de la ventana, status "desconocido") · https://nightlifemadrid.com/fiestas-madrid/ (fiestas semanales → fechas dentro de la ventana). Opium Madrid y Oh My Club están cerrados en 2026: omitir salvo evento fechado. **Madrid Lux (madridlux.com) no se usa como fuente.** Salas que suelen faltar y hay que buscar expresamente (web propia, Fourvenues, Xceed o Instagram vía WebSearch): Teatro Barceló, Gabana 1800, Specka, Marula Café, Medias Puri, Uñas Chung Lee, Toni 2, Stardust, Liberty Supper Club, Villa Panthera, Istar, Sala Caracol.

### Agente D → data/taquillas.json — fuentes "Taquilla.com", "Eventbrite", "Atrapalo", "Discotech", "Notikumi", "AllEvents", "Dondego"
https://www.taquilla.com/conciertos/discotecas/madrid y https://www.taquilla.com/conciertos/discotecas (filas de Madrid), venue https://www.taquilla.com/humanes-de-madrid/fabrik-humanes , eventos https://www.taquilla.com/entradas/{slug} (un objeto por sesión) · Eventbrite solo hosts .com/.ca: https://www.eventbrite.com/d/spain--madrid/events--this-weekend/ , https://www.eventbrite.ca/d/spain--madrid/parties--today , https://www.eventbrite.com/d/spain--madrid/rave-party/ , + WebSearch "eventbrite madrid fiesta {mes}" (precios normalmente no visibles → null) · https://www.atrapalo.com/entradas/madrid/musica/bares-fiestas-y-discotecas/ · https://app.discotech.me/madrid/events (+ ?page=2,3; sin precios) · https://www.notikumi.com/place/Madrid?lang=en · https://allevents.in/madrid/parties (solo ocio nocturno) · https://dondego.es/madrid/fiestas/ .

### Agente E → data/salas.json — fuente = nombre de la sala, o "Fourvenues"
https://siroco.es/agenda/ · https://www.mondodisko.es/eventos/ (+ /eventos/{id}) · https://www.labtheclub.com/agenda/ (enlaces a ra.co/events/{id} → leerlos para precio/edad) · https://independanceclub.com/en/collections/conciertos/conciertos y /collections/tardeos · https://shokomadrid.com/collections/eventos-shoko-madrid (precio 0 € = null) · https://berlincafe.es/programa/ · https://www.mobydickclub.com/programacion.php · https://salaelsol.com/agenda/ · https://ochoymedioclub.com/conciertos/ y /entradas-club/ · https://salariviera.com/conciertossalariviera/ · https://salachango.es/ y /eventos · https://vandidoclub.com/ y https://site.fourvenues.com/en/vandido · https://site.fourvenues.com/en/nazca-club · https://www.b12madrid.com/entradas-b12-madrid · https://web.bodeguitadeenmedio.es/entradas-bodeguita-madrid · https://www.salabut.es/agenda-sesiones/ · https://teatroeslava.com/conciertos-madrid/ y /clubbing/ · https://salirmadrid.es/en/boite-live · intentar también https://www.salacaracol.com/programacion/ , https://conciertoscopernico.com/ , https://marulacafe.com/mad/ , https://www.teatrobarcelo.com/ , https://www.goyasocialclub.com/event/ , https://iconmadrid.com/ , https://teatrokapital.com/en/nightery_event/ , https://www.specka.es/ , https://gabana.es/ , https://mediaspuri.com/ , https://www.libertysupperclub.com/ . Conciertos solo si empiezan a las 20:00 o más tarde (tipo "concierto"); sesiones tipo "club"; tardeos tipo "tardeo". Series semanales sin fecha explícita: solo las fechas que la página muestra.

### Agente F → data/extra1.json — fuentes "Applinkers", "All Madrid Nightlife", "Tardeo Madrid", "Yass Party", "Bclever", "Studentfy", "Songkick", "Hoy Madrid"
https://applinkers.com/entradas/madrid/listas-gratis/ (réplica de Fourvenues: PRIORIDAD ALTA) + https://applinkers.com/entradas/madrid/{lunes|martes|miercoles|jueves|viernes|sabado|domingo}/ + /entradas/madrid/hoy/ + páginas de sala /entradas/madrid/{sala}/ (fecha, hora, sala, precio-desde, "gratis hasta la X" → free=true, música, edad) · https://www.allmadridnightlife.com/en/day-parties-madrid (tardeos) y https://www.allmadridnightlife.com/en/ (#agenda) · https://tardeomadrid.es/ · https://yassparty.com/en/madrid/ · https://bclever.ai/?l=madrid (+ /eventos/madrid/...) · https://www.studentfy.com/madrid/events · https://www.songkick.com/metro-areas/28755-spain-madrid/genre/electronic y /this-weekend · https://www.hoymadrid.app/planes-conciertos-hoy-en-madrid/ .

### Agente G → data/extra2.json — fuentes "Conciertos.club", "Madrid en Vivo", "La Ganzúa", "esMadrid"
https://conciertos.club/madrid (~350 eventos: fecha, hora, sala, género, precio; quedarse con los que empiezan ≥20:00 o etiquetados Electrónica/Dance/DJ; "concierto" para directo, "club" para DJ) · https://madridenvivo.com/agenda-de-conciertos-y-espectaculo/clubbing/ y https://madridenvivo.com/agenda-de-conciertos-y-espectaculo/ (solo hoy) · https://www.laganzua.net/conciertos/madrid (+ madrid-pagina-2) · https://www.esmadrid.com/agenda-musica-madrid (grandes conciertos ≥20:00).
