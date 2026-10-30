# Fuentes nuevas para Madrid de Noche (evaluación del 30 oct 2026)

Probado desde este entorno (proxy + Chromium headless con `tools/fetch.js`, y `curl` para comprobar si responde) con unas 75 páginas o llamadas. La ventana considerada es del 30 oct al 13 nov de 2026. El solapamiento se ha estimado cruzando los nombres de sala con `run/data/*.json` (1665 eventos de la extracción actual). **No se ha escrito ningún parser.** Las llamadas de ejemplo de abajo solo son para orientar a los agentes.

## Tabla resumen

| # | Fuente | Acceso | Eventos Madrid (14 d) | Campos clave | Solape | Prioridad |
|---|---|---|---|---|---|---|
| 1 | **Resident Advisor – GraphQL** (`ra.co/graphql`) | JSON por POST con curl (200), sin clave | **189** | hora inicio/fin, `cost`, `minimumAge`, line-up, género, dirección, tramos de entrada con `SOLDOUT`/`VALID` | ~60 % con Techno Airlines; hoy RA aporta **0** eventos propios | **ALTA** |
| 2 | **Xceed** (`xceed.me` + API `events.xceed.me/v1`) | HTML servido con JSON-LD `Event` y API JSON pública, sin clave | ~90 (API), 195 en el listado web (todas las fechas) | hora, precio "desde" y ofertas, `typicalAgeRange`, **dress code**, política de edad, estado (AGOTADO / venta finalizada), géneros, artistas | ~40 %; trae Cuenca Club/Pirandello, CORE, Club Malasaña, Jade, Barco, Casa Amante, High Club Room, Hood Dogs, Enbabia | **ALTA** |
| 3 | **WHAN** (`app.whan.es`, ticketera de clubs) | API JSON pública `api/v1/public/explore` + `api/v1/event/{slug}` (curl 200) | **104** | hora, tramos de precio, agotado por tramo, **lista gratis hasta la X**, edad (+18/+20), campo `dressCode`, reservados | ~50 %; nuevas: Victoria, Los Amantes, Dopamina, Makáá, La Flaca (tardeo), Nômâda, Keli; también Ištar, Panthera, Liberty, Rubicón, Todos Santos, Nazca | **ALTA** |
| 4 | **DICE – páginas de ciudad** (`dice.fm/browse/madrid-5d8cef380de1e404dc962211/music/{dj,party,gig}`) | HTML con `__NEXT_DATA__` (curl 200) | ~24 por categoría (~70 en total) | hora inicio/fin, `amount_from` (céntimos), `status` (on-sale/agotado), sala y dirección | alto con DICE vía búsqueda, pero es mucho más estable | **ALTA** (mejora de una fuente actual) |
| 5 | **iCal/REST de webs de salas** (Siroco, Sala El Sol, La Riviera) | `.ics` y REST de WordPress (curl 200) | Siroco 39, El Sol 18, Riviera 11 | hora exacta, URL de la ficha; Riviera da `cost` | 100 % (mismas salas), mejor calidad y menos fetches | MEDIA |
| 6 | Wurlitzer Ballroom (`wurlitzerballroom.com/agenda`) | HTML servido | ~15 | puertas, precio, género, "taquilla" | bajo (3 eventos hoy) | MEDIA |
| 7 | Sala Galileo Galilei (`salagalileo.es/programacion/`) | HTML servido; entradas en geeticket/oneboxtds | ~8 | fecha, hora, enlace de compra | medio (4 hoy) | BAJA-MEDIA |
| 8 | Wegow (API `wegow.com/api/events/?cities=3117735`) | JSON (curl 200) | 5 (solo 20 destacados, sin paginar) | fecha, `purchase_url`, cancelado | alto (grandes recintos) | BAJA |
| 9 | Clubs In Madrid (`clubsinmadrid.com/es/entradas`) | HTML servido | ~30 | fecha, sala; las entradas enlazan a WHAN | 100 % con WHAN | BAJA |
| 10 | Enterticket (`enterticket.es`) | HTML servido | 2–4 (Brunch Electronik) | precio desde, fecha | bajo | BAJA |
| 11 | Luma (`luma.com/madrid`), Meetup | HTML servido | pocos de ocio nocturno | precio, agotado | — | BAJA |
| 12 | Entradium | SPA (sin datos en el HTML), la búsqueda no filtra por ciudad | ? | — | — | BAJA |
| — | Fourvenues, Shotgun, Ticketmaster, Bandsintown, See Tickets, Tomaticket, El Corte Inglés, Giglon, TicketSwap, Instagram, Nox Agency, DJ Mag ES | **Bloqueadas** (403/429/challenge) | — | — | — | inaccesibles |
| — | Guía del Ocio, Madrid Diferente, Entradas.com, cadavra.es, honky-tonk.es, lacoquetteblues.com, istarmadrid.com, lulaclub.es, Plan B Madrid, Salir por Madrid, Nochea, Muchanoche | **El proxy rechaza la conexión** (CONNECT 502: dominio no permitido o inexistente) | — | — | — | inaccesibles |
| — | Le Cool Madrid (sin publicar), The Gay Agenda (cerrada), bresh.es (dominio aparcado), Mondo Sonoro (agenda vacía), Time Out (solo artículos) | Sin agenda útil | 0 | — | — | descartadas |

