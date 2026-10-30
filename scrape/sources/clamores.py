"""Sala Clamores (salaclamores.es/calendario, Webflow con HTML servido): tarjetas a.card-blog-post-list con día, mes (inglés),
precio ("Dsd 11€ + G.G", "15€ + G.G.", "Dsd Free"), fecha en castellano, hora y título; enlazan a la ficha /eventos/<slug>.
Las sesiones de Clamores Dance Club (slug con club/session/party o hora ≥ 23:00) son "club"; el resto conciertos (solo ≥ 20:00)."""
import re, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, infer_year, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Sala Clamores"
MIN_EVENTS = 4
VENUE = "Sala Clamores"
ADDRESS = "C/ Alburquerque 14, 28010 Madrid"
ZONE = "Chamberí"
BASE = "https://www.salaclamores.es"

def scrape(today, end):
    try: html = get(BASE + "/calendario")
    except Exception as ex: log(NAME, "calendario", ex); return []
    out, seen = [], set()
    for a in soup(html).select("a.card-blog-post-list[href]"):
        href = a["href"]
        url = BASE + href if href.startswith("/") else href
        if url in seen: continue
        seen.add(url)
        g = lambda sel: clean_text(a.select_one(sel).get_text(" ")) if a.select_one(sel) else ""
        day, mon = g(".date-component-calendar-2"), plain(g(".date-component-calendar-3"))
        if not day.isdigit() or mon not in MONTHS: continue
        try: date = datetime.date(infer_year(MONTHS[mon], int(day), today), MONTHS[mon], int(day)).isoformat()
        except ValueError: continue
        tm = re.search(r"(\d{1,2}):(\d{2})", g(".date-component-calendar4"))
        start = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None
        date = night_date(date, start)
        if not in_window(date, today, end): continue
        title = g("h2.heading-4") or clean_text((a.select_one("img[alt]") or {}).get("alt", ""))
        if not title or excluded_title(title) or re.search(r"burlesque|brunch|vermu|premios", plain(title)): continue
        slug = plain(href)
        club = bool(re.search(r"club-session|dance-club|clamores-club|party|perreo", slug)) or bool(start and (start >= "23:00" or start < "06:00"))
        typ = "club" if club else "concierto"
        if typ == "concierto" and (not start or start < "20:00"): continue
        ptxt = g("h1.post-heading")
        pp = plain(ptxt)
        nums = euro_nums(ptxt)
        free = bool(re.search(r"\bfree\b|gratis|gratuit|libre", pp))
        desde = bool(re.search(r"\b(dsd|desde)\b", pp))
        pmin = 0 if free and not nums else (min(nums) if nums else None)
        pmax = None if desde or not nums or max(nums) == pmin else max(nums)
        if free and nums: pmin, pmax = 0, None
        genre = re.search(r"\(([^)]+)\)\s*$", title)
        out.append(event(title=title, date=date, start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type=typ,
                         music=music_tags(re.sub(r"grabaci[oó]n (?:de )?disco", " ", plain((genre.group(1) if genre else "") + " " + title + " " + slug.replace("-", " ")))) or ([] if typ == "concierto" else ["comercial"]),
                         priceMin=pmin, priceMax=pmax, priceText=(ptxt.replace("Dsd", "Desde").replace("G.G", "gastos")[:120] if ptxt else None), free=free,
                         description=("Clamores Dance Club." if typ == "club" else None),
                         sources=[{"name": NAME, "url": url}], ticketUrl=url))
    return out
