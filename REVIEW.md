# Revisión: Madrid de Noche (30 oct 2026, segunda pasada)

> **Actualización de las 09:45.** Tras lo descrito abajo, la extracción pasó de agentes a **parsers Python** (25 fuentes, `scrape/`), con agentes solo de respaldo; se añadieron fuentes nuevas (WHAN, Xceed, feeds de salas) a partir de `FUENTES.md`; se quitó Madrid Lux; la tarea diaria se sustituyó por una que despierta una **sesión de ejecución** con acceso al repo (`README.md` tiene los ids). Con los parsers la BD pasó de 981 a 1663 eventos y el coste diario deja de depender de leer webs con modelos.

> Actualización de las 08:30: tras esta revisión se cambió además el **almacenamiento**: en vez de un documento por evento (que obligaba a conocer ~1000 versiones al día y a subir hasta 20 lotes), los eventos van en 4–8 documentos `chunk-NN` que se reescriben enteros. Desaparecen `versions.txt` de 1000 líneas, los lotes y `meta/seen`; la tarea hace 4–8 escrituras. Los 981 eventos ya están migrados. Y la misma app funciona como **web estática** (rama `gh-pages`, pendiente de activar GitHub Pages) para compartirla sin cuenta de Claude; el runbook incluye un paso opcional que la actualiza mediante una sesión hija con acceso al repo. Los puntos 1–4 de "Actualización diaria" quedan así sustituidos por este diseño más simple.

Revisión completa del proyecto antes de la primera ejecución de la tarea diaria (hoy 22:00). Se contrastó el código local con el artifact publicado, la BD (981 documentos descargados y analizados) y la tarea programada, y se ejecutó una sesión programada de prueba para ver qué herramientas tiene realmente la tarea.

## Lo que estaba roto y se ha arreglado

**Actualización diaria (lo urgente)**
1. El prompt de la tarea y el runbook hablaban de `write_db` con ops `op/path/data/ifVersion`. La herramienta real de las sesiones programadas es `ArtifactData`, cuyo `batch` usa `{op, collection, doc_id, data|file_path, if_version}`. `merge.py` genera ahora ese formato (`out/batchf_NN.json` con `file_path`, verificado que funciona, y `out/batch_NN.json` en línea como fallback).
2. La BD se leía entera al contexto (~200 000 tokens). Ahora se descarga con `query … out_dir` (archivos en disco). Las versiones de los documentos solo aparecen en el texto del resultado, así que el runbook pide volcarlas a `db/versions.txt`; `merge.py` las interpreta pegadas tal cual y se niega a generar lotes si faltan.
3. Cada día se habrían reescrito los ~1000 documentos. Ahora los eventos sin cambios no generan escritura (ayer habrían sido 613 de 886); la "última vez visto" va en `meta/seen`, un solo documento.
4. Los cancelados nunca se borraban. Ahora se borra un evento futuro que lleva 3 extracciones sin aparecer, siempre que alguna de sus fuentes sí se haya extraído ese día (o 7 días sin aparecer en cualquier caso). Los duplicados antiguos del mismo evento se borran al detectarse.
5. Espera a los agentes: 25 → 60 min. Los agentes en background avisan al terminar, así que no hace falta sondear.
6. Campos estables (dirección, dress code, edad, descripción, line-up, música, hora de cierre) se conservan del documento existente si la extracción de hoy no los trae.
7. Zona: 156 eventos estaban en "Otros". `merge.py` deduce ahora la zona por la tabla de salas o por el código postal de la dirección.
8. `meta/status` incluye `running`/`runStartedAt` (la app muestra "actualizando ahora…"), `run` con los contadores del día y `failedSources`.

**App**
1. "Finde" devolvía 0 (`Math.max` sobre cadenas).
2. Dentro de la noche, lo de las 00:00–05:59 ordena ahora después de lo de las 22:00.
3. Búsqueda insensible a tildes y por varias palabras; también busca por nombre de fuente.
4. El precio ya no desborda la tarjeta en móvil (columna de título con `min-width:0`, precio con ancho máximo y texto recortado a 2 líneas).
5. Las cabeceras de día se pegan justo debajo de la cabecera real (su altura se mide con `ResizeObserver`).
6. Cerrar los filtros tocando fuera o con Escape aplica el filtro.
7. El botón principal de la ficha usa `ticketUrl` (el enlace más barato); el resto de fuentes van detrás. Nuevo botón "Cómo llegar" (Google Maps).
8. Accesibilidad: tarjetas abribles con teclado (Enter/espacio), foco visible, el foco entra en los paneles y vuelve al cerrar, `aria-pressed`/`role=switch`, grises con contraste ≥ 4,5:1, `prefers-reduced-motion`.
9. "tardeo" traducido; el filtro de edad ahora significa "donde me dejan entrar" (Tengo 18–19 / 20 / 21–24 / 25+).
10. Favoritos: además de `localStorage` se guardan en el documento privado `data/users/<id>/prefs` de la BD (sobreviven a borrar el navegador y se sincronizan entre dispositivos).
11. Botón ⟳ "actualizar ahora", solo visible para el propietario: lanza la tarea programada mediante la capacidad `mcp` (conector "Claude Code Remote", `fire_trigger`) tras una confirmación en pantalla. Mientras `meta/status.running` sea true (máx. 3 h) el botón gira y la cabecera lo indica.
12. La página cumple ahora el contrato del publicador (sin `<html>/<head>`, `color-scheme: dark`, cabecera pegajosa respetando el área segura, gutter lateral de 16 px, aviso cuando falla la carga de algún tramo).

**Fusión / especificación**
- Exclusiones nuevas: tributos, shows drag, monólogos/stand-up (eran los casos que QA había borrado a mano y que la fusión volvía a meter).
- Regla "un título contiene al otro" limitada a títulos de ≥2 palabras o ≥12 caracteres (evitaba que una variante corta absorbiera otra sesión).
- `SPEC.md`: exige la página propia del evento como URL, define cuándo poner "disponible"/"agotado", pide nombres de fuente estables y dirección con código postal cuando no se sabe la zona.

## Comprobaciones hechas
- `node test.js` (15 comprobaciones) en verde con datos de ejemplo y con los 981 eventos reales, a 390 px y 1200 px, sin errores de consola ni scroll horizontal.
- `merge.py` ejecutado contra el volcado real de la BD con las extracciones de la carga inicial: 888 únicos, 7 nuevos, 256 actualizados, 609 sin cambios (sin escritura), 4 duplicados antiguos a borrar, 6 lotes. No se subió nada: la extracción es la de ayer y revertiría las correcciones de QA.
- Sesión programada de prueba (una sola vez, ya borrada): herramientas disponibles, `batch` con `file_path` OK, `query` con `out_dir` OK, `python3` OK.
- Artifact republicado (versión 10) con `db` (2 reglas), `user` y `mcp`; lectura con nivel "view" devuelve eventos; los 4 archivos publicados coinciden con los del repo.

## Lo que queda (ver README "Pendiente")
- La primera ejecución real decidirá si el paso de `versions.txt` (≈1000 líneas que el modelo tiene que pegar) es fiable. Si no lo es, la alternativa es leer la BD en páginas de 100 sin `out_dir` (más tokens) o pedir a la herramienta que guarde las versiones.
- Cobertura de las fuentes nunca ejecutadas y de las 12 salas sin eventos.
- Enlaces a página propia, precios y estados: medir después de la primera ejecución.
- El entorno cloud "Madrid de Noche" tiene la red cerrada: no sirve para extraer desde Claude Code hasta que se amplíe el acceso.
