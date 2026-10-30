# Madrid de Noche — especificación de extracción

## Objetivo
Extraer eventos nocturnos de Madrid (sesiones de discoteca, fiestas, conciertos nocturnos, afters, bares con DJ, tardeos, pub crawls) de una fuente web y guardarlos como JSON normalizado. Ventana: desde HOY hasta HOY+14 días (incluidos). Hoy = fecha actual en Europe/Madrid (si son las 00:00–05:59, "hoy" es la noche que empezó el día anterior).

## Reglas de acceso
- Solo WebFetch y WebSearch. Nada de curl/python contra webs externas (está bloqueado).
- Si WebFetch rechaza una URL por "not on allowlist", haz primero una WebSearch que la devuelva (p. ej. `feverup madrid night clubs`) y reintenta.
- Si una página devuelve datos claramente antiguos (fechas pasadas), ignórala.
- Sé eficiente: una página de listado + solo las páginas de detalle necesarias para completar precio/hora/dirección. Máximo ~40 fetches por fuente.

## Formato de salida
Un archivo JSON con un array de objetos. Guárdalo en la ruta que te indiquen. Cada objeto:

```json
{
  "title": "Nombre del evento (sin el nombre de la sala si ya va en venue, salvo que sea parte del nombre)",
  "date": "2026-10-31",            // noche en que EMPIEZA. Un evento que empieza 00:30 del día 1 pertenece a la noche del 31 (date=2026-10-31).
  "start": "23:30",                // o null
  "end": "06:00",                  // o null
  "venue": "Teatro Kapital",       // nombre canónico de la sala (ver lista)
  "address": "C/ Atocha 125, 28012 Madrid",   // o null
  "zone": "Atocha",                // ver tabla de zonas; "Otros" si no se sabe
  "venueKind": "discoteca",        // lo pone merge.py desde scrape/venues.json: discoteca | sala | bar | recinto | rooftop | pubcrawl | otro (pubcrawl = quedada que recorre varios bares; lo detecta por el título). No hace falta rellenarlo
  "type": "club",                  // club | concierto | fiesta | after | bar | tardeo | festival | otro
  "music": ["reggaeton","comercial"],   // etiquetas de la lista cerrada; [] si no se sabe
  "priceMin": 15,                  // precio más bajo de entrada general en €, número; 0 si hay lista/entrada gratis; null si no se publica
  "priceMax": 25,                  // precio más alto de entrada general (sin mesas VIP); null si no se sabe
  "priceText": "Lista gratis hasta 1:00 · Anticipada 15 € con 1 copa · Taquilla 20 €",  // resumen legible, máx 120 caracteres, o null
  "free": false,                   // true si existe alguna forma de entrar gratis (lista, invitación, antes de cierta hora)
  "dressCode": "Elegante, no deportivas",   // texto literal/resumido si la fuente lo indica; null si no
  "ageMin": 18,                    // número o null si no se indica. Si distingue chicas/chicos, usa el menor y ponlo en priceText o description
  "lineup": ["DJ Nano", "Alex Martini"],    // [] si no hay
  "description": "2 copas hasta la 1:00. Mesas VIP desde 200 €.",  // 1-3 frases útiles (incluye lo que no cabe en otros campos: copas incluidas, reservados, salas), máx 400 caracteres, o null
  "status": "disponible",          // disponible | ultimas | agotado | desconocido
  "sources": [{"name": "Fever", "url": "https://feverup.com/m/664043"}],   // name: nombre corto de la fuente (siempre el mismo para la misma web); url: página PROPIA del evento. Solo si no existe página propia, la del listado
  "ticketUrl": "https://feverup.com/m/664043"   // mejor enlace para comprar/apuntarse (página de compra del evento concreto, no la portada)
}
```

## Etiquetas de música (lista cerrada)
reggaeton, latino, comercial, pop, techno, house, electronica, hiphop, trap, rnb, afro, dancehall, indie, rock, dnb, hardtechno, disco, salsa, flamenco, remember, urban, variado, otros
- "Urbano/Urban" → urban. "Afrohouse/Afrobeats" → afro. "Tech house / melodic / minimal" → house + techno. "EDM / dance / electrónica" → electronica. "Latin / latino / bachata" → latino (o salsa si es baile latino). "80s/90s/2000s/remember" → remember. "Funky / disco / nu-disco" → disco. "Comercial / mainstream / hits / de todo" → comercial. Si la fuente no indica música pero la sala es claramente de un estilo (ver salas), usa el de la sala.