---

## ALTA

### 1. Resident Advisor vía GraphQL — `https://ra.co/graphql`
- **Cubre:** toda la escena electrónica: LAB theCLUB, The Bassement, Lula, El Sótano, Flat HiFi, Goya Social Club, Siroco, Casa Amante, Hangar48, Cadavra, Skin, Subcero, Club Malasaña, Nômade Temple, Sala Cocó, Specka, X Private, Lasociaciøn, Core, Fabrik, Mondo, etc.
- **Acceso:** POST con JSON con `curl`. Responde 200 sin cookies ni clave, aunque la web de ra.co da 403 a cualquier navegador desde aquí. Área de Madrid: `areas:{eq:41}`. Paginación `pageSize:100, page:N`; `totalResults` da 189 para el 30 oct–13 nov.
  ```
  curl -s https://ra.co/graphql -H 'Content-Type: application/json' -H 'Referer: https://ra.co/events/es/madrid' \
   -d '{"query":"{ eventListings(filters:{areas:{eq:41},listingDate:{gte:\"2026-10-30\",lte:\"2026-11-13\"}},pageSize:100,page:1){ totalResults data{ event{ id title date startTime endTime cost minimumAge isTicketed contentUrl genres{name} artists{name} venue{name address} tickets(queryType:AVAILABLE){title priceRetail validType} } } } }"}'
  ```
- **Campos:** inicio y fin, `cost` ("18€"), `minimumAge`, géneros, artistas, dirección y entradas por tramo con precio y `validType` (SOLDOUT/VALID), de donde sale el estado. No da dress code.
- **Solape:** Techno Airlines replica buena parte de RA (sobre el 60 %), pero la extracción actual tiene 0 eventos con fuente "Resident Advisor" y Techno Airlines no trae edad, precio por tramo ni estado.
- **Por qué alta:** desbloquea la fuente electrónica más completa con datos estructurados, en solo 2 llamadas.
- **Riesgo:** es una API no documentada y puede cerrarse o limitar peticiones. Hay que usar pocas llamadas y conviene un fallback a Techno Airlines.

