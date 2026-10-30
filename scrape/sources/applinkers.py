"""Applinkers (applinkers.com): agenda de Madrid servida por el servidor; replica Fourvenues (listas gratis).

/entradas/madrid/agenda/ lista ~120 sesiones con hora, edad, música, "lista gratis hasta", precio-desde y AGOTADO.
Las páginas de sala (/entradas/madrid/<sala>/) aportan dirección y completan fechas que falten en la agenda.
Applinkers no tiene página propia por evento: cada tarjeta enlaza a la ficha de compra en Fourvenues (site.fourvenues.com),
que se usa como source y ticketUrl.
"""
import re, time
from scrape.common import get, soup, event, parse_date, parse_time, parse_price, in_window, music_tags, clean_text, plain, log

NAME = "Applinkers"
MIN_EVENTS = 40
BASE = "https://applinkers.com"
LISTS = ["/entradas/madrid/agenda/", "/entradas/madrid/hoy/", "/entradas/madrid/listas-gratis/"] + \
        [f"/entradas/madrid/{d}/" for d in ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")]
NOT_NIGHT = re.compile(r"\b(lessons?|clases?|workshops?|taller|karaoke|bingo|tributo|tribute|monologo|stand ?up|comedia)\b", re.I)
VENUE_ALIAS = {"fitz": "Fitz Club", "mon": "Sala Mon", "copernico": "Sala Copérnico", "sala copernico": "Sala Copérnico", "sala la riviera": "La Riviera",
               "chaman": "Chamán", "chango": "Changó Club", "chango club": "Changó Club", "joy eslava": "Joy Eslava", "saint club": "Saint Club",
               "cristo social club": "Cristo Social Club", "vandido": "Vandido"}

def canon_venue(name):
    name = clean_text(name)
    k = plain(name)
    if k in VENUE_ALIAS: return VENUE_ALIAS[k]
    return name.title() if name.isupper() and len(name) > 3 else name

def url_date(url):
    m = re.search(r"-(\d{2})-(\d{2})-(\d{4})-[A-Za-z0-9]{3,6}$", url)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None

def card_fields(c, today):
    a = c.select_one("a.ent-ev-tap, a.ent-card-link")
    if not a or not a.get("href", "").startswith("http"): return None
    url = a["href"].split("?")[0]
    title = clean_text((c.select_one(".ent-ev-nombre, .ent-card-title") or a).get_text()) or clean_text(a.get("aria-label"))
    when = clean_text((c.select_one(".ent-ev-fecha, .ent-card-sub") or c).get_text())
    date = url_date(url) or parse_date(when, today)
    tm = re.search(r"(\d{1,2}:\d{2})\s*$", when)
    start = parse_time(tm.group(1)) if tm else None
    club = c.select_one(".ent-ev-club")
    d = {"url": url, "title": title, "date": date, "start": start, "venue": clean_text(club.get_text()) if club else None,
         "free_txt": None, "age": None, "price_txt": None, "agotado": False, "music": []}
    for b in c.select(".ent-ev-badge"):
        cl, t = b.get("class", []), clean_text(b.get_text())
        if "is-gratis" in cl: d["free_txt"] = t
        elif "is-edad" in cl:
            m = re.search(r"\d+", t); d["age"] = int(m.group()) if m else None
        elif "is-precio" in cl: d["price_txt"] = t
        elif "is-agotado" in cl: d["agotado"] = True
        else: d["music"].append(t)
    pr = c.select_one(".ent-precio")
    if pr:
        t = clean_text(pr.get_text())
        if re.search(r"agotado", t, re.I): d["agotado"] = True
        else: d["price_txt"] = t
    return d

def scrape(today, end):
    cards, clubs = {}, {}
    for path in LISTS:
        try: html = get(BASE + path)
        except Exception as ex: log(NAME, "listado", path, ex); continue
        s = soup(html)
        for c in s.select(".ent-ev-card"):
            d = card_fields(c, today)
            if d and d["url"] not in cards: cards[d["url"]] = d
        if path.endswith("/agenda/") or path.endswith("/hoy/"):
            for slug in re.findall(r'href="/entradas/madrid/([a-z0-9-]+)/"', html):
                if slug not in ("agenda", "hoy", "mapa", "listas-gratis", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"):
                    clubs.setdefault(slug, None)
    # páginas de sala: dirección y fechas que falten
    info = {}
    for slug in list(clubs):
        time.sleep(0.4)
        try: html = get(f"{BASE}/entradas/madrid/{slug}/")
        except Exception as ex: log(NAME, "sala", slug, ex); continue
        s = soup(html)
        h1 = s.select_one("h1"); ad = s.select_one(".ent-dir")
        name = clean_text(h1.get_text()) if h1 else None
        addr = clean_text(ad.get_text()) if ad else None
        if addr: addr = re.sub(r",\s*Espa[ñn]a$", "", addr); addr = re.sub(r"\s*\(Madrid\)", "", addr)
        info[slug] = (name, addr)
        for c in s.select(".ent-card"):
            d = card_fields(c, today)
            if d and d["url"] not in cards and d["date"]:
                d["venue"] = name
                cards[d["url"]] = d
    by_name = {plain(n): a for n, a in info.values() if n}
    out = []
    for d in cards.values():
        if not d["date"] or not in_window(d["date"], today, end) or not d["venue"] or NOT_NIGHT.search(plain(d["title"])): continue
        addr = by_name.get(plain(d["venue"]))
        free = d["free_txt"]
        pmin, pmax, _ = parse_price(d["price_txt"].replace("€", " eur")) if d["price_txt"] else (None, None, False)
        parts = []
        if free: parts.append(free)
        if d["price_txt"]: parts.append(re.sub(r"^Desde", "desde", d["price_txt"]))
        if d["agotado"]: parts.append("Agotado")
        if free: pmin = 0
        music = music_tags(" ".join(m.replace("-", " ") for m in d["music"]))
        if "hardtechno" in music and "techno" in music: music.remove("techno")
        if not d["music"]: music = music_tags(d["title"])
        tardeo = "tardeo" in plain(d["title"]) or (d["start"] and "06:00" <= d["start"] < "20:00")
        status = "agotado" if d["agotado"] else ("disponible" if d["price_txt"] or free else "desconocido")
        out.append(event(title=d["title"], date=d["date"], start=d["start"], venue=canon_venue(d["venue"]), address=addr,
                         type="tardeo" if tardeo else "club", music=music, priceMin=pmin, priceMax=pmax if pmax != pmin else None,
                         priceText=" · ".join(parts)[:120] or None, free=bool(free), ageMin=d["age"], status=status,
                         sources=[{"name": NAME, "url": d["url"]}], ticketUrl=d["url"]))
    log(NAME, len(out), "eventos")
    return out
