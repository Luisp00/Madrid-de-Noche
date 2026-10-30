"""Gruta 77 (gruta77.com/programacion-eventos-gruta77-madrid/, WordPress + EventON): la página trae un JSON-LD Event por concierto
(nombre, inicio/fin con hora, descripción HTML con "Precio de las entradas: 12€/15€ (+ g.g.)" y enlace de venta). Todo son conciertos."""
import re, html as _html
from scrape.common import get, ld_json, event, in_window, clean_text, plain, night_date, music_tags, log
from scrape.sources._filtros import excluded_title, euro_nums
from scrape.sources._salas import resolve

NAME = "Gruta 77"
MIN_EVENTS = 3
VENUE = resolve("Gruta 77") or ("Gruta 77", "C/ Cuclillo 6, 28019 Madrid", "Usera / Carabanchel")
URL = "https://gruta77.com/programacion-eventos-gruta77-madrid/"

def _dt(s):
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:T(\d{1,2}):(\d{2}))?", s or "")
    if not m: return None, None
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", (f"{int(m.group(4)):02d}:{m.group(5)}" if m.group(4) else None)

def scrape(today, end):
    try: page = get(URL)
    except Exception as ex: log(NAME, "programación", ex); return []
    out, seen = [], set()
    for d in ld_json(page):
        if d.get("@type") != "Event": continue
        title = clean_text(_html.unescape(d.get("name") or ""))
        date, start = _dt(d.get("startDate"))
        _, endt = _dt(d.get("endDate"))
        if not date or not title: continue
        date = night_date(date, start)
        if not in_window(date, today, end) or not start or start < "20:00": continue
        raw = d.get("description") or ""
        text = clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", raw)))
        if excluded_title(title) or re.search(r"homenaje|tributo|tribute", plain(title)): continue
        url = re.sub(r"/var/.*$", "/", d.get("url") or URL)
        if (url, date) in seen: continue
        seen.add((url, date))
        venue = VENUE
        mv = re.search(r"\ben la (sala [^,;(]+)$", title, re.I)
        if mv:
            r = resolve(mv.group(1))
            if r: venue = r
        pm = re.search(r"precio de las entradas:?\s*(.*?)(?:entradas a la venta|bio/|$)", text, re.I)
        ptxt = clean_text(pm.group(1)).rstrip(" .") if pm else ""
        nums = euro_nums(ptxt)
        free = bool(re.search(r"gratis|gratuit|entrada libre", plain(ptxt)))
        pmin = 0 if free else (min(nums) if nums else None)
        pmax = max(nums) if nums and pmin is not None and max(nums) > pmin else None
        tk = next((l for l in re.findall(r"href='([^']+)'|href=\"([^\"]+)\"", raw) for l in l if l and re.search(r"ticket|entradas|dice\.fm|wegow|entradium", l, re.I)), None)
        out.append(event(title=title, date=date, start=start, end=endt, venue=venue[0], address=venue[1], zone=venue[2], type="concierto",
                         music=music_tags(title + " " + text[:200]) or ["rock"], priceMin=pmin, priceMax=pmax,
                         priceText=(ptxt[:120] or None) if (nums or free) else None, free=free, description=(text[:400] or None),
                         sources=[{"name": NAME, "url": url}], ticketUrl=tk or url))
    return out
