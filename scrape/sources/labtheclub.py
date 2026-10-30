"""LAB theCLUB (labtheclub.com/agenda/, WordPress servido): tarjetas article.event-featured con fecha (también en el slug
"…-30102026/"), título, "Desde las 23:55" y el botón "Entradas" (Resident Advisor u otra ticketera, que no se visita).
La clase lab_club-* indica la sala del complejo (BeRenatta, Elite Club, LAB theClub, Vipper Club): todas en el ático de Chamartín.
Las fichas propias no añaden precio ni descripción, así que no se visitan. Precio: la agenda no lo publica (null)."""
import re, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, parse_date, night_date, music_tags, log

NAME = "LAB theCLUB"
MIN_EVENTS = 2
VENUE = "LAB theCLUB"
ADDRESS = "Estación de Chamartín-Clara Campoamor, planta alta (C/ Agustín de Foxá s/n), 28036 Madrid"
ZONE = "Chamartín"
URL = "https://www.labtheclub.com/agenda/"

def scrape(today, end):
    try: html = get(URL)
    except Exception as ex: log(NAME, "agenda", ex); return []
    s = soup(html)
    clubs = {a.get("data-filter"): clean_text(a.get_text()) for a in s.select("a.lab_club__selector-item[data-filter]")}
    out = []
    for art in s.select("article.event-featured, article.type-event"):
        a = art.select_one("a.entry-event__link[href]")
        h = art.select_one(".entry-event__title")
        if not a or not h: continue
        url, title = a["href"].strip(), clean_text(h.get_text(" "))
        m = re.search(r"-(\d{2})(\d{2})(\d{4})/?$", url)
        date = None
        if m:
            try: date = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
            except ValueError: date = None
        if not date:
            dt = art.select_one(".entry-event__date")
            date = parse_date(dt.get_text(" ") if dt else "", today)
        sub = art.select_one(".entry-event__subtitle")
        mt = re.search(r"(\d{1,2})[:.](\d{2})", sub.get_text() if sub else "")
        start = f"{int(mt.group(1)):02d}:{mt.group(2)}" if mt else None
        date = night_date(date, start)
        if not in_window(date, today, end): continue
        club = next((clubs.get(c) for c in art.get("class", []) if c in clubs), None)
        ticket = None
        for b in art.select("a.entry-event__btn[href]"):
            if re.search(r"entradas|tickets", plain(b.get_text())): ticket = b["href"].strip(); break
        typ = "tardeo" if start and "14:00" <= start < "21:00" else "club"
        out.append(event(title=title, date=date, start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type=typ,
                         music=music_tags(title) or ["techno", "electronica"],
                         description=(f"Sala {club} del complejo LAB." if club and club != "LAB theClub" else None),
                         sources=[{"name": NAME, "url": url}], ticketUrl=ticket if ticket and ticket.startswith("http") else url))
    return out