### 2. Xceed — `https://xceed.me/es/madrid/events` + `https://events.xceed.me/v1/...`
- **Cubre:** clubs y fiestas comerciales y electrónicas, tardeos y fiestas universitarias: Cuenca Club (Sala Pirandello), Pirandello I-II-III, Panda Club, Goya Social Club (su web remite a Xceed), CORE, Club Malasaña, Jade Club, Barco Sound House, Casa Amante, High Club Room, Hood Dogs Planet, Enbabia Library, Lula, Nazca, Seven, Strong, ART Madrid Club, Joy Eslava (tardeo) y Marabú. Clubbingspain vende a través de Xceed, así que queda cubierto también.
- **Acceso:**
  - El listado web viene servido en el HTML (curl 200, ~1 MB). Muestra 24 de 195 eventos con "VER MÁS" por JS y trae 3 bloques JSON-LD `Event`.
  - Cada ficha `https://xceed.me/es/madrid/event/{slug}/{id}` lleva JSON-LD completo (`offers` con precio, `availability`, `typicalAgeRange`, `location.address`, `performer` con géneros) y, en el JSON embebido, `dressCode` (p. ej. "Ven como estás") y `agePolicy`.
  - API JSON pública sin clave:
    - `https://events.xceed.me/v1/events?limit=500&offset=0&startTime={unix}&endTime={unix}` devuelve **todas las ciudades**; los filtros `city`/`cityId` se ignoran, así que hay que filtrar por `venue.city.slug == "madrid"`. 2 páginas (~1000 eventos) dieron 89 de Madrid.
    - `https://events.xceed.me/v1/events/{legacyId}` da el detalle: `doorsOpening`, `about`, ajustes, dress code y edad.
- **Campos:** inicio y fin, precio "desde" y tramos (incluidas mesas VIP), estado (AGOTADO, VENTA FINALIZADA, `eventStatus`), edad, dress code, géneros, line-up y dirección.
- **Solape:** las salas aparecen hoy con 1–3 eventos cada una. Cuenca/Pirandello y Hood Dogs no aparecen nunca. Estimado: ~40 % ya cubierto.
- **Por qué alta:** es la ticketera de discotecas más grande que sí es accesible, tiene dress code y edad estructurados y la API es estable.

### 3. WHAN — `https://app.whan.es/explore`
- **Cubre:** clubs de lujo de Salamanca y Chamberí y tardeos: Todos Santos, Los Amantes, Ištar, Panthera (Villa Panthera), Rubicón, Victoria, Liberty Club (Liberty Supper Club), Nazca, Dopamina, Makáá Social Club, La Flaca (tardeo), Nômâda y Keli. Es la ticketera que usan clubsinmadrid.com y varias salas que el RUNBOOK da como "difíciles" (Istar, Liberty, Villa Panthera).
- **Acceso:** la web es JS (Symfony + Vue), pero su API pública responde a curl sin clave:
  - Listado: `https://app.whan.es/api/v1/public/explore?page[number]=N&page[size]=48` (el tamaño máximo efectivo es 48). `meta` da 277 eventos en total y 7 páginas, todos de toda España. Hay que filtrar por `attributes.club.province == "Madrid"`.
  - Detalle: `https://app.whan.es/api/v1/event/{slug}?preview=1`.
  - Artistas: `/api/v2/public/events/{id}/artists`.
  - Detrás hay Cloudflare: el curl directo funcionó, pero el navegador pasa por un challenge.
- **Campos:** inicio y fin, `eventType`, `musicType`, tramos con `price` y `sold`, listas gratis con hora límite ("GUEST LIST CHICAS 01:00"), edad (texto "+20"), `dressCode` (a menudo vacío), reservados desde X € y enlace a Maps.
- **Volumen:** 277 eventos de Madrid en total, **104 en la ventana**.
- **Solape:** Todos Santos (13), Rubicón (12), Istar (11) y Nazca (29) ya llegan por Madrid Lux, Applinkers y otras fuentes. Victoria, Los Amantes, Dopamina, Makáá, La Flaca y Nômâda no aparecen. Estimado: ~50 % ya cubierto.
- **Por qué alta:** son 100 eventos con precio y estado reales de un segmento (Serrano/VIP) que hoy solo tiene precios "desde" de las webs de listas.

