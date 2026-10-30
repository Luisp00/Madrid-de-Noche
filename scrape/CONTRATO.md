# Contrato de los parsers (scrape/sources/<fuente>.py)

Cada módulo expone `NAME` (nombre corto de la fuente, el mismo que usa la app), `MIN_EVENTS` (mínimo razonable de
eventos en una ventana de 14 días; por debajo la fuente se da por fallida y la sesión lanza un agente de respaldo) y
`scrape(today, end) -> list[dict]` con eventos en el esquema de SPEC.md (usa `common.event(**campos)`).

Reglas:
- Red: `common.get(url)` (requests, proxy del entorno, reintentos, caché 1 h en run/cache) para HTML/JSON servido por el
  servidor; `common.browser(url, raw=True)` (Chromium headless) solo cuando la página necesita JavaScript o bloquea a
  requests. Nunca más de ~60 páginas de detalle por fuente y `time.sleep(0.4)` entre ellas. Nada de curl.
- No modifiques `scrape/common.py` ni `scrape.py`; si te falta un helper, defínelo en tu módulo.
- `date` es la noche en que empieza el evento (madrugada de 00:00–05:59 → noche anterior: `common.night_date`).
- `venue` debe ser la sala real (nunca "Madrid"); `sources[0].url` y `ticketUrl` la página propia del evento.
- Precio: `priceMin` = entrada general más barata (0 si hay lista/entrada gratis), `priceMax` = la más cara sin mesas VIP,
  `priceText` resumen ≤120 caracteres; `free` si hay alguna forma gratis. Si la web no publica precio, null.
- Excluye lo que SPEC.md dice que no es ocio nocturno (teatros con butaca, karaoke, tributos, monólogos, clases,
  "VIP sin esperas", conciertos antes de las 20:00…). Fuera de la ventana [today, end] no se devuelve nada.
- Nada inventado: si un dato no está, null / [] / "desconocido".
- Prueba: `cd /home/user/Madrid-de-Noche && python3 scrape.py --only <modulo> --out run/scrape_test --today 2026-10-30`
  y revisa `run/scrape_test/<modulo>.json`: fechas dentro de la ventana, salas reales, horas y precios cuando la web los da.
