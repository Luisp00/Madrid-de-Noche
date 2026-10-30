"""esMadrid (esmadrid.com, turismo oficial): /agenda-musica-madrid lista ~27 conciertos/festivales destacados; la ficha trae Cuándo, Dónde, Dirección, Precio, Horarios y Tipo
(el JSON-LD solo trae fecha sin hora). Un evento por fecha suelta dentro de la ventana; los ciclos/festivales con rango de fechas ("2 oct a 30 nov") se descartan."""
import re, time, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, MONTHS, music_tags, log
from scrape.sources._filtros import excluded_venue, excluded_title, euro_nums

NAME = "esMadrid"
MIN_EVENTS = 3
BASE = "https://www.esmadrid.com"
LIST_URL = BASE + "/agenda-musica-madrid"
LABELS = {"Cuándo", "Dónde", "Dirección", "Zona turística", "Teléfono", "Fax", "Web", "Correo electrónico", "Metro", "Autobús", "Cercanías",
          "Alquiler de bicis (BiciMAD)", "Precio", "Horarios", "Tipo"}
BAD_TYPE = re.compile(r"cl[aá]sica|[oó]pera|flamenco|zarzuela|teatro|danza|musical|infantil|ni[nñ]os|comedia", re.I)
TYPE_MUSIC = [("hardtechno", r"hard ?techno"), ("techno", r"techno"), ("house", r"house"), ("electronica", r"electr[oó]nic"), ("pop", r"pop-rock|\bpop\b"),
              ("rock", r"rock|metal|punk"), ("latino", r"latin"), ("urban", r"urban"), ("hiphop", r"hip ?hop|\brap\b"), ("reggaeton", r"reggaet"),
              ("indie", r"indie"), ("rnb", r"r&b|soul|blues"), ("disco", r"funk|disco")]


def fields(html):
    s = soup(html)
    lines = [clean_text(x) for x in s.get_text("\n").split("\n") if clean_text(x)]
    try: i = lines.index("Cuándo")
    except ValueError: return None, lines
    out, cur = {}, None
    for ln in lines[i:i + 80]:
        if ln in LABELS:
            cur = ln; out[cur] = []
            if cur == "Tipo": pass
        elif cur:
            out[cur].append(ln)
            if cur == "Tipo": break
    return out, lines


def parse_dates(txt, today):
    """'27, 28, 30 y 31 de octubre' / '7 nov y 5 dic' -> lista de fechas ISO; None si es un rango ('2 oct a 30 nov') o no se entiende."""
    p = plain(txt)
    if re.search(r"\d\s*(?:de\s+)?[a-z]*\s+a\s+\d", p) or " al " in p or "hasta" in p: return None
    toks = re.findall(r"\d{1,2}|[a-z]{3,10}", p)
    dates, nums = [], []
    for t in toks:
        if t.isdigit(): nums.append(int(t))
        elif t in MONTHS and nums:
            mo = MONTHS[t]
            for d in nums:
                y = datetime.date.fromisoformat(today).year
                try: dt = datetime.date(y, mo, d)
                except ValueError: continue
                if dt < datetime.date.fromisoformat(today) - datetime.timedelta(days=60): dt = datetime.date(y + 1, mo, d)
                dates.append(dt.isoformat())
            nums = []
    return dates or None


