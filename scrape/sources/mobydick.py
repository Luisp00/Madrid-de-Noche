"""Moby Dick Club (mobydickclub.com/programacion.php): HTML servido con bloques div#grupoconcierto por mes
("Programación de conciertos · NOVIEMBRE 2026"): título (.conciertotitulo o title de la imagen), "JUEVES 5 de NOVIEMBRE. 21h.",
"ANTICIPADA: 10€. TAQUILLA: 15€.", botón COMPRAR ENTRADA y ficha propia (AMPLIAR). Todo son conciertos (solo ≥20:00)."""
import re, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Moby Dick Club"
MIN_EVENTS = 3
VENUE = "Moby Dick Club"
ADDRESS = "Av. Brasil 5, 28020 Madrid"
ZONE = "Tetuán / Azca"
BASE = "https://www.mobydickclub.com/"
URL = BASE + "programacion.php"

def scrape(today, end):
    try: html = get(URL)
    except Exception as ex: log(NAME, "programación", ex); return []
    s = soup(html)
    out, year, ymonth = [], int(today[:4]), None
    for el in s.select("#titularprog, #grupoconcierto"):
        if el.get("id") == "titularprog":
            m = re.search(r"([a-z]+)\s+(\d{4})", plain(el.get_text(" ")))
            if m and m.group(1) in MONTHS: ymonth, year = MONTHS[m.group(1)], int(m.group(2))
            continue
        fe = el.select_one(".conciertofecha")
        if not fe: continue
        ftxt = plain(fe.get_text(" "))
        m = re.search(r"(\d{1,2})\s+de\s+([a-z]+)", ftxt)
        if not m or m.group(2) not in MONTHS: continue
        day, mon = int(m.group(1)), MONTHS[m.group(2)]
        y = year + (1 if ymonth and mon < ymonth else 0)
        try: date = datetime.date(y, mon, day).isoformat()
        except ValueError: continue          # p. ej. "31 de NOVIEMBRE"
        mt = re.search(r"\.\s*(\d{1,2})(?:[:.](\d{2}))?\s*h", ftxt)
        start = f"{int(mt.group(1)):02d}:{int(mt.group(2) or 0):02d}" if mt and int(mt.group(1)) < 24 else None
        img = el.select_one("img[alt]")
        alt = clean_text(img.get("alt")) if img else ""
        t = el.select_one(".conciertotitulo")
        title = clean_text(t.get_text(" ")) if t else (clean_text(img.get("title")) if img and img.get("title") else "")
        if not title: continue
        pres = el.select_one(".conciertopresenta")
        if excluded_title(title, alt) or re.search(r"\btributo\b|tribute", plain(alt)): continue
        date = night_date(date, start)
        if not in_window(date, today, end): continue
        if not start or start < "20:00": continue
        pr = el.select_one(".conciertoprecio")
        ptxt = clean_text(pr.get_text(" ")) if pr else ""
        ant = re.search(r"anticipada[^:]*:(.*?)(?:taquilla|$)", ptxt, re.I | re.S)
        taq = re.search(r"taquilla[^:]*:(.*)$", ptxt, re.I | re.S)
        an, tq = euro_nums(ant.group(1) if ant else ""), euro_nums(taq.group(1) if taq else "")
        free = bool(re.search(r"entrada libre|gratis|gratuit", plain(ptxt)))
        nums = an + tq
        pmin = 0 if free else (min(an) if an else (min(tq) if tq else None))
        pmax = max(nums) if nums and pmin is not None and max(nums) > pmin else None
        amp = el.select_one("a.botonampliar[href]") or el.select_one("#fotothumbprog a[href]")
        url = BASE + amp["href"].lstrip("./") if amp and not amp["href"].startswith("http") else (amp["href"] if amp else URL)
        tk = el.select_one("a.botonentradas[href]")
        desc = el.select_one(".conciertotxt")
        dtxt = clean_text(desc.get_text(" ")) if desc else ""
        out.append(event(title=title,
                         date=date, start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type="concierto",
                         music=music_tags(dtxt[:400]) or ["indie", "rock"], priceMin=pmin, priceMax=pmax,
                         priceText=(ptxt[:120] if (nums or free) else None), free=free,
                         description=((clean_text(pres.get_text()) + ". " if pres else "") + dtxt)[:400] or None,
                         sources=[{"name": NAME, "url": url}],
                         ticketUrl=(tk["href"].strip() if tk and tk["href"].startswith("http") else url)))
    return out
