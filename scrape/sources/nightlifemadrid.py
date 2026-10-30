"""Nightlife Madrid (nightlifemadrid.com): fiestas SEMANALES. /fiestas-madrid/ lista las fiestas con horario y enlace de entradas
(tickets.nightlifemadrid.com/<slug>/, SPA con JavaScript: sin precios en HTML); /parties-madrid/<día>/ dice en qué días se celebra cada una.
Se generan las fechas de la ventana que corresponden a esos días. Pub crawls (Meet & Party, Fucking Monday): solo las 3 primeras noches (SPEC).
"""
import re, time, datetime
from scrape.common import get, soup, event, music_tags, clean_text, plain, log

NAME = "Nightlife Madrid"
MIN_EVENTS = 5
BASE = "https://nightlifemadrid.com"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ABBR = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
# slug de entradas -> (sala, dirección, música por defecto de la sala, tipo)
VENUES = {"icon": ("Icon Madrid", None, ["comercial", "house", "reggaeton"], "club"),
          "teatro-kapital": ("Teatro Kapital", "C/ Atocha 125, 28012 Madrid", ["comercial", "reggaeton", "house"], "club"),
          "calle-365": ("Calle 365", None, [], "bar"), "casa-suecia": ("Casa Suecia", None, [], "tardeo"),
          "toy-room": ("Toy Room", None, [], "club"), "utopia": ("Utopia", None, [], "club"), "waves": ("Waves", None, [], "tardeo"),
          "fucking-monday": ("Calle 365", None, ["comercial", "reggaeton"], "fiesta"), "meet--party": ("Manamá", "C/ Barcelona 14, 28012 Madrid", ["comercial"], "fiesta")}
CRAWL = {"fucking-monday", "meet--party"}
SKIP = re.compile(r"language|speak|karaoke|clase|lesson|workshop")

def rng(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})", s or "")
    return (f"{int(m.group(1)):02d}:{m.group(2)}", f"{int(m.group(3)):02d}:{m.group(4)}") if m else (None, None)

def cards(html):
    out = []
    for c in soup(html).select(".et_pb_promo"):
        h = c.select_one("h3"); a = c.select_one("a[href]")
        if not h or not a: continue
        title = clean_text(h.get_text())
        txt = clean_text(c.get_text(" "))
        m = re.search(r"/(?:es|en)/([\w-]+)/?$", a["href"].split("?")[0])
        out.append({"title": title, "time": rng(txt), "slug": m.group(1) if m else None, "url": a["href"].split("?")[0]})
    return out

def hint_days(title):
    """'(Jue - Dom)', '(Vie y Sáb)', '(Mie, Vie y Sáb)' -> {3,4,5,6} ... o None."""
    m = re.search(r"\(([^)]*)\)", title)
    if not m: return None
    p = plain(m.group(1)); toks = re.findall(r"\b(lun|mar|mie|jue|vie|sab|dom)", p)
    if not toks: return None
    if re.search(r"\b(lun|mar|mie|jue|vie|sab|dom)\w*\s*-\s*(lun|mar|mie|jue|vie|sab|dom)", p) and len(toks) == 2:
        a, b = ABBR[toks[0]], ABBR[toks[1]]
        return set(range(a, b + 1))
    return {ABBR[t] for t in toks}

def scrape(today, end):
    t0, t1 = datetime.date.fromisoformat(today), datetime.date.fromisoformat(end)
    hints = {}
    try:
        for c in cards(get(BASE + "/fiestas-madrid/")):
            hints[(c["slug"], plain(re.sub(r"\(.*?\)|\ben\b.*$", "", c["title"])))] = hint_days(c["title"])
    except Exception as ex: log(NAME, "fiestas-madrid", ex)
    weekly = {}
    for wd, day in enumerate(DAYS):
        try: html = get(f"{BASE}/parties-madrid/{day}/")
        except Exception as ex: log(NAME, "día", day, ex); continue
        for c in cards(html):
            if not c["slug"] or c["slug"] not in VENUES or SKIP.search(plain(c["title"])): continue
            title = re.sub(r"\s+en\s+(?:ICON|Calle 365|Casa Suecia)$", "", c["title"])
            key = (c["slug"], plain(title), c["time"])
            h = hints.get((c["slug"], plain(re.sub(r"\(.*?\)", "", title))))
            if h is not None and wd not in h: continue
            weekly.setdefault(key, {"c": c, "title": title, "days": set()})["days"].add(wd)
    out = []
    for (slug, _, _), w in weekly.items():
        venue, addr, music, typ = VENUES[slug]
        start, endt = w["c"]["time"]
        d = t0
        while d <= t1:
            if d.weekday() in w["days"] and not (slug in CRAWL and (d - t0).days > 2):
                title = w["title"]
                if plain(title) in ("teatro kapital",): title = f"Teatro Kapital {['lunes','martes','miércoles','jueves','viernes','sábado','domingo'][d.weekday()]}"
                tard = bool(start and "06:00" <= start < "20:00")
                out.append(event(title=title, date=d.isoformat(), start=start, end=endt, venue=venue, address=addr, type="tardeo" if tard else typ,
                                 music=(['latino', 'salsa'] if 'meet & dance' in title.lower() else music_tags(title) or music), status="desconocido",
                                 description="Pub crawl semanal de Nightlife Madrid." if slug in CRAWL else "Fiesta semanal de Nightlife Madrid; precio y reserva en la web de entradas.",
                                 sources=[{"name": NAME, "url": w["c"]["url"]}], ticketUrl=w["c"]["url"]))
            d += datetime.timedelta(days=1)
    log(NAME, len(out), "eventos")
    return out