def scrape(today, end):
    try: lst = get(LIST_URL)
    except Exception as ex:
        log(NAME, "listado", ex); return []
    links, hint = [], {}
    ls = soup(lst)
    for a in ls.select("a[href^='/agenda/'], a[href*='esmadrid.com/agenda/']"):
        u = a["href"] if a["href"].startswith("http") else BASE + a["href"]
        u = u.split("?")[0].split("#")[0]
        if u.rstrip("/").endswith("/agenda/busqueda") or u in links: continue
        links.append(u)
        box = a.find_parent(class_="node-event")
        m = re.search(r"\(([^()]+?)\.\s*[^().]*\)\s*\.?\s*$", clean_text(box.get_text(" ")) if box else "")
        if m: hint[u] = clean_text(m.group(1))
    log(NAME, "fichas:", len(links))
    out = []
    for u in links[:60]:
        try: html = get(u)
        except Exception as ex:
            log(NAME, "ficha", u, ex); continue
        time.sleep(0.4)
        f, _ = fields(html)
        if not f: continue
        title = clean_text((soup(html).select_one("h1") or soup(html).title).get_text()).replace("| Turismo Madrid", "").strip()
        venue = clean_text(" ".join(f.get("Dónde", [])))
        tipo = ", ".join(f.get("Tipo", []))
        if venue in ("--", "") and hint.get(u): venue = hint[u]
        if not venue or venue == "--" or "varios" in plain(venue) or "sede principal" in plain(venue): continue
        if excluded_venue(venue) or excluded_title(title) or BAD_TYPE.search(tipo): continue
        dates = parse_dates(" ".join(f.get("Cuándo", [])), today)
        if not dates: continue
        dates = [d for d in dates if in_window(d, today, end)]
        if not dates: continue
        times = re.findall(r"(\d{1,2})[:.](\d{2})", " ".join(f.get("Horarios", [])))
        start = f"{int(times[0][0]):02d}:{times[0][1]}" if times else None
        endt = f"{int(times[1][0]):02d}:{times[1][1]}" if len(times) > 1 else None
        electronic = bool(re.search(r"electr[oó]nic|techno|house", plain(tipo + " " + title)))
        if not start or (start < "20:00" and start >= "06:00" and not electronic): continue
        d = f.get("Dirección", [])
        address = None
        if len(d) >= 2:
            cp = next((x for x in d if re.fullmatch(r"\d{5}", x)), None)
            address = re.sub(r"\s+,", ",", clean_text(f"{d[0]} {d[1]}")) + (f", {cp} Madrid" if cp else ", Madrid")
        web = next((x for x in f.get("Web", []) if x.startswith("http")), None)
        desc = None
        # precio: líneas del bloque Precio; las que citan otras fechas ("27 y 28 octubre: entradas agotadas") solo valen para esas fechas
        ptxt_all = " ".join(f.get("Precio", []))
        for date in dates:
            day = int(date[8:])
            txt = ptxt_all
            m = re.findall(r"((?:\d{1,2}(?:\s*(?:,|y)\s*\d{1,2})*)\s*(?:de\s+)?[a-zé]{3,10})\s*:\s*([^:]*?)(?=(?:\d{1,2}(?:\s*(?:,|y)\s*\d{1,2})*\s*(?:de\s+)?[a-zé]{3,10}\s*:)|$)", txt, re.I)
            if m:
                keep = [body for lab, body in m if day in [int(x) for x in re.findall(r"\d{1,2}", lab)]]
                txt = " ".join(keep)
            nonvip = " ".join(x for x in re.split(r"(?<=€)", txt) if "vip" not in plain(x))
            nums = euro_nums(nonvip)
            pmin = min(nums) if nums else None
            pmax = max(nums) if len(nums) > 1 and max(nums) != min(nums) else None
            if re.search(r"entrada libre|gratuit|gratis", plain(txt)) and not nums: pmin = 0
            ptxt = clean_text(txt)[:120] or None
            if not nums and pmin != 0: ptxt = None  # "A la venta el…", "agotadas": sin precio utilizable
            mus = []
            for tag, rx in TYPE_MUSIC:
                if re.search(rx, plain(tipo)) and tag not in mus: mus.append(tag)
            for t in music_tags(title):
                if t not in mus: mus.append(t)
            ev = event(title=title, date=date, start=start, end=endt, venue=venue, address=address,
                       type="festival" if re.search(r"festival", plain(tipo + " " + title)) else "concierto",
                       music=mus or ["otros"], priceMin=pmin, priceMax=pmax, priceText=ptxt, free=(pmin == 0),
                       description=(f"Tipo: {tipo}." if tipo else None), sources=[{"name": NAME, "url": u}], ticketUrl=web or u)
            out.append(ev)
    return out
