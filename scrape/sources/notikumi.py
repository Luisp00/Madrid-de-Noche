"""Notikumi (notikumi.com): listado /place/Madrid paginado por offset (12 por página) y fichas con JSON-LD Event."""
import re, time
from scrape.common import get, soup, ld_json, event, parse_date, parse_time, parse_price, in_window, music_tags, clean_text, night_date, plain, log

NAME = "Notikumi"
MIN_EVENTS = 10
BASE = "https://www.notikumi.com"
MAX_PAGES = 12
MAX_DETAIL = 60
THEATRE_OK = re.compile(r"kapital|barcel|magno|eslava", re.I)
BAD_VENUE = re.compile(r"\bteatro\b|auditorio|ateneo|c[ií]rculo de bellas|palacio de congresos|cine\b|museo|centro cultural", re.I)
BAD_TITLE = re.compile(r"this is \w+ en madrid|tributo|tribute|monolog|stand ?up|comedia|musical\b|candlelight|karaoke|clase |taller|workshop|infantil|ballet|opera|[oó]pera|cena|magia|circo|espect[aá]culo para", re.I)
NIGHT_TAGS = re.compile(r"\b(club|clubs|clubbing|discoteca|discotecas|fiesta|fiestas|party|tardeo|after|dj|techno|reggaeton|electr[oó]nica)\b", re.I)

def _listing(today, end):
    out, seen, stop = [], set(), False
    for page in range(MAX_PAGES):
        url = f"{BASE}/place/Madrid?lang=en" + (f"&offset={12 * page}" if page else "")
        try: html = get(url)
        except Exception as ex: log(NAME, "listado", url, ex); break
        cards = soup(html).select("a.event-card")
        if not cards: break
        for a in cards:
            href = a.get("href", "")
            dt = a.select_one(".event-date-text")
            txt = clean_text(dt.get_text()) if dt else ""
            m = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", href)
            if not m: continue
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            if date > end: stop = True; continue
            if href in seen or date < today or "multiple" in txt.lower(): continue
            seen.add(href)
            tm = re.search(r"(\d{1,2}:\d{2})\s*$", txt)
            out.append((href, date, tm.group(1) if tm else None))
        if stop: break
        time.sleep(0.4)
    return out

def scrape(today, end):
    out = []
    for href, ldate, ltime in _listing(today, end)[:MAX_DETAIL]:
        url = BASE + href
        try: html = get(url + "?lang=en")
        except Exception as ex: log(NAME, "ficha", url, ex); continue
        time.sleep(0.4)
        d = next((x for x in ld_json(html) if x.get("@type") in ("Event", "MusicEvent")), None)
        if not d: continue
        title = clean_text(d.get("name"))
        loc = d.get("location") or {}
        venue = clean_text(loc.get("name") or "")
        venue = re.sub(r"\s+Madrid$", "", venue).strip()
        venue = {"Shôko": "Shoko"}.get(venue, venue)
        if not venue or not title: continue
        if BAD_VENUE.search(venue) and not THEATRE_OK.search(venue): continue
        if BAD_TITLE.search(title): continue
        ad = loc.get("address") or {}
        parts = [clean_text(ad.get("streetAddress") or ""), clean_text(" ".join(x for x in [ad.get("postalCode"), ad.get("addressLocality")] if x))]
        address = ", ".join(p for p in parts if p) or None
        sd = d.get("startDate") or ""
        start = sd.split("T")[1][:5] if "T" in sd else ltime
        date = ldate
        if not start: continue
        tags = [clean_text(a.get_text()) for a in soup(html).select(".c-tag-list a[href^='/tag/']")]
        tags = [x for x in tags if x]
        tagtxt = " ".join(tags)
        desc = clean_text(d.get("description") or "")
        night = bool(NIGHT_TAGS.search(plain(tagtxt + " " + title)))
        if not night and "Conciertos" not in tags: night = bool(re.search(r"\bclub\b|discoteca", plain(venue)))
        if start < "20:00" and not re.search(r"tardeo|after", plain(title + " " + tagtxt)): continue
        if not night and start < "20:00": continue
        pl = plain(title + " " + tagtxt)
        typ = "tardeo" if "tardeo" in pl else "after" if re.search(r"\bafter", pl) else "concierto" if re.search(r"concierto|live|jazz|rock|\bpunk|metal", pl) and not night else "club" if night else "concierto"
        price_txt = None; pmin = pmax = None; free = False
        if re.search(r"\d\s*(?:€|euros?)", desc, re.I):
            pmin, pmax, free = parse_price(desc)
            price_txt = clean_text(desc)[:120]
        elif re.search(r"\b(entrada|acceso)\s+(gratis|gratuit[ao]|libre)|\bgratis\b", desc, re.I):
            pmin, free, price_txt = 0, True, "Gratis"
        out.append(event(title=title, date=night_date(date, start), start=start, venue=venue, address=address, type=typ,
                         music=music_tags(title + " " + tagtxt) or (["otros"] if re.search(r"jazz|blues|swing", plain(title + " " + tagtxt)) else []), priceMin=pmin, priceMax=pmax, priceText=price_txt, free=free,
                         description=desc[:400] or None, sources=[{"name": NAME, "url": url}], ticketUrl=url))
    return [e for e in out if in_window(e["date"], today, end)]
