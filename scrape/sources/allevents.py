"""AllEvents (allevents.in/madrid/parties): tarjetas SSR de varias páginas (?page=N) + API de listado (/api/categorization/web/v1/list)
con precio y dirección. Fuente ruidosa (mezcla meetups, talleres, conciertos de estadio): se filtra por heurística de ocio nocturno."""
import re, time, html as _html, datetime
from scrape.common import get, session, soup, event, parse_date, in_window, music_tags, clean_text, night_date, plain, log

NAME = "AllEvents"
MIN_EVENTS = 5
BASE = "https://allevents.in"
PAGES = [BASE + "/madrid/parties"] + [f"{BASE}/madrid/parties?page={p}" for p in range(2, 7)] + [BASE + "/madrid/halloween-parties", BASE + "/madrid/clubs"]
KW = "!(\"third party\"|\"any party\"|\"both party\") party, disco, nightlife, \"pub night\", MASQUERADE,\"bar night\",\"pub crawl\",\"bar crawl\""
MAX_DETAIL = 40

NEG = re.compile(r"workshop|taller|clase\b|clases\b|masterclass|comedy|stand ?up|monolog|mon[oó]log|bingo|brunch|cena\b|dinner|lectura|reading|libro|tertulia|networking|language|idiomas|intercambio|meetup|swap|singles|citas|infantil|kids|cumplea[nñ]os|pasaje|terror room|asesinato|misterio|murder in|globos|flamenco|candlelight|tributo|tribute|boxing|nfl|tailgate|pop-up|crucero|awards|gala\b|beauty|esports|jazz room|ca[nñ]a|vermut|pinta|lunch|terapia|summit|afterwork|quedada|escape|karaoke|navidad|comedia|obra\b|tarot|teatro(?! kapital)|musical\b", re.I)
NEG_VENUE = re.compile(r"bistrot|bistro|restaurante|movistar arena|palacio vistalegre|bernab|metropolitano|wizink|teatro(?! kapital| barcel| magno| eslava)|auditorio|hostel|hotel|museo|librer|casa de|centro (cultural|de)|spa\b|lush|aeropuerto|bodas|novotel|residencia|galer[ií]a|estatua|downtown|puerta del sol|apple store|vodafone|in front of", re.I)
POS_VENUE = re.compile(r"club|disco|sala |kapital|siroco|s[oó]tano|enbabia|pub\b|\bbar\b|lounge|gruta|nazca|riviera|las ventas|wagon|juglar|tempo|ya.sta|independance|leona|planet|commo|espit|ella sky|forajido|blackbird|cabaret|barcel|magno|eslava|joy", re.I)
POS_TITLE = re.compile(r"party|fiesta|session|sesi[oó]n|noche|tardeo|\bdj\b|halloween|after|perreo|reggaet|techno|house|ruta del bacalao|pogo|rock|live|concierto|m[uú]sica", re.I)
CRAWL = re.compile(r"pub ?crawl|bar ?crawl", re.I)
VENUE_ALIAS = [(r"las ventas", "Las Ventas"), (r"riviera", "La Riviera"), (r"hood dogs by planet club", "Planet Club"), (r"espit chupitos", "Espit Chupitos Sol"),
               (r"^independance", "Independance Club"), (r"^teatro kapital", "Teatro Kapital"), (r"^sala nazca|^nazca", "Nazca"), (r"^el s[oó]tano$", "El Sotano")]
ADDR_VENUE = {"san dimas, 3": "Siroco"}

def _time(txt):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])", txt or "")
    if not m: return None
    h, mi, ap = int(m.group(1)), m.group(2), m.group(3).lower()
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    return f"{h:02d}:{mi}"

def _date(txt, today):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})(?:,?\s*(\d{4}))?", txt or "")
    return parse_date(m.group(0), today) if m else None