### 4. DICE por páginas de ciudad — `https://dice.fm/browse/madrid-5d8cef380de1e404dc962211[/music/dj|/music/party|/music/gig]`
- **Acceso:** HTML servido (curl 200) con `__NEXT_DATA__` → `props.pageProps.events`. Cada página trae 23–30 eventos. La paginación (`nextCursor`) se hace por XHR y no funciona como parámetro de URL.
- **Campos:** `event_start_date`/`event_end_date`, `price.amount_from` (céntimos), `status` (on-sale, sold-out…), sala y dirección.
- **Volumen:** DJ 24 y Party 23 en la ventana (Cadavra, Specka, The Bassement, Café Berlín, Siroco, El Sol, Independance, Teatro Magno, El Sótano), más Gig.
- **Solape:** alto con la DICE actual (46 eventos por WebSearch), pero es más fiable y barato: 3 páginas sustituyen muchas búsquedas.
- **Por qué alta:** cambio pequeño en el agente B que da precio y estado reales.

## MEDIA

### 5. Feeds iCal/REST de salas que ya usamos
- `https://siroco.es/events.ics` (Events Manager): 51 eventos, **39 en la ventana**, con URL de cada ficha.
- `https://salaelsol.com/events.ics`: 41 eventos, **18 en la ventana**.
- `https://salariviera.com/wp-json/tribe/events/v1/events?start_date=2026-10-30&end_date=2026-11-13`: JSON, **11 eventos** con `start_date` y `cost`. También `https://salariviera.com/?ical=1`.
- Probados sin resultado: `/events.ics` y `?ical=1` en Berlín, Moby Dick, Ochoymedio, Changó, But, Eslava, Copérnico, Clamores, Gruta 77, Icon, Mondo e Independance (devuelven HTML). Gruta 77 y Teatro Barceló usan EventON, pero sin REST público.
- **Por qué media:** no traen eventos nuevos, pero dan horas exactas y bajan fetches del agente E.

### 6. Wurlitzer Ballroom — `https://wurlitzerballroom.com/agenda`
- HTML servido (Next.js). Conciertos casi a diario desde las 21–22 h (punk, garage, rock) con puertas, precio ("10€") y "Entradas en taquilla". Hoy solo hay 3 eventos suyos.
- **Por qué media:** sala nocturna de conciertos con buena calidad de datos, pero de nicho.

## BAJA
- **Sala Galileo Galilei** (`salagalileo.es/programacion/`): HTML servido con fecha, hora y enlace a geeticket/oneboxtds. Unos 8 eventos, muchos de humor, magia o pases de 19:30, así que no son nocturnos.
- **Wegow API** (`https://www.wegow.com/api/events/?page_size=20&cities=3117735`, 3117735 = id GeoNames de Madrid): JSON accesible, pero solo devuelve 20 destacados y no pagina. En la ventana: 5 conciertos grandes (Movistar Arena, Las Ventas, Riviera). `wegow.com/es/fiestas/madrid` no lista fiestas.
- **Clubs In Madrid** (`clubsinmadrid.com/es/entradas`): HTML servido con unos 30 eventos de Rubicón, Liberty, Victoria, Istar, Los Amantes y Todos Santos. Las entradas enlazan a `app.whan.es`, así que es un subconjunto de WHAN.
- **Enterticket**: la portada servida solo muestra Brunch Electronik Madrid (7 y 8 nov, desde 27 €). Hay pocos eventos de Madrid.
- **Luma / Meetup**: accesibles, pero son sobre todo networking y tecnología. Algún "afterwork" o "Art After Hours" con precio o agotado. No compensa.
- **Entradium**: SPA y la búsqueda no filtra por ciudad (salen pádel y museos). Lo usan algunas salas pequeñas.

