"""Changó (salachango.es, Next.js con HTML servido): fichas /eventos/<slug-con-fecha> (conciertos y especiales) enlazadas desde
/eventos y /conciertos, cada una con JSON-LD Event (inicio, fin, enlace de compra). Las sesiones residentes no tienen ficha:
la web dice "AURA los jueves y viernes. CHICLE todos los sábados" y enlaza a Fourvenues (bloqueado por Cloudflare, no se visita),
así que se emite una sesión por cada jueves/viernes/sábado de la ventana salvo que esa noche haya un especial de club, sin hora ni precio."""
import re, time, datetime
from scrape.common import get, soup, ld_json, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Changó"
MIN_EVENTS = 4
VENUE = "Changó"
ADDRESS = "C/ Covarrubias 42, 28010 Madrid"
ZONE = "Chamberí"
BASE = "https://salachango.es"
MAX_DETAIL = 30

def _slug_date(href):
    m = re.search(r"-(\d{1,2})-([a-z]+)-(\d{4})$", href.rstrip("/"))
    if not m or m.group(2) not in MONTHS: return None
    try: return datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
    except ValueError: return None

def _residents(html):
    """{weekday: (nombre, url de entradas)} según el bloque "Sesiones residentes"."""
    p = plain(soup(html).get_text(" "))
    links = re.findall(r'href="(https://www\.fourvenues\.com/[a-z0-9-]+)"', html)
    aura = next((l for l in links if "chicle" not in l), None)
    chicle = next((l for l in links if "chicle" in l), None)
    out = {}
    if re.search(r"aura\s+(?:los\s+)?jueves\s*(?:y|·)\s*viernes", p):
        out[3] = out[4] = ("AURA", aura)
    if re.search(r"chicle\s+(?:todos\s+)?(?:los\s+)?sabados", p):
        out[5] = ("CHICLE", chicle)
    return out

def scrape(today, end):
    hi = (datetime.date.fromisoformat(end) + datetime.timedelta(days=1)).isoformat()
    links, res = {}, {}
    for path in ("/eventos", "/conciertos"):
        try: html = get(BASE + path)
        except Exception as ex: log(NAME, path, ex); continue
        if path == "/eventos": res = _residents(html)
        for h in re.findall(r'href="(/eventos/[a-z0-9-]+)"', html):
            d = _slug_date(h)
            if d and today <= d <= hi: links[BASE + h] = d
    out, special_nights, n = [], set(), 0
    for url in sorted(links, key=links.get):
        if n >= MAX_DETAIL: break
        n += 1
        try: html = get(url)
        except Exception as ex: log(NAME, "ficha", url, ex); continue
        time.sleep(0.4)
        ev = next((x for x in ld_json(html) if "Event" in str(x.get("@type"))), None)
        if not ev: continue
        title = clean_text(re.sub(r"\s*·\s*Sala Chang[oó].*$", "", ev.get("name") or "", flags=re.I))
        sd, ed = ev.get("startDate") or "", ev.get("endDate") or ""
        start = sd[11:16] if "T" in sd else None
        endt = ed[11:16] if "T" in ed else None
        date = night_date(sd[:10] or links[url], start)
        if not in_window(date, today, end): continue
        sp = soup(html)
        main = sp.select_one("main") or sp
        first = plain(main.get_text(" | ", strip=True)[:40]).split("|")[0].strip()
        is_concert = ev.get("@type") == "MusicEvent" or first == "concierto"
        desc = clean_text(ev.get("description") or "")
        if excluded_title(title, desc[:120]): continue
        typ = "concierto" if is_concert else ("tardeo" if start and "14:00" <= start < "20:00" else "club")
        if typ == "concierto" and (not start or start < "20:00"): continue
        if typ != "concierto": special_nights.add(date)
        off = ev.get("offers") or {}
        off = off[0] if isinstance(off, list) and off else off
        price = off.get("price") if isinstance(off, dict) else None
        nums = euro_nums(desc)
        pmin = float(price) if price not in (None, "") else (min(nums) if nums else None)
        if pmin is not None and pmin == int(pmin): pmin = int(pmin)
        tk = off.get("url") if isinstance(off, dict) else None
        out.append(event(title=title, date=date, start=start, end=endt, venue=VENUE, address=ADDRESS, zone=ZONE, type=typ,
                         music=music_tags(title + " " + desc), priceMin=pmin,
                         priceText=(f"{pmin} €" if pmin is not None else None), description=(desc[:400] or None),
                         status=("agotado" if "SoldOut" in str(off.get("availability") if isinstance(off, dict) else "") else "desconocido"),
                         sources=[{"name": NAME, "url": url}], ticketUrl=tk or url))
    d0, d1 = datetime.date.fromisoformat(today), datetime.date.fromisoformat(end)
    while d0 <= d1:
        r = res.get(d0.weekday())
        if r and d0.isoformat() not in special_nights:
            name, tk = r
            out.append(event(title=f"{name} · Sala Changó", date=d0.isoformat(), venue=VENUE, address=ADDRESS, zone=ZONE, type="club",
                             music=[], description=f"Sesión residente de Changó ({'jueves y viernes' if name == 'AURA' else 'sábados'} según la web de la sala).",
                             sources=[{"name": NAME, "url": BASE + "/eventos#" + name.lower()}], ticketUrl=tk or BASE + "/eventos"))
        d0 += datetime.timedelta(days=1)
    return out