def _price(txt):
    t = clean_text(txt or "")
    if not t: return None, None, None
    if re.fullmatch(r"free", t, re.I): return 0, None, "Gratis"
    m = re.match(r"EUR\s*([\d.,]+)(?:\s*to\s*([\d.,]+))?", t)
    if not m: return None, None, None
    lo = float(m.group(1).replace(",", ".")); hi = float(m.group(2).replace(",", ".")) if m.group(2) else None
    lo = int(lo) if lo == int(lo) else lo
    if hi: hi = int(hi) if hi == int(hi) else hi
    if lo == 0: return 0, (hi or None), f"Gratis – {hi:g} €" if hi else "Gratis"
    if hi and hi > lo and hi <= 3 * lo: return lo, hi, f"{lo:g} € – {hi:g} €"
    return lo, None, f"{lo:g} €" if not hi or hi == lo else f"Desde {lo:g} €"

def _api_items():
    out = []
    try:
        s = session(); s.get(BASE + "/madrid/parties", timeout=30)
    except Exception as ex:
        log(NAME, "api warm-up", ex); return out
    for page in range(1, 9):
        payload = {"venue": 0, "page": page, "rows": 15, "tag_type": "", "sdate": 0, "edate": 0, "city": "madrid", "keywords": KW, "category": ["parties"],
                   "formats": 0, "sort_by_score_only": True}
        d = None
        for _ in range(3):
            try:
                r = s.post(BASE + "/api/categorization/web/v1/list", json=payload, headers={"Origin": BASE, "Referer": BASE + "/madrid/parties"}, timeout=30)
                d = r.json(); break
            except Exception: time.sleep(1)
        items = (d or {}).get("item") or []
        out += items
        if len(items) < 15: break
    return out

def _split_location(loc):
    """('Forajido Bar & Disco, Costanilla de Capuchinos, 1, Madrid, 28004, Madrid, ES') -> (venue, address)."""
    loc = clean_text(_html.unescape(loc or ""))
    low = plain(loc)
    for k, v in ADDR_VENUE.items():
        if low.startswith("calle " + k) or low.startswith("c. " + k) or ("calle " + k) in low[:30]: return v, loc
    if re.match(r"^(calle|c\.|c/|p\.|avda|avenida|paseo|plaza)", low) or re.match(r"^\d", low): return None, loc
    if "," in loc:
        v, rest = loc.split(",", 1)
        if re.search(r"\d", rest) and len(v) <= 45: return clean_text(v), clean_text(rest)
    return loc, None