## Zonas (por código postal o barrio)
El directorio `scrape/venues.json` es la referencia definitiva de nombre, dirección, zona y tipo de local: cuando una sala está ahí con `verified: true`, su dirección y zona mandan sobre lo que diga la fuente y sobre las tablas de abajo.
28004 → Malasaña / Chueca · 28012, 28013, 28014 → Centro / Sol · 28005 → La Latina · 28012 (C/ Atocha, Lavapiés) → Atocha · 28045 → Atocha · 28015, 28008 → Argüelles / Moncloa · 28003, 28010 → Chamberí · 28001, 28006, 28009, 28028 → Salamanca · 28007 → Retiro · 28020 → Tetuán / Azca · 28002, 28016, 28036 → Chamartín · 28018, 28038, 28031 → Vallecas · 28026, 28019, 28025 → Usera / Carabanchel · 28034 (Fuencarral / Barrio del Pilar) → Otros norte · 28042 → Barajas · 28023 → Aravaca / Pozuelo · 28970 → Humanes (Fabrik) · 28942, 28943 → Fuenlabrada · 28922 → Alcorcón · 28100 → Alcobendas · 28220 → Majadahonda · Resto → Otros
- Si la sala está en la lista de salas conocidas, manda la zona de la lista (aunque el código postal diga otra cosa). Excepciones conocidas al código postal: **Siroco** (C/ San Dimas 3, 28015) → Malasaña / Chueca; **Green Social Club** (P.º de la Castellana 40, 28046) → Salamanca.
- **Fitz Club** (C/ Princesa 1, 28008) → Argüelles / Moncloa (no Centro / Sol).

## Salas conocidas (nombre canónico → zona, música habitual)
Teatro Kapital → Atocha, comercial/reggaeton/house · Fabrik → Humanes (Fabrik), techno/electronica (o comercial según fiesta) · Teatro Barceló → Malasaña / Chueca, comercial/reggaeton · Shoko → La Latina (C/ Toledo 86), comercial/latino · Opium Madrid → Chamberí, comercial/reggaeton · Joy Eslava → Centro / Sol, comercial/remember · Mondo Disko → Centro / Sol, techno/house · Goya Social Club → Salamanca, house/techno · Panda Club → Chamartín, comercial · Vandido → Salamanca, reggaeton/urban · Independance Club → Atocha, comercial/rock · Oh My Club → Tetuán / Azca, reggaeton/comercial · Sala But → Argüelles / Moncloa, variado · Sala Mon → Argüelles / Moncloa, variado · Sala Copérnico → Argüelles / Moncloa, pop/indie · Siroco (C/ San Dimas 3, 28015 — excepción: aunque el CP es 28015, va en Malasaña) → Malasaña / Chueca, electronica · LAB theCLUB → Chamartín, techno/electronica · Nazca → Tetuán / Azca, reggaeton · Lula Club → Centro / Sol, house/afro · The Bassement → Argüelles / Moncloa, techno/hiphop · Specka → Tetuán / Azca, techno · La Riviera → La Latina (Príncipe Pío), concierto · Sala Caracol → Atocha, concierto · Sala Sol → Centro / Sol, indie/rock · Moby Dick → Chamartín, indie/rock · Medias Puri → Centro / Sol, fiesta · Uñas Chung Lee → Centro / Sol, fiesta · Toni 2 → Centro / Sol, bar · Cadavra → Centro / Sol, techno · Icon Madrid → Salamanca, comercial · Gabana 1800 → Salamanca, comercial · Liberty Supper Club → Chamberí, house/comercial · Rubicón → Salamanca · Istar → Centro / Sol · Graf → Centro / Sol, comercial · Villa Panthera → Chamartín · Teatro Magno → Centro / Sol · Fitz Club (C/ Princesa 1, 28008; alias "Fitz") → Argüelles / Moncloa · Stardust → Centro / Sol · Boite (C/ Tetuán 27, 28013) → Centro / Sol · Blackhaus → Aravaca / Pozuelo · VG Fuenlabrada → Fuenlabrada · Hangar 48 → Otros · Ya'sta Club → Malasaña / Chueca · Lab the Club (Lab Madrid, antiguo Barceló? no: Lab the Club está en C/ Marqués de Vadillo) → Usera / Carabanchel · Sala Wagon → Atocha · Leona Bar → Malasaña / Chueca

