"""Dondego (dondego.es/madrid/fiestas): listado JSON-LD ItemList (varias vistas por mes) + fichas con Event/Place/precio/edad."""
import re, time, datetime
from scrape.common import get, soup, ld_json, event, parse_price, parse_time, in_window, music_tags, clean_text, night_date, plain, MONTHS, log

NAME = "Dondego"
MIN_EVENTS = 5
BASE = "https://dondego.es/madrid/fiestas/"
VIEWS = ["", "?date=hoy", "?date=octubre", "?date=noviembre"]
MAX_DETAIL = 50
BAD = re.compile(r"bingo|drag|parque warner|pumpkin|autocine|almudena|c[ií]rculo de bellas|infantil|karaoke|tributo|candlelight|teatro (?!kapital|barcel|magno|eslava)|museo|mercadillo|feria\b", re.I)
VENUE_FIX = {"fabrik madrid": "Fabrik", "sala siroco": "Siroco", "strong the club": "Sala Strong"}

def _candidates():
    out = {}
    for v in VIEWS:
        try: html = get(BASE + v)
        except Exception as ex: log(NAME, "listado", v, ex); continue
        for d in ld_json(html):
            if d.get("@type") != "ItemList": continue
            for it in d.get("itemListElement", []):
                e = it.get("item") or {}
                if e.get("url"): out[e["url"]] = e
    return out

def _dates(when, start_iso, end_iso, today):
    """Noches de la ficha: rango 'D–D mes' si lo hay, si no la fecha de startDate."""
    m = re.search(r"(\d{1,2})\s*[–-]\s*(\d{1,2})\s+([a-záéíóú]+)", when or "", re.I)
    base = start_iso[:10]
    if m and plain(m.group(3)) in MONTHS:
        d1, d2, mo = int(m.group(1)), int(m.group(2)), MONTHS[plain(m.group(3))]
        y = int(base[:4])
        try:
            a, b = datetime.date(y, mo, d1), datetime.date(y, mo, d2)
            if 0 <= (b - a).days <= 4: return [(a + datetime.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]
        except ValueError: pass
    return [base]

def scrape(today, end):
    out = []
    cands = {u: e for u, e in _candidates().items() if e.get("startDate") and e["startDate"][:10] <= end}
    # quedan solo los que empiezan en ventana, o que pueden ser rangos que empiezan antes
    cands = {u: e for u, e in cands.items() if e["startDate"][:10] >= (datetime.date.fromisoformat(today) - datetime.timedelta(days=4)).isoformat()}
    for url, c in list(cands.items())[:MAX_DETAIL]:
        if BAD.search(c.get("name", "")): continue
        try: html = get(url)
        except Exception as ex: log(NAME, "ficha", url, ex); continue
        time.sleep(0.4)
        lds = ld_json(html)
        d = next((x for x in lds if x.get("@type") == "Event"), None)
        pl = next((x for x in lds if x.get("@type") == "Place"), None)
        if not d: continue
        title = re.sub(r"^(Fiesta|Festival)\s+[«\"]?(.*?)[»\"]?$", r"\2", clean_text(d.get("name")))
        title = re.sub(r"[«»]", "", title)
        vname = clean_text((pl or {}).get("name") or (c.get("location") or {}).get("name") or "")
        if not vname or BAD.search(vname) or BAD.search(title): continue
        venue = VENUE_FIX.get(plain(vname), vname)
        addr = clean_text(((pl or {}).get("address") or {}).get("streetAddress") or "") or None
        sp = soup(html)
        for x in sp(["script", "style", "svg"]): x.decompose()
        txt = clean_text(sp.get_text(" "))
        m = re.search(r"¿Cuándo\?\s*(.{0,60}?)\s*¿Dónde", txt)
        when = m.group(1) if m else ""
        tm = re.search(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", when)
        sd = d.get("startDate", "")
        start = (tm.group(1) if tm else sd.split("T")[1][:5] if "T" in sd else None)
        endt = parse_time(tm.group(2)) if tm else None
        if start:
            start = parse_time(start)
        if start and start < "14:00": continue
        age = None
        m = re.search(r"Límite de edad\s*(\d{1,2})\+", txt)
        if m: age = int(m.group(1))
        pmin = pmax = None; ptxt = None; free = False
        o = d.get("offers") or {}
        if isinstance(o, list): o = o[0] if o else {}
        try:
            lo = float(o.get("lowPrice") if o.get("lowPrice") is not None else o.get("price"))
            hi = float(o["highPrice"]) if o.get("highPrice") is not None else None
            pmin = int(lo) if lo == int(lo) else lo
            if hi and hi > lo and hi <= 100: pmax = int(hi) if hi == int(hi) else hi
            free = lo == 0
            ptxt = ("Gratis" if lo == 0 else f"{pmin:g} € – {pmax:g} €" if pmax else f"Desde {pmin:g} €")
        except (TypeError, ValueError):
            m = re.search(r"Precio\s*(\d[\d,.]*\s*€(?:\s*—\s*\d[\d,.]*\s*€)?)", txt)
            if m: pmin, pmax, free = parse_price(m.group(1)); ptxt = m.group(1)[:120]
        desc = clean_text(d.get("description") or "")[:400] or None
        ticket = o.get("url") or url
        pl_ = plain(title + " " + (desc or ""))
        typ = "festival" if "festival" in plain(d.get("name", "")) else "tardeo" if "tardeo" in pl_ else "after" if re.search(r"\bafter\b", pl_) else "club"
        for night in _dates(when, sd, d.get("endDate"), today):
            date = night_date(night, start) if start and start < "06:00" and night == sd[:10] else night
            if not in_window(date, today, end): continue
            out.append(event(title=title, date=date, start=start, end=endt, venue=venue, address=addr, type=typ, music=music_tags(title + " " + (desc or "")),
                             priceMin=pmin, priceMax=pmax, priceText=ptxt, free=free, ageMin=age, description=desc,
                             sources=[{"name": NAME, "url": url}], ticketUrl=ticket))
    return out
