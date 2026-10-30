"""Shoko (shokomadrid.com, Shopify): los eventos son productos de la colección "eventos-shoko-madrid" (products.json).
Fecha del título ("THE ROOM - friday, 30.10.2026"); hora de la ficha del producto ("Éxitos del hip hop y el R&B | A partir de las 23:45")
o del body ("From 6:00 PM to 11:00 PM" en los tardeos). El producto de Shopify vale 0 €: el precio real, el estado y el dress code
vienen del widget de PATT que incrusta la ficha (iframe events.patt.club/embed/event/<id>), leído con la misma API que usa nightlifemadrid.py."""
import re, time, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, log

NAME = "Shoko"
MIN_EVENTS = 4
VENUE = "Shoko"
ADDRESS = "C/ Toledo 86, 28005 Madrid"
ZONE = "La Latina"
BASE = "https://shokomadrid.com"
FEED = BASE + "/collections/eventos-shoko-madrid/products.json?limit=250"
MAX_DETAIL = 40

def _t(h, mi, ap=None):
    h, mi = int(h), int(mi or 0)
    if ap and ap.lower() == "pm" and h < 12: h += 12
    if ap and ap.lower() == "am" and h == 12: h = 0
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None

def _range(txt):
    """'From 6:00 PM to 11:00 PM' / 'de 18:00 a 23:00' -> (start, end)."""
    m = re.search(r"(?:from|de|desde)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|h)?\s*(?:to|a|hasta)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|h)?", txt, re.I)
    if not m: return None, None
    ap2 = m.group(6) if m.group(6) and m.group(6).lower() != "h" else None
    ap1 = m.group(3) if m.group(3) and m.group(3).lower() != "h" else ap2
    return _t(m.group(1), m.group(2), ap1), _t(m.group(4), m.group(5), ap2)

def _detail(url):
    """(subtítulo de la cabecera, descripción 'Meet the artist') de la ficha del producto."""
    try: html = get(url)
    except Exception as ex: log(NAME, "ficha", url, ex); return "", "", None
    s = soup(html)
    sub = s.select_one(".text_position_abs > p")
    desc = s.select_one(".contentsl .metafield-rich_text_field")
    m = re.search(r"events\.patt\.club/embed/event/([0-9a-f]{24})", html)
    return (clean_text(sub.get_text(" ")) if sub else ""), (clean_text(desc.get_text(" ")) if desc else ""), (m.group(1) if m else None)

def _patt(eid):
    """Precio, estado, dress code y edad de la sesión en PATT (la ticketera del widget). {} si no hay entradas."""
    if not eid: return {}
    try:
        from scrape.sources import nightlifemadrid as nm
        return nm.price_info(nm.detail(eid)) or {}
    except Exception as ex:
        log(NAME, "patt", eid, ex); return {}

def scrape(today, end):
    try: prods = get(FEED, json_=True).get("products", [])
    except Exception as ex: log(NAME, "products.json", ex); return []
    log(NAME, "productos:", len(prods))
    hi = (datetime.date.fromisoformat(end) + datetime.timedelta(days=1)).isoformat()
    out, n = [], 0
    for p in prods:
        raw = clean_text(p.get("title"))
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$", raw)
        if not m: continue
        try: date = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError: continue
        if not (today <= date <= hi): continue
        title = clean_text(re.sub(r"\s*-?\s*\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b\s*,?\s*$", "", raw[:m.start()], flags=re.I))
        title = re.sub(r"\s*-\s*$", "", title)
        body = clean_text(soup(p.get("body_html") or "").get_text(" "))
        url = f"{BASE}/products/{p['handle']}"
        sub, desc, eid = "", "", None
        if n < MAX_DETAIL:
            n += 1; sub, desc, eid = _detail(url); time.sleep(0.4)
        px = _patt(eid)
        start, endt = _range(body)
        if not start:
            mt = re.search(r"(?:a partir de las|desde las|from)\s+(\d{1,2})[:.](\d{2})", sub + " " + body, re.I)
            if mt: start = _t(mt.group(1), mt.group(2))
        pl = plain(title + " " + body)
        typ = "tardeo" if "tardeo" in pl or (start and "14:00" <= start < "20:00") else "club"
        d = night_date(date, start)
        if not in_window(d, today, end): continue
        text = " ".join(x for x in [sub, desc or body] if x)
        out.append(event(title=title, date=d, start=start, end=endt, venue=VENUE, address=ADDRESS, zone=ZONE, type=typ,
                         music=music_tags(title + " " + text) or ["comercial", "latino"], description=(text[:400] or None),
                         priceMin=px.get("priceMin"), priceMax=px.get("priceMax"), priceText=px.get("priceText"), free=bool(px.get("free")),
                         status=px.get("status") or "desconocido", dressCode=px.get("dressCode"), ageMin=px.get("ageMin"),
                         sources=[{"name": NAME, "url": url}], ticketUrl=url))
    return out