## Salas que faltaban (resultado)
| Sala | Resultado |
|---|---|
| Teatro Barceló | La web carga, pero el calendario EventON dice "NO EVENTS" en oct y nov. Solo tiene sesiones fijas: lunes, miércoles Fuego (+18), jueves Rookies (+19), viernes y sábado (+25). No aparece en Xceed ni en WHAN; probablemente vende por Fourvenues (bloqueado). Seguir con Madrid Lux y Applinkers. |
| Gabana 1800 | La web solo tiene sesiones y eventos corporativos, sin agenda. |
| Medias Puri | Web con información fija: viernes, sábado y vísperas de 23:59 a 06:00, +18, sin dress code. Los botones de entradas van por JS (posiblemente Fourvenues). |
| Liberty Supper Club / Ištar / Villa Panthera | **Están en WHAN** (fuente 3). |
| Goya Social Club | Su web remite a **Xceed** (fuente 2); también está en RA. |
| Marula Café | marulacafe.com solo muestra el local de Barcelona (Escudellers 49). La sede de Madrid parece cerrada. |
| Sala Caracol | Error 521: el servidor no responde. |
| Costello | La web está desactualizada (posts de 2020) y la programación sale vacía. |
| Cadavra, Honky Tonk, La Coquette, Istar, Lula (webs propias) | El proxy rechaza la conexión. Ya están cubiertas por otras fuentes (28, 17, 13, 11 y 18 eventos). |
| Uñas Chung Lee, Toni 2, Stardust | No se encontró ninguna web con agenda. Siguen dependiendo de Madrid Lux, Discotecas Gratis y similares. |

## Inaccesibles desde este entorno
- **Fourvenues** (`site.fourvenues.com`, `www.fourvenues.com`, `web.fourvenues.com`): 403 "No bots on the guest list" incluso con Chromium y 15 s de espera. El challenge necesita `challenges.cloudflare.com`, que el proxy rechaza. `api.fourvenues.com` da 401 porque pide clave. Applinkers sigue siendo la única réplica.
- **Shotgun**: 429 tanto con curl como con navegador (también `/api/graphql`).
- **Ticketmaster España**: 403 `{"response":"block"}`. La Discovery API exige clave.
- **Bandsintown**: 403 de Cloudflare ("you have been blocked").
- **See Tickets ES**: 403 "Unusual Traffic Detected".
- **Tomaticket**: challenge de Cloudflare.
- **El Corte Inglés Entradas, Giglon, TicketSwap, Nox Agency, DJ Mag ES**: 403.
- **Instagram**: 429 en la web y 401 en la API (los Linktree sí cargan, p. ej. Madrid No Descansa, pero solo enlazan a WhatsApp o a su web).
- **Conexión rechazada por el proxy**: guiadelocio.com, madriddiferente.com, entradas.com, planbmadrid.es, salirpormadrid.com, nochea.es, muchanoche.com, breshparty.com, cadavra.es, honky-tonk.es, lacoquetteblues.com, istarmadrid.com, lulaclub.es. Si alguno es imprescindible, revisar la red del entorno.

## Recomendación de integración (orden)
1. Añadir al agente B **RA GraphQL** (2 llamadas) y **DICE browse** (3 páginas).
2. Nuevo agente o ampliación del C con **WHAN API** (7 páginas de listado y detalle solo para precio y estado) y **Xceed API** (2–3 llamadas de listado + JSON-LD o detalle por evento).
3. En el agente E, sustituir el HTML de Siroco, El Sol y Riviera por sus feeds iCal/REST.
4. Nota: estas fuentes son llamadas JSON con curl, no WebFetch. La regla del RUNBOOK "solo WebFetch/WebSearch, nada de curl" tendría que admitir excepciones para estos endpoints, o habría que usar `tools/fetch.js --raw` para los GET (Xceed, WHAN, DICE, iCal). RA GraphQL es un POST, así que necesita curl o Node.