### Salas frecuentes que suelen venir sin dirección (verificadas oct-2026)
- Sala Strong (alias "Strong The Club"), C/ Trujillos 7, 28013 → Centro / Sol, house/techno
- Las Ventas (alias "Live Las Ventas"), C/ Alcalá 237, 28028 → Salamanca, concierto/urban
- Sala But (alias "Mondo Disko @ Sala But", "Sala But (Mondo)"), C/ Barceló 11, 28004 → Malasaña / Chueca. Mondo Disko hace algunas noches aquí; su sala habitual es Club Cocó (C/ Alcalá 20, 28014 → Centro / Sol)
- Core, C/ Tetuán 27, 28013 → Centro / Sol, techno/electronica. **Misma dirección que Boite**: CORE es el club que funciona en ese local (abierto en 2026). Si una fuente pone Boite y otra Core para la misma noche y título, es el mismo evento (merge.py los fusiona por dirección)
- Cadillac Solitario, C/ Fermín Caballero 6, 28034 → Otros norte, rock/pop (conciertos)
- Jazzville (Jazzville Café), C/ Jesús Aprendiz 19 (Pacífico) → Retiro, otros (jazz)
- El Despertar Café, C/ Torrecilla del Leal 18, 28012 (Lavapiés) → Atocha, otros (jazz)
- Sala Vesta, C/ Barquillo 29, 28004 → Malasaña / Chueca, pop/indie (conciertos)
- Tiffany's The Club, Av. Doctor Arce 10, 28002 → Chamartín, reggaeton/comercial
- Bonded Club, C/ Miguel Ángel 9, 28010 → Chamberí, comercial
- Cristo Social Club, C/ Juan Bravo 35, 28006 → Salamanca, comercial
- Green Social Club, P.º de la Castellana 40, 28046 → Salamanca (excepción al CP), comercial
- Kube, C/ Poeta Joan Maragall 38, 28020 → Tetuán / Azca, reggaeton/comercial
- Marabú, C/ Ponzano 37, 28003 → Chamberí, comercial/reggaeton
- Manamá, C/ Barcelona 14, 28012 (junto a Sol) → Centro / Sol, reggaeton/comercial
- Todos Santos, C/ Génova 28, 28004 → Malasaña / Chueca, comercial
- Blue Club, C/ Orense 12, 28020 → Tetuán / Azca, reggaeton
- Etnia Club, C/ Orense 14, 28020 → Tetuán / Azca, reggaeton/latino
- Saint Club, C/ Velázquez 64, 28001 → Salamanca, comercial
- Chamán, C/ Poeta Joan Maragall 1, 28020 → Tetuán / Azca, reggaeton/comercial
- Pabblo Club (Pabblo), Pl. Pablo Ruiz Picasso 1, 28020 → Tetuán / Azca. Ojo: también hace cenas-espectáculo (excluidas); solo sesiones de club/afterwork
- Bellaqueolab: es una marca de fiestas de reggaeton, no una sala; se celebra en Global Club, C/ Fundadores 7, 28028 → Salamanca (venue = "Global Club")
- Madrid No Descansa: es una promotora (511 Events), no una sala. Usa la sala real de cada evento (Todos Santos, Rubicón, Gunilla, Salvaje, Las Ventas…); si no aparece, zona "Otros"
- Veneno The Club: no se ha podido verificar la dirección → zona "Otros" salvo que la fuente la dé

## Normas
- Un objeto por sesión/noche. Un evento "recurrente del 29 oct al 31 dic" se convierte en un objeto por cada noche dentro de la ventana en la que la sala realmente abre (usa el calendario de la fuente; si no lo hay, solo jueves–sábado).
- Si la fuente muestra "Desde X €", priceMin = X y priceMax = null.
- Las mesas/reservados VIP NO cuentan para priceMin/priceMax; menciónalos en description.
- Comisiones de gestión: inclúyelas en el precio si la fuente lo muestra sumado; si no, ignóralas.
- Nada de eventos pasados ni fuera de Madrid y alrededores.
- **Qué NO es ocio nocturno (no lo incluyas; merge.py también lo descarta):**
  - Conciertos en teatros/auditorios con butaca: Teatro Albéniz, Teatro Rialto, Ateneo de Madrid, Círculo de Bellas Artes, Nuevo Teatro Alcalá, Teatro Salón Cervantes, auditorios, etc. Sí valen las salas-teatro de fiesta: Teatro Kapital, Teatro Barceló, Joy Eslava (Teatro Eslava) y Teatro Magno.
  - Karaoke, bingo, clases y talleres ("clase de salsa", lessons, workshops), tablaos flamencos, musicales y teatro, cenas-espectáculo, conciertos Candlelight, actividades infantiles, museos.
  - Productos de "saltarse la cola" / reserva sin evento propio, como "Fiesta VIP sin esperas en X" de Fever.
  - Shisha / cachimba.
  - Conciertos tributo ("Tributo a…", "tribute to"), shows drag, monólogos, stand-up y comedia.
  - Conciertos que empiezan antes de las 20:00.
  - Pub crawls / rutas de bares: solo las 3 primeras noches de la ventana.
  - Entradas semanales genéricas ("Jueves en X", "Viernes en X", "X - Entradas") si la sala tiene esa noche un evento con nombre propio: quédate con el evento con nombre.
- No inventes datos: si un campo no aparece, null/[]/"desconocido".
- Enlaces: cada evento debe llevar la URL de su propia página (la que tiene fecha, precio y botón de compra). Un enlace al listado general solo vale si la web no tiene páginas por evento.
- `status`: "disponible" solo si la web de venta lo muestra a la venta; "agotado" solo si lo dice la propia web de venta (no un agregador); si no se ve, "desconocido".
- Fuentes vetadas: no uses madridlux.com (Madrid Lux) ni cites sus datos.
- Nombres de fuente: usa siempre el mismo nombre corto para la misma web (p. ej. "Fever", "Resident Advisor", "Applinkers", "Conciertos.club", "Salir Madrid", "Bynova"), sin variantes.
- Zona: si no sabes la zona, deja "Otros" pero pon la dirección con código postal; merge.py deduce la zona a partir del código postal y de la lista de salas.
- Las fechas sin año: deduce el año (hoy es 2026-10-30; si el mes es anterior al actual, es 2027).
