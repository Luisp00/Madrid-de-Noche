"""Ochoymedio (ochoymedioclub.com): promotora con conciertos en varias salas y el club de los sábados.
Conciertos: tienda WooCommerce, API pública /wp-json/wc/store/v1/products (una petición): nombre, enlace, precio (céntimos, gastos
incluidos), stock, categoría = sala, y descripción corta "FECHA: viernes, 6 noviembre, 2026 · HORA: PUERTAS 20:00H · LUGAR: SALA BUT".
Club: /entradas-club/ (tarjetas omc-club-widget: título, sala, DJs, "7 noviembre 00:30", botón de entradas). La fecha de la tarjeta
es la de la noche (coincide con la de Dice, "7th nov"), así que no se resta un día aunque la hora sea 00:30. Precio del club: no lo publica."""
import re, datetime, html as _html
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, infer_year, log
from scrape.sources._filtros import excluded_title
from scrape.sources._salas import resolve

NAME = "Ochoymedio"
MIN_EVENTS = 3
BASE = "https://ochoymedioclub.com"
API = BASE + "/wp-json/wc/store/v1/products?per_page=100"
CLUB = BASE + "/entradas-club/"

def _venue(name):
    r = resolve(name)
    return r if r else (clean_text(name).title(), None, "Otros")

def _date(txt, today):
    m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-z]+),?\s*(\d{4})?", plain(txt))
    if not m or m.group(2) not in MONTHS: return None
    d, mo = int(m.group(1)), MONTHS[m.group(2)]
    y = int(m.group(3)) if m.group(3) else infer_year(mo, d, today)
    try: return datetime.date(y, mo, d).isoformat()
    except ValueError: return None

def _concerts(today, end):
    try: items = get(API, json_=True)
    except Exception as ex: log(NAME, "store api", ex); return []
    out = []
    for p in items:
        name = clean_text(_html.unescape(p.get("name") or ""))
        sd = clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", p.get("short_description") or p.get("description") or "")))
        cats = [clean_text(_html.unescape(c.get("name") or "")) for c in p.get("categories") or []]
        if re.search(r"producto prueba|abono", plain(name)) or any(plain(c) == "barcelona" for c in cats) or "barcelona" in plain(sd): continue
        fm = re.search(r"FECHA:\s*(.*?)(?:HORA|PUERTAS|LUGAR|$)", sd, re.I)
        date = _date(fm.group(1), today) if fm else None
        if not date: continue
        cm = re.search(r"CONCIERTO:?\s*(\d{1,2})[:.](\d{2})", sd, re.I) or re.search(r"(?:HORA|PUERTAS):?\s*(?:PUERTAS\s*)?(\d{1,2})[:.](\d{2})", sd, re.I)
        start = f"{int(cm.group(1)):02d}:{cm.group(2)}" if cm else None
        date = night_date(date, start)
        if not in_window(date, today, end) or not start or start < "20:00": continue
        if excluded_title(name): continue
        lm = re.search(r"LUGAR:\s*(.*?)(?:GASTOS|YA INCLUIDO|$)", sd, re.I)
        vname = cats[0] if cats else (lm.group(1) if lm else "")
        venue, address, zone = _venue(vname)
        pr = p.get("prices") or {}
        unit = 10 ** int(pr.get("currency_minor_unit", 2) or 2)
        rng = pr.get("price_range") or {}
        try:
            lo = int(rng.get("min_amount") or pr.get("price")) / unit
            hi = int(rng.get("max_amount") or pr.get("price")) / unit
        except (TypeError, ValueError): lo = hi = None
        fix = lambda x: (int(x) if x == int(x) else round(x, 2)) if x is not None else None
        lo, hi = fix(lo), fix(hi)
        status = "disponible" if p.get("is_in_stock") else "agotado"
        ptxt = (f"{lo} €" if not hi or hi == lo else f"{lo}–{hi} €") + " (gastos incluidos)" if lo is not None else None
        out.append(event(title=name, date=date, start=start, venue=venue, address=address, zone=zone, type="concierto",
                         music=music_tags(name) or ["pop", "indie"], priceMin=lo, priceMax=(hi if hi and lo is not None and hi > lo else None),
                         priceText=ptxt, free=(lo == 0), description=(sd[:400] or None), status=status,
                         sources=[{"name": NAME, "url": p.get("permalink")}], ticketUrl=p.get("permalink")))
    return out

def _club(today, end):
    try: html = get(CLUB)
    except Exception as ex: log(NAME, "club", ex); return []
    out = []
    for c in soup(html).select("article.omc-club-widget__card"):
        t = c.select_one(".omc-club-widget__event-title")
        dt = c.select_one(".omc-club-widget__date")
        if not t or not dt: continue
        title = clean_text(t.get_text(" "))
        tm = c.select_one(".omc-club-widget__time")
        start = None
        if tm:
            m = re.search(r"(\d{1,2})[:.](\d{2})", tm.get_text())
            if m: start = f"{int(m.group(1)):02d}:{m.group(2)}"
            tm.extract()
        date = _date(dt.get_text(" "), today)
        if not date or not in_window(date, today, end): continue
        room = c.select_one(".omc-club-widget__room")
        venue, address, zone = _venue(room.get_text(" ") if room else "")
        djs = [clean_text(s.get_text()) for s in c.select(".omc-club-widget__djs span") if clean_text(s.get_text())]
        a = c.select_one("a.omc-club-widget__button[href]")
        tk = a["href"].strip() if a else CLUB
        if plain(title) in ("tba", "tbc", ""): title = "Ochoymedio Club"
        elif "ochoymedio" not in plain(title): title = f"Ochoymedio Club: {title}"
        typ = "tardeo" if start and "14:00" <= start < "21:00" else "club"
        out.append(event(title=title, date=date, start=start, venue=venue, address=address, zone=zone, type=typ,
                         music=["pop", "indie"], lineup=djs, description="Club de pop de Ochoymedio.",
                         sources=[{"name": NAME, "url": tk if tk.startswith("http") else CLUB}], ticketUrl=tk))
    return out

def scrape(today, end):
    return _concerts(today, end) + _club(today, end)
