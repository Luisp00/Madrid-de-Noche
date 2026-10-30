"""Taquilla.com: listados de discotecas (microdata schema.org por sesión) + fichas /entradas/{slug} con todas las sesiones."""
import re, time, datetime
from scrape.common import get, soup, event, parse_time, in_window, music_tags, clean_text, night_date, plain, log

NAME = "Taquilla.com"
MIN_EVENTS = 20
BASE = "https://www.taquilla.com"
LIST_URLS = [BASE + "/conciertos/discotecas/madrid", BASE + "/conciertos/discotecas", BASE + "/conciertos/discotecas/page/1",
             BASE + "/humanes-de-madrid/fabrik-humanes"]
MAX_DETAIL = 55
CITIES = ("madrid", "humanes", "fuenlabrada", "alcorcon", "alcobendas", "getafe", "leganes", "mostoles", "pozuelo", "majadahonda",
          "las rozas", "torrejon", "alcala de henares", "san sebastian de los reyes", "rivas", "coslada", "parla", "pinto", "boadilla")
NOT_MADRID = ("barcelona", "valencia", "sevilla", "malaga", "bilbao", "granada", "cordoba", "alicante", "zaragoza", "jerez", "gran canaria",
              "durango", "armilla", "murcia", "vigo", "palma", "tenerife")
EXCLUDE = re.compile(r"sin esperas|shisha|cachimba|karaoke|tributo|tribute|monolog|stand ?up|comedia|clase de|taller|candlelight|musical|drag |cena|bingo|tablao|escape", re.I)
CRAWL = re.compile(r"pub ?crawl|bar ?crawl|ruta de bares", re.I)

def _meta(li, p):
    e = li.select_one(f"meta[itemprop={p}]")
    return e.get("content") if e else None

def _is_madrid(loc, street, name, title):
    blob = plain(" ".join(x or "" for x in (loc, street, name)))
    if any(c in blob for c in NOT_MADRID): return False
    if any(re.search(r"\b" + re.escape(c) + r"\b", blob) for c in CITIES): return True
    return bool(re.search(r"\b280\d\d\b|\b289\d\d\b", blob)) or bool(re.search(r"-\s*madrid\s*$", plain(title)))

def _sessions(html):
    """Sesiones (dicts) de un listado o ficha."""
    out = []
    for li in soup(html).select("li[itemscope][itemtype]"):
        t = li.get("itemtype", "")
        if "Event" not in t or "EventVenue" in t: continue
        url = _meta(li, "url") or ""
        m = re.search(r"/entradas/([^/?#]+)\?event=(\d+)", url)
        if not m: continue
        loc = li.select_one("[itemprop=location]")
        venue = _meta(loc, "name") if loc else None
        times = [x.get_text(strip=True) for x in li.select(".ent-results-list-hour-time")]
        avail = clean_text(li.select_one(".ent-results-list-availability").get_text()) if li.select_one(".ent-results-list-availability") else ""
        out.append(dict(slug=m.group(1), id=m.group(2), title=_meta(li, "name") or "", date=(_meta(li, "startDate") or "")[:10],
                        venue=venue, street=_meta(loc, "streetAddress") if loc else None, city=_meta(loc, "addressLocality") if loc else None,
                        low=_meta(li, "lowPrice"), high=_meta(li, "highPrice"), times=times, avail=avail))
    return out

def _num(x):
    try: return float(x)
    except Exception: return None

def _clean_title(t):
    t = clean_text(t)
    t = re.sub(r"\s+-\s+(Madrid|Humanes de Madrid|Fuenlabrada|Alcorc[oó]n|Getafe|Legan[eé]s)$", "", t, flags=re.I)
    t = re.sub(r"\s+de\s*!", "!", t)
    return t.strip(" -")

def _venue(s):
    v = clean_text(s["venue"] or "")
    v = re.sub(r"\s+Madrid,\s*\d{5}$", "", v)
    if re.match(r"a concretar", v, re.I):
        m = re.search(r"\ben\s+([A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ' .&-]{2,40})$", _clean_title(s["title"]))
        return clean_text(m.group(1)) if m else None
    v = re.sub(r"^Plaza de Toros de Las Ventas$", "Las Ventas", v, flags=re.I)
    v = re.sub(r"^Sala Siroco$", "Siroco", v, flags=re.I)
    return v or None