def scrape(today, end):
    cands = {}
    for u in PAGES:
        try: html = get(u)
        except Exception as ex: log(NAME, "listado", u, ex); continue
        for li in soup(html).select("li.event-card[data-eid]"):
            eid = li["data-eid"]
            if eid in cands: continue
            g = lambda sel: clean_text(li.select_one(sel).get_text(" ")) if li.select_one(sel) else ""
            cands[eid] = dict(id=eid, title=_html.unescape(g("h3") or li.get("data-name", "")), when=g(".date"), loc=g(".location"), price=g(".price-container"),
                              url=(li.get("data-link") or "").split("?")[0], api=None)
    for it in _api_items():
        eid = it.get("event_id")
        if not eid: continue
        c = cands.setdefault(eid, dict(id=eid, title=_html.unescape(it.get("eventname") or ""), when=it.get("app_display_time") or "", loc=_html.unescape(it.get("location") or ""),
                                       price=it.get("display_price_label") or "", url=(it.get("event_url") or "").split("?")[0], api=None))
        c["api"] = it
        if not c["price"]: c["price"] = it.get("display_price_label") or ""
    # filtro heurístico
    sel = []
    for c in cands.values():
        date = _date(c["when"], today); start = _time(c["when"])
        if not date or not start or not c["url"]: continue
        d = night_date(date, start)
        if not in_window(d, today, end): continue
        title = re.sub(r"^Entradas\s+(?:para\s+)?(?:el\s+)?", "", c["title"], flags=re.I).strip()
        title = re.sub(r"\s+(Madrid\s+)?Tickets$", "", title, flags=re.I).strip()
        tags = " ".join((c["api"] or {}).get("tags") or [])
        venue, addr = _split_location(c["loc"])
        if venue:
            m = re.match(r"^(.{3,40}?)\s+((?:Calle|C/|Avenida|Paseo)\s.+)$", venue)
            if m: venue, addr = m.group(1), addr or m.group(2)
            venue = re.sub(r"\s+Madrid$", "", re.sub(r"^Eventos\s+", "", venue)).strip()
            if venue.isupper() and len(venue) > 4: venue = venue.title()
        if (c["api"] or {}).get("venue") and not addr:
            addr = clean_text((c["api"]["venue"] or {}).get("street") or "") or None
        if not venue or NEG.search(title) or re.search(r"workshop|meetup|comedy|networking", tags, re.I) or NEG_VENUE.search(venue): continue
        is_crawl = bool(CRAWL.search(title))
        if is_crawl and d > (datetime.date.fromisoformat(today) + datetime.timedelta(days=2)).isoformat(): continue
        if not (POS_VENUE.search(venue) or POS_TITLE.search(title) or is_crawl): continue
        if not (POS_VENUE.search(venue) or re.search(r"party|fiesta|session|tardeo|\bdj\b|halloween|pogo|noche|after", title, re.I) or is_crawl): continue
        if start < "20:00" and not re.search(r"tardeo|bacalao|party|fiesta|festival", title, re.I): continue
        sel.append((c, title, venue, addr, d, start))
    out = []
    for n, (c, title, venue, addr, d, start) in enumerate(sel):
        endt = None
        if n < MAX_DETAIL:
            try:
                dh = get(c["url"]); time.sleep(0.4)
                m = re.search(r"takes place on [A-Za-z]{3}, \d{1,2} [A-Za-z]{3},? (?:\d{4} )?at \d{1,2}:\d{2} [ap]m(?: to [A-Za-z]{3}, \d{1,2} [A-Za-z]{3},? (?:\d{4} )?at (\d{1,2}:\d{2} [ap]m))? at (.+?)\.?\"", dh.replace("\\/", "/"), re.I)
                if m:
                    if m.group(1): endt = _time(m.group(1))
                    if not addr:
                        tail = re.sub(r"\s*//\s*", ", ", m.group(2)); tail = re.sub(r",\s*Spain\.?$", "", tail).strip()
                        if tail.lower().startswith(venue.lower()): tail = tail[len(venue):].lstrip(", ").strip()
                        if tail and re.search(r"\d", tail): addr = tail
            except Exception as ex:
                log(NAME, "ficha", c["url"], ex)
        if endt == start: endt = None
        for rx, v in VENUE_ALIAS:
            if re.search(rx, venue, re.I): venue = v; break
        if addr: addr = re.sub(r"\s*//\s*", ", ", addr); addr = re.sub(r",\s*(Madrid,\s*)?ES$", "", addr).replace("Spain", "").strip(" ,") or None
        api = c["api"] or {}
        tk = api.get("tickets") or {}
        if api.get("tickets") and tk.get("min_ticket_price") is not None and tk.get("ticket_currency") == "EUR":
            lo, hi = tk["min_ticket_price"], tk.get("max_ticket_price")
            pmin, pmax, ptxt = _price(f"EUR {lo:g} to {hi:g}" if hi is not None and hi != lo else f"EUR {lo:g}" if lo else "Free")
        else:
            pmin, pmax, ptxt = _price(c["price"])
        pl = plain(title)
        conc = bool(re.search(r"riviera|las ventas|gruta|nazca|wagon|juglar|chango|caracol|blackbird|rock bar", plain(venue)))
        typ = "tardeo" if "tardeo" in pl else "festival" if re.search(r"festival", pl) else "after" if re.search(r"\bafter(show|party)?\b", pl) else \
              "concierto" if (conc or re.search(r"concierto|en concierto", pl)) and not re.search(r"party|fiesta", pl) else "club"
        out.append(event(title=title, date=d, start=start, end=endt, venue=venue, address=addr, type=typ, music=music_tags(title),
                         priceMin=pmin, priceMax=pmax, priceText=ptxt, free=pmin == 0,
                         sources=[{"name": NAME, "url": c["url"]}], ticketUrl=(tk.get("ticket_url") if tk.get("has_tickets") and tk.get("ticket_url") else c["url"])))
    return out
