"""All Madrid Nightlife (allmadridnightlife.com): la agenda completa está en /Data/agenda.json (lista plana de sesiones
Fourvenues con club, evento, dia, hora_inicio/fin, link, edad, p=[min,max], g=% gastos, ago=agotado).
`dia` es la fecha CALENDARIO de inicio: una sesión que empieza a las 00:00 del día 31 es de la noche del 30 (common.night_date).
"""
import re, unicodedata
from scrape.common import get, event, music_tags, clean_text, plain, night_date, in_window, log

NAME = "All Madrid Nightlife"
MIN_EVENTS = 40
URL = "https://www.allmadridnightlife.com/Data/agenda.json"
NOT_NIGHT = re.compile(r"\b(lessons?|clases?|workshops?|taller|karaoke|bingo|tributo|tribute|monologo|stand ?up|comedia|cancelad[oa]s?|cancell?ed)\b")
VENUE_ALIAS = {"manama": "Manamá", "cristo social club": "Cristo Social Club", "nazca": "Nazca", "sala mon": "Sala Mon", "club graf": "Graf",
               "vennus madrid": "Vennus", "chaman boiler club": "Chamán", "chango": "Changó Club", "cats madrid": "Cats", "fitz club": "Fitz Club",
               "bonded": "Bonded Club", "copernico": "Sala Copérnico", "tiffanys the club": "Tiffany's The Club", "mokai beach club": "Mokai Beach Club",
               "banoi": "Banoi", "la riviera": "La Riviera", "green social club": "Green Social Club", "marabu": "Marabú"}
# marcas/promotoras → sala real según el título
BY_TITLE = {"yatengoplan": [(r"pabblo", "Pabblo Club"), (r"green", "Green Social Club")],
            "madrid no descansa": [(r"rubicon", "Rubicón"), (r"las ventas", "Las Ventas"), (r"sala de despecho", "Sala de Despecho")],
            "bellaqueolab": [(r"ponzano", "Marabú"), (r".", "Global Club")],
            "latidolatino": [(r"ponzano", "Marabú")]}

def venue_of(club, title):
    k = plain(club)
    for rx, v in BY_TITLE.get(k, []):
        if re.search(rx, plain(title)): return v
    return VENUE_ALIAS.get(k) or clean_text(club)

def scrape(today, end):
    try: data = get(URL, json_=True)
    except Exception as ex:
        log(NAME, "agenda.json", ex); return []
    out, seen = [], set()
    for e in data:
        if not isinstance(e, dict) or not e.get("link") or not e.get("dia") or not e.get("club"): continue
        start = e.get("hora_inicio") or None
        date = night_date(e["dia"], start)
        if not in_window(date, today, end): continue
        url = e["link"].split("?")[0]
        if url in seen: continue
        seen.add(url)
        title = clean_text(unicodedata.normalize("NFKC", e.get("evento") or "").replace("|", " - ")) or None
        if not title or NOT_NIGHT.search(plain(title)): continue
        venue = venue_of(e["club"], title)
        p = e.get("p") if isinstance(e.get("p"), list) and e.get("p") else None
        pmin = pmax = ptxt = None
        if p:
            pmin = p[0]; pmax = p[1] if len(p) > 1 and p[1] != p[0] else None
            ptxt = f"Entrada {pmin:g}" + (f"–{pmax:g}" if pmax else "") + " €" + (" + gastos" if e.get("g") else "")
        if e.get("ago"): ptxt = ((ptxt + " · ") if ptxt else "") + "Agotado"
        status = "agotado" if e.get("ago") else ("disponible" if p else "desconocido")
        pt = plain(title)
        tardeo = bool(start and "06:00" <= start < "20:00") or "tardeo" in pt or "afterwork" in pt
        out.append(event(title=title, date=date, start=start, end=e.get("hora_fin") or None, venue=venue, type="tardeo" if tardeo else "club",
                         music=music_tags(title), priceMin=pmin, priceMax=pmax, priceText=ptxt, ageMin=e.get("edad") or None, status=status,
                         sources=[{"name": NAME, "url": url}], ticketUrl=url))
    log(NAME, len(out), "eventos")
    return out
