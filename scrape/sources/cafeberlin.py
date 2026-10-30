"""Café Berlín (berlincafe.es/programa/, WordPress): listado paginado (9 por página, ordenado por publicación, no por fecha)
con día de la semana + día + mes (sin año), hora, "Entradas desde: X€", categoría (cafe-berlin = conciertos, berlin-club = club)
y botón ENTRADAS (cafeberlinentradas.com / tickets.berlinclub.es). El año se deduce del día de la semana.
La API wp-json/wp/v2/project (sin fecha de evento) da el texto de cada ficha: "Apertura de puertas", "Entradas Taquilla: 27€"."""
import re, time, datetime, html as _html
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, infer_year, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Café Berlín"
MIN_EVENTS = 4
VENUE = "Café Berlín"
ADDRESS = "Costanilla de los Ángeles 20, 28013 Madrid"
ZONE = "Centro / Sol"
BASE = "https://berlincafe.es"
MAX_PAGES = 14
WD = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}

def _date(wd, day, mon, today):
    t = datetime.date.fromisoformat(today)
    cands = []
    for y in (t.year - 1, t.year, t.year + 1):
        try: d = datetime.date(y, mon, day)
        except ValueError: continue
        if wd is None or d.weekday() == wd: cands.append(d)
    if not cands: return datetime.date(infer_year(mon, day, today), mon, day)
    return min(cands, key=lambda d: abs((d - t).days))

def _api():
    """{link: texto de la ficha} de los ~100 programas publicados más recientes."""
    try: items = get(BASE + "/wp-json/wp/v2/project?per_page=100", json_=True)
    except Exception as ex: log(NAME, "wp-json", ex); return {}
    return {p.get("link", "").rstrip("/").lower(): clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", (p.get("content") or {}).get("rendered", "")))) for p in items}

def scrape(today, end):
    texts = _api()
    t0 = datetime.date.fromisoformat(today)
    out, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = BASE + "/programa/" + (f"page/{page}/" if page > 1 else "")
        try: html = get(url)
        except Exception as ex: log(NAME, "listado", url, ex); break
        arts = soup(html).select("article.programas-lista-programa")
        if not arts: break
        recent = False
        for a in arts:
            box = a.select_one(".fecha-evento")
            h = a.select_one("h2")
            lk = a.select_one(".programa-informacion a[href]")
            if not box or not h or not lk: continue
            wdn = plain((box.select_one(".evento-fecha-dia-nombre") or box).get_text())[:3]
            dd = re.search(r"\d{1,2}", (box.select_one(".evento-fecha-dia") or box).get_text())
            mm = plain((box.select_one(".evento-fecha-mes") or box).get_text())[:3]
            if not dd or mm not in MONTHS: continue
            d = _date(WD.get(wdn), int(dd.group()), MONTHS[mm], today)
            if d >= t0 - datetime.timedelta(days=45): recent = True
            link = lk["href"].strip()
            if link in seen: continue
            seen.add(link)
            title = clean_text(h.get_text(" "))
            info = clean_text((a.select_one("h5") or a).get_text(" "))
            mt = re.search(r"\b(\d{1,2}):(\d{2})\b", info)
            start = f"{int(mt.group(1)):02d}:{mt.group(2)}" if mt else None
            date = night_date(d.isoformat(), start)
            if not in_window(date, today, end): continue
            cls = " ".join(a.find_parent(class_="isotope-item").get("class", [])) if a.find_parent(class_="isotope-item") else ""
            club = "berlin-club" in cls
            typ = "club" if club else "concierto"
            if club and start and "14:00" <= start < "21:00": typ = "tardeo"
            if typ == "concierto" and (not start or start < "20:00"): continue
            if excluded_title(title): continue
            body = texts.get(link.rstrip("/").lower(), "")
            desde = euro_nums(info)
            mtq = re.search(r"taquilla[^€]{0,20}\d+(?:[.,]\d+)?\s*€", body, re.I)
            taq = euro_nums(mtq.group(0)) if mtq else []
            pmin = desde[0] if desde else None
            pmax = taq[0] if taq and pmin is not None and taq[0] > pmin else None
            free = pmin == 0
            parts = []
            if pmin is not None: parts.append("Gratis" if free else f"Desde {pmin} €")
            if taq: parts.append(f"Taquilla {taq[0]} €")
            doors = re.search(r"apertura de puertas:?\s*(\d{1,2}[:.]\d{2})", body, re.I)
            tk = a.select_one("a.btn-entradas[href]")
            lineup = [clean_text(x) for x in re.split(r"\s*(?:\+|&|,|\bB2B\b)\s*", title.split("·", 1)[1])] if "·" in title else []
            desc = " ".join(x for x in [("Berlín Club (sesión)." if club else None), (f"Apertura de puertas {doors.group(1)}." if doors else None)] if x) or None
            out.append(event(title=title, date=date, start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type=typ,
                             music=music_tags(title + " " + body[:300]) or (["house", "disco"] if club else []),
                             priceMin=pmin, priceMax=pmax, priceText=(" · ".join(parts) or None), free=free,
                             lineup=[x for x in lineup if x][:8], description=desc,
                             sources=[{"name": NAME, "url": link}], ticketUrl=(tk["href"].strip() if tk else link)))
        if not recent: break
        time.sleep(0.4)
    return out