def _to_event(s, today, end, desc=None):
    title = _clean_title(s["title"])
    if EXCLUDE.search(title) or EXCLUDE.search(s["venue"] or ""): return None
    d = s["date"]
    if not in_window(d, today, end) and not in_window(d, (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat(), end): return None
    if CRAWL.search(title) and d > (datetime.date.fromisoformat(today) + datetime.timedelta(days=2)).isoformat(): return None
    venue = _venue(s)
    if not venue: return None
    start = None
    for t in s["times"]:
        if re.match(r"^\d{1,2}:\d{2}$", t): start = parse_time(t); break
    date = night_date(d, start)
    if not in_window(date, today, end): return None
    pl = plain(title)
    typ = "tardeo" if "tardeo" in pl else "after" if re.search(r"\bafter\b", pl) else "festival" if re.search(r"festival|fest\b|hallowfest|xxl|masters of", pl) else "club"
    if typ == "club" and re.search(r"concierto|live\b|\(live\)", pl): typ = "concierto"
    if start and start < "20:00" and typ in ("club", "concierto") and not re.search(r"fiesta|party|session|dj|noche", pl): return None
    lo, hi = _num(s["low"]), _num(s["high"])
    pmin = pmax = None; ptxt = None
    if lo is not None and lo > 0:
        pmin = int(lo) if lo == int(lo) else round(lo, 2)
        if hi and hi > lo: pmax = int(hi) if hi == int(hi) else round(hi, 2)
        ptxt = f"{pmin:g} € – {pmax:g} €" if pmax else f"{pmin:g} €"
    av = plain(s["avail"])
    status = "agotado" if "agotad" in av else "ultimas" if re.search(r"baja|ultim|pocas", av) else "disponible" if pmin else "desconocido"
    street = clean_text(re.sub(r",?\s*España\s*$", "", s["street"] or "")) or None
    if street and not re.search(r"\d{5}", street) and s["city"] and s["city"] not in street: street = f"{street}, {s['city']}"
    url = f"{BASE}/entradas/{s['slug']}?event={s['id']}"
    return event(title=title, date=date, start=start, venue=venue, address=street, type=typ, music=music_tags(title),
                 priceMin=pmin, priceMax=pmax, priceText=ptxt, description=desc, status=status,
                 sources=[{"name": NAME, "url": url}], ticketUrl=url)

def scrape(today, end):
    sessions, seen = [], set()
    for lu in LIST_URLS:
        try: html = get(lu)
        except Exception as ex: log(NAME, "listado", lu, ex); continue
        for s in _sessions(html):
            if s["id"] in seen or not _is_madrid(s["city"], s["street"], s["venue"], s["title"]): continue
            seen.add(s["id"]); sessions.append(s)
    # fichas de las entidades con sesiones de ocio nocturno: traen todas las sesiones de la ventana
    slugs = []
    for s in sessions:
        if s["slug"] in slugs or EXCLUDE.search(s["title"]) or CRAWL.search(s["title"]): continue
        slugs.append(s["slug"])
    descs = {}
    for slug in slugs[:MAX_DETAIL]:
        try: html = get(f"{BASE}/entradas/{slug}")
        except Exception as ex: log(NAME, "ficha", slug, ex); continue
        sp = soup(html)
        card = sp.select_one(".card-content")
        if card:
            txt = clean_text(card.get_text(" ")); txt = re.sub(r"^Descripci[oó]n\s*", "", txt)
            descs[slug] = txt[:300] if txt else None
        for s in _sessions(html):
            if s["id"] not in seen and _is_madrid(s["city"], s["street"], s["venue"], s["title"]):
                seen.add(s["id"]); sessions.append(s)
        time.sleep(0.4)
    out = []
    for s in sessions:
        vslug = plain(_venue(s) or "").replace(" ", "-")
        desc = descs.get(s["slug"]) if s["slug"] not in vslug and vslug not in s["slug"] else None
        ev = _to_event(s, today, end, desc)
        if ev: out.append(ev)
    return out
