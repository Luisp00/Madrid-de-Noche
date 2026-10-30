"""Mondo Disko (mondodisko.es/eventos/, HTML servido; el wp-json no existe): tarjetas con marca (MONDO DISKO / MONDO KRYSTAL…),
line-up en el título, sala ("Club Cocó", "Sala But", "Terraza Jowke"), "Juev. 05 NOV 2026", "23:59h" y clase last-tickets/sold-out.
La ficha /eventos/{id} trae horario completo ("23:59h - 05:30h"), dirección y los tipos de entrada (div.ticket-card: nombre, precio
+ gastos). La sala sale del directorio venues.json (Club Cocó → Sala Cocó)."""
import re, time, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, log
from scrape.sources._salas import resolve

NAME = "Mondo Disko"
MIN_EVENTS = 3
BASE = "https://www.mondodisko.es"
MAX_DETAIL = 30

def _num(s):
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", s or "")
    return float(m.group(1).replace(",", ".")) if m else None

def _detail(url):
    try: html = get(url)
    except Exception as ex: log(NAME, "ficha", url, ex); return {}
    s = soup(html)
    out = {"tickets": [], "hours": None, "addr": None}
    for p in s.select("p"):
        t = clean_text(p.get_text(" "))
        if not out["hours"] and re.match(r"^\d{1,2}:\d{2}h?\s*-\s*\d{1,2}:\d{2}h?$", t): out["hours"] = t
    loc = s.select_one(".fa-location-dot")
    if loc and loc.find_next("p"): out["addr"] = [clean_text(x) for x in loc.find_next("p").get_text("\n").split("\n") if clean_text(x)]
    for c in s.select("#entradas .ticket-card"):
        h = c.select_one("h3")
        ps = [clean_text(p.get_text()) for p in c.select("p")]
        name = clean_text(h.get_text()) if h else ""
        if re.search(r"bono|reservad|mesa", plain(name)) or any("no incluye entrada" in plain(x) for x in ps): continue
        prices = [x for x in ps if re.search(r"\d\s*€", x)]
        if not prices: continue
        base, fee = _num(prices[0]), (_num(prices[1]) if len(prices) > 1 and prices[1].startswith("+") else 0)
        if base is None: continue
        v = round(base + (fee or 0), 2)
        out["tickets"].append((name, int(v) if v == int(v) else v, "agotad" in plain(" ".join(ps)) or "sold-out" in " ".join(c.get("class", []))))
    return out

def scrape(today, end):
    try: html = get(BASE + "/eventos/")
    except Exception as ex: log(NAME, "listado", ex); return []
    out, n = [], 0
    for card in soup(html).select(".grid-evento .evento"):
        a = card.select_one("a.entradas-evento[href], a[href^='/eventos/']")
        if not a: continue
        url = BASE + a["href"] if a["href"].startswith("/") else a["href"]
        brand = clean_text((card.select_one(".tag-evento") or card).get_text(" ")) if card.select_one(".tag-evento") else ""
        art = clean_text((card.select_one(".artistas") or card).get_text(" "))
        spans = [clean_text(x.get_text()) for x in card.select(".fecha-evento span")]
        if len(spans) < 2: continue
        sala, dtxt = spans[0], spans[1]
        m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", plain(dtxt))
        if not m or m.group(2) not in MONTHS: continue
        try: date = datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
        except ValueError: continue
        tm = re.search(r"(\d{1,2}):(\d{2})", spans[2] if len(spans) > 2 else "")
        start = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None
        date = night_date(date, start)
        if not in_window(date, today, end): continue
        det = {}
        if n < MAX_DETAIL:
            n += 1; det = _detail(url); time.sleep(0.4)
        endt = None
        if det.get("hours"):
            hs = re.findall(r"(\d{1,2}):(\d{2})", det["hours"])
            if len(hs) > 1: endt = f"{int(hs[1][0]):02d}:{hs[1][1]}"
        r = resolve(sala)
        if r: venue, address, zone = r
        else:
            venue, zone = sala, "Otros"
            ad = (det.get("addr") or [])[1:]
            address = ", ".join(ad) or None
        tks = det.get("tickets") or []
        avail = [t for t in tks if not t[2]] or tks
        nums = [t[1] for t in avail]
        pmin = min(nums) if nums else None
        pmax = max(nums) if nums and max(nums) > pmin else None
        ptxt = " · ".join(f"{t[0]} {t[1]} €" for t in avail)[:120] or None
        cls = " ".join((card.select_one(".flyer-evento") or card).get("class", []))
        status = "agotado" if "sold" in cls or (tks and all(t[2] for t in tks)) else ("ultimas" if "last-tickets" in cls else ("disponible" if tks else "desconocido"))
        title_parts = re.split(r"\s*:\s*", art, 1)
        lineup_txt = title_parts[1] if len(title_parts) > 1 and len(title_parts[0]) < 60 else art
        lineup = [clean_text(x) for x in re.split(r"\s*/\s*|\s+B2B\s+", re.sub(r"^(EXTENDED|AFTERPARTY)\s*(?:X [^-]+)?-?\s*", "", lineup_txt, flags=re.I)) if clean_text(x)]
        bbase, _, bextra = brand.partition(" - ")
        bbase = bbase.strip() or "MONDO DISKO"
        title = art if plain(bbase) in plain(art) else f"{bbase.title()}: {art}"
        typ = "tardeo" if start and "12:00" <= start < "21:00" else ("after" if re.search(r"\bafter(?!party)", plain(art)) else "club")
        out.append(event(title=title[:160], date=date, start=start, end=endt, venue=venue, address=address, zone=zone, type=typ,
                         music=music_tags(art) or ["techno", "house"], priceMin=pmin, priceMax=pmax, priceText=ptxt, free=(pmin == 0),
                         lineup=lineup[:10], description=(f"{bbase.title()} en {sala}." + (f" {bextra.strip().capitalize()}." if bextra.strip() else "")), status=status,
                         sources=[{"name": NAME, "url": url}], ticketUrl=url))
    return out
