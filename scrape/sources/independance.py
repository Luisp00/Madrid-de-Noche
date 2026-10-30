"""Independance Club (independanceclub.com, Shopify): colecciones conciertos / sesiones ("NOCHES") / tardeos vía products.json.
El título trae fecha y horario ("KPOP PARTY - VIERNES 06 NOVIEMBRE DE 23:30H A 06H", "TORO - VIERNES 06 NOVIEMBRE A LAS 20H");
las variantes son los tramos de entrada con precio (gastos incluidos) y disponibilidad ("ENTRADA GRATIS - Agotadas")."""
import re, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, infer_year, MONTHS, log
from scrape.sources._filtros import excluded_title

NAME = "Independance Club"
MIN_EVENTS = 3
VENUE = "Independance Club"
ADDRESS = "C/ Atocha 127, 28012 Madrid"
ZONE = "Atocha"
BASE = "https://independanceclub.com"
COLLS = [("sesiones", "club"), ("tardeos", "tardeo"), ("conciertos", "concierto")]
WD = r"(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
TAGMUS = {"80": "remember", "90": "remember", "2000": "remember", "techno": "techno", "pop": "pop", "kpop": "pop", "rock": "rock", "indie": "indie",
          "punk": "rock", "heavy metal": "rock", "urbana": "urban"}

def _hm(h, m):
    h, m = int(h), int(m or 0)
    return f"{h:02d}:{m:02d}" if h < 24 and m < 60 else None

def _parse_title(raw, today):
    p = plain(raw)
    m = re.search(r"\b" + WD + r"\s+(\d{1,2})\s+(?:de\s+)?([a-z]+)", p)
    if not m or m.group(2) not in MONTHS: return None
    day, mon = int(m.group(1)), MONTHS[m.group(2)]
    try: date = datetime.date(infer_year(mon, day, today), mon, day).isoformat()
    except ValueError: return None
    rest = p[m.end():]
    start = endt = None
    r = re.search(r"\bde\s+(\d{1,2})(?:[:.](\d{2}))?\s*h?\s*(?:a\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*h", rest)
    if r: start, endt = _hm(r.group(1), r.group(2)), _hm(r.group(3), r.group(4))
    else:
        r = re.search(r"\ba las\s+(\d{1,2})(?:[:.](\d{2}))?\s*h", rest)
        if r: start = _hm(r.group(1), r.group(2))
    # título sin la parte de fecha: "KPOP PARTY - VIERNES 06…" -> "KPOP PARTY"
    cut = re.search(r"\s*[-–]\s*(?=" + WD + r"\b)", plain(raw))
    title = clean_text(raw[:cut.start()]) if cut else clean_text(raw)
    return title, date, start, endt

def _prices(variants):
    vs = [v for v in variants if not re.search(r"reservado|\bmesa|botella \(", plain(v.get("title")))]
    avail = [v for v in vs if v.get("available")]
    use = avail or vs
    nums = []
    for v in use:
        try: nums.append(float(v.get("price") or 0))
        except ValueError: pass
    nums = [int(n) if n == int(n) else round(n, 2) for n in nums]
    if not nums: return None, None, False, None, ("agotado" if vs and not avail else "desconocido")
    pmin, pmax = min(nums), max(nums)
    free = pmin == 0
    def lab(v):
        n = clean_text(re.sub(r"\s*[-–(]\s*(quedan.*|agotad.*)$", "", v["title"], flags=re.I)).capitalize()
        pr = v["price"].replace(".00", "")
        return n if pr in ("0", "0.0") else f"{n} {pr} €"
    txt = " · ".join(lab(v) for v in use)
    few = lambda v: re.search(r"quedan pocas|ultimas", plain(v["title"])) or (lambda m: m and int(m.group(1)) <= 20)(re.search(r"quedan (\d+)", plain(v["title"])))
    status = "agotado" if not avail else ("ultimas" if all(few(v) for v in avail) else "disponible")
    return pmin, (pmax if pmax > pmin else None), free, (txt[:117] + "…" if len(txt) > 120 else txt), status

def scrape(today, end):
    out, seen = [], set()
    for coll, typ in COLLS:
        try: prods = get(f"{BASE}/collections/{coll}/products.json?limit=250", json_=True).get("products", [])
        except Exception as ex: log(NAME, coll, ex); continue
        for p in prods:
            if p["handle"] in seen: continue
            seen.add(p["handle"])
            pt = _parse_title(clean_text(p.get("title")), today)
            if not pt: continue
            title, date, start, endt = pt
            date = night_date(date, start)
            if not in_window(date, today, end): continue
            tags = [plain(t) for t in p.get("tags") or []]
            body = clean_text(soup(p.get("body_html") or "").get_text(" "))
            if excluded_title(title) or "tributo" in tags or "homenaje" in plain(title): continue
            t = typ
            if t == "concierto" and (not start or start < "20:00"): continue
            if t == "club" and start and "14:00" <= start < "21:00": t = "tardeo"
            pmin, pmax, free, ptxt, status = _prices(p.get("variants") or [])
            mus = [TAGMUS[x] for x in tags if x in TAGMUS]
            mus = list(dict.fromkeys(mus + music_tags(title))) or (music_tags(body[:400]) if t != "concierto" else []) or (["comercial", "rock"] if t != "concierto" else [])
            lu = re.search(r"line ?up:?\s*(.{3,120}?)(?:\s{2,}|será|$)", body, re.I)
            lineup = [clean_text(x) for x in re.split(r"\s*(?:&|,|\+|\by\b)\s*", lu.group(1)) if clean_text(x)] if lu else []
            url = f"{BASE}/products/{p['handle']}"
            out.append(event(title=title, date=date, start=start, end=endt, venue=VENUE, address=ADDRESS, zone=ZONE, type=t, music=mus,
                             priceMin=pmin, priceMax=pmax, priceText=ptxt, free=free, lineup=lineup[:8], description=(body[:400] or None),
                             status=status, sources=[{"name": NAME, "url": url}], ticketUrl=url))
    return out
