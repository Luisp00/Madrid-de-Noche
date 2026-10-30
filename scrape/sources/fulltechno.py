"""Fulltechno (fulltechno.club): listado WooCommerce paginado con fecha/estilo en las clases CSS; ficha con JSON-LD y bloque 'Información práctica'."""
import re, time
from scrape.common import get, soup, ld_json, event, parse_time, in_window, music_tags, clean_text, night_date, log

NAME = "Fulltechno"
MIN_EVENTS = 20
LIST_URL = "https://fulltechno.club/poblacion/madrid/"
MAX_PAGES = 30
MAX_DETAIL = 200          # el listado de 14 días ronda las 180 fichas (WordPress, sin límite de la web)
NOT_MADRID = re.compile(r"barcelona|valencia|sevilla|bilbao|malaga|málaga|ibiza|l'illa diagonal", re.I)

def _price(raw):
    """'17' / '1€/13€/15€' / '48 - 75€' / '€15' / '16.0' / 'desde 10 €' -> (min, max, texto)."""
    if not raw: return None, None, None
    raw = clean_text(raw)
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d{1,2})?", raw)]
    if not nums: return None, None, None
    nums = [int(n) if n == int(n) else n for n in nums]
    lo, hi = min(nums), max(nums)
    if re.search(r"desde|from", raw, re.I) or len(nums) == 1: hi = None
    txt = raw if "€" in raw else raw + " €"
    return lo, (hi if hi != lo else None), txt[:120]

def _info(txt):
    """Bloque 'Información práctica' de la ficha."""
    i = txt.find("Información práctica")
    # solo la plantilla con "Fecha: noche del ..." es la ficha propia; la otra repite el bloque de un evento relacionado
    if i < 0 or not re.match(r"Información práctica Fecha: noche del", txt[i:i + 60]): return {}
    b = txt[i:i + 700]
    out = {}
    m = re.search(r"Horario:\s*de\s*(\d{1,2}:\d{2})\s*a\s*(\d{1,2}:\d{2})", b)
    if m: out["start"], out["end"] = m.group(1).zfill(5), m.group(2).zfill(5)
    m = re.search(r"Lugar:\s*(.*?)(?=\s+Precio:|\s+Madrid Radio Taxi|$)", b)
    if m:
        v = m.group(1).strip().rstrip(".").strip()
        if v and len(v) <= 160 and not re.match(r"\d{1,2} de ", v): out["lugar"] = v
    m = re.search(r"Precio:\s*([^\n]*?)\.(?:\s|$)", b)
    if m and re.search(r"\d", m.group(1)) and len(m.group(1)) <= 40: out["precio"] = m.group(1)
    return out

def _split_lugar(v):
    """'Madreams, Av. de Pedro Diez, 28, ..., 28019 Madrid, Madrid' -> (sala, dirección|None)."""
    parts = [p.strip() for p in v.split(",") if p.strip()]
    if not parts: return None, None
    parts = [p for p in parts if p.lower() not in ("spain", "españa")]
    while len(parts) > 1 and parts[-1].lower() == "madrid" and (len(parts) < 3 or parts[-2].lower().endswith("madrid") or True): parts.pop(); break
    name = parts[0]
    addr = ", ".join(parts[1:]) or None
    if addr and not re.search(r"\d|calle|c/|av|paseo|plaza|pza|ronda|travesía|glorieta", addr, re.I): addr = None
    return name, (addr + (", Madrid" if addr and "madrid" not in addr.lower() else "")) if addr else None

def scrape(today, end):
    cards, seen = [], set()
    for p in range(1, MAX_PAGES + 1):
        url = LIST_URL + (f"page/{p}/" if p > 1 else "")
        try: html = get(url)
        except Exception as ex: log(NAME, "listado", url, ex); break
        s = soup(html); lis = s.select("li.product")
        if not lis: break
        last = None
        for li in lis:
            m = re.search(r"ftc-fecha-(\d{4})(\d{2})(\d{2})", " ".join(li.get("class", [])))
            a = li.select_one("a[href*='/evento/']")
            if not m or not a: continue
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"; last = date
            href = a["href"].split("?")[0]
            if href in seen or not in_window(date, today, end): continue
            seen.add(href)
            loc = li.select_one(".ftc-card-location span")
            cards.append({"url": href, "date": date, "styles": re.findall(r"ftc-est-([a-z-]+)", " ".join(li.get("class", []))),
                          "title": clean_text((li.select_one(".ftc-card-title, .woocommerce-loop-product__title, h3") or a).get_text()),
                          "loc": clean_text(loc.get_text()) if loc else None})
        if last and last > end: break
    out, dedup = [], set()
    for c in cards[:MAX_DETAIL]:
        try:
            ev = detail(c, today, end)
        except Exception as ex:
            log(NAME, "detalle", c["url"], ex); ev = None
        if ev:
            k = (ev["title"].lower(), ev["date"], ev["venue"].lower())
            if k in dedup: continue
            dedup.add(k); out.append(ev)
        time.sleep(0.4)
    return out

def detail(c, today, end):
    url, date, title = c["url"], c["date"], c["title"]
    html = get(url)
    s = soup(html)
    txt = clean_text(s.get_text(" "))
    start = endt = None; lineup = []; desc = None
    for d in ld_json(html):
        if d.get("@type") in ("Event", "MusicEvent"):
            sd = d.get("startDate") or ""
            if "T" in sd and not sd.endswith("T00:00:00+01:00") and not sd.endswith("T00:00:00+02:00"): start = sd.split("T")[1][:5]
            ed = d.get("endDate") or ""
            if "T" in ed: endt = ed.split("T")[1][:5]
            perf = d.get("performer") or []
            perf = perf if isinstance(perf, list) else [perf]
            lineup = [p.get("name") for p in perf if isinstance(p, dict) and p.get("name")]
            desc = clean_text(d.get("description") or "").rstrip("…").strip() or None
    info = _info(txt)
    # el horario del texto manda (el JSON-LD pone 00:00 cuando no sabe la hora)
    if info.get("start"): start, endt = info["start"], info.get("end") or endt
    m = None
    if not start:
        m = re.search(r"(?:a partir de las|desde las|empieza a las|lugar de|horario de)\s*(\d{1,2}[:.]\d{2})(?:\s*(?:hasta las|a las|hasta|a)\s*(\d{1,2}[:.]\d{2}))?", txt)
        if m: start, endt = parse_time(m.group(1).replace(".", ":")), parse_time((m.group(2) or "").replace(".", ":")) or endt
    # sala y ciudad: migas "TÍTULO / fecha / Sala, Ciudad"
    crumb = None
    for d in ld_json(html):
        if d.get("@type") == "BreadcrumbList":
            items = d.get("itemListElement") or []
            if items: crumb = (items[-1].get("name") or "")
    cvenue = ccity = None
    if crumb and crumb.count(" / ") >= 2:
        last = crumb.split(" / ")[-1].strip()
        if "," in last: cvenue, ccity = [x.strip() for x in last.rsplit(",", 1)]
        else: ccity = last
    if ccity and not re.match(r"madrid", ccity, re.I): return None            # evento de otra ciudad colado en el listado
    venue = address = None
    if info.get("lugar"):
        if NOT_MADRID.search(info["lugar"]): return None
        venue, address = _split_lugar(info["lugar"])
    if not venue and cvenue and cvenue.lower() != "madrid": venue = cvenue
    if not venue and c["loc"]:
        v = re.sub(r"\s*·\s*Madrid$", "", c["loc"]).strip()
        if v and v.lower() != "madrid" and not v.lower().startswith("powered") and not re.match(r"\d{1,2} de ", v): venue = v
    if not venue:
        m = re.search(r"\b(?:llega a|se celebra en|se celebrará en|tendrá lugar en|en)\s+((?:Sala|Club|Teatro)\s+[A-ZÁÉÍÓÚÑ][\w'ÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\w'ÁÉÍÓÚÑáéíóúñ]+)?|[A-ZÁÉÍÓÚÑ][\w'ÁÉÍÓÚÑáéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][\w'ÁÉÍÓÚÑáéíóúñ]+)?)\s*(?:,|\.|\s+(?:la|el|en|con))", txt)
        if m: venue = m.group(1)
    if not venue:
        m = re.search(r"\s@\s*([^|]+?)\s*$", title) or re.search(r"\s[-–]\s*([^-–|]+?)\s*$", title)
        if m: venue = clean_text(m.group(1))
    if venue: venue = re.sub(r"^(?:TBA|TBC)\s*[–-]\s*", "", venue).strip()
    if not venue or venue.lower() in ("madrid", "por anunciar", "tba", "tbc") or venue.lower().startswith("powered by"): return None
    if NOT_MADRID.search(venue) or (address and NOT_MADRID.search(address)): return None
    if not address:
        m = re.search(r"Puedes encontrar .{1,60}? en ([^.]{8,120}?)\.\s+Su capacidad", txt)
        if m: address = clean_text(m.group(1))
    if address and "madrid" not in address.lower(): address += ", Madrid"
    # precio
    pmin, pmax, ptxt = _price(info.get("precio"))
    if pmin is None:
        for d in ld_json(html):
            o = d.get("offers") if d.get("@type") in ("Event", "MusicEvent") else None
            if isinstance(o, dict) and o.get("price") not in (None, ""): pmin, pmax, ptxt = _price(str(o["price"]))
    if pmin is None:
        pe = s.select_one(".summary .price, p.price")
        if pe: pmin, pmax, ptxt = _price(pe.get_text(" "))
    # fecha de noche
    ndate = night_date(date, start) if start else date
    # sesiones de tarde/concierto breve (antes de las 20:00 y acabando pronto): no son ocio nocturno
    if start and "06:00" <= start < "20:00" and endt and "06:00" <= endt <= "23:00": return None
    title = re.sub(r"\s+en Madrid$", "", title, flags=re.I)
    styles = c["styles"]
    music = [t for t in ("hardtechno" if "hard" in "".join(styles) or "industrial" in styles else "", "techno" if "techno" in styles or "minimal" in styles else "",
                         "house" if "house" in styles or "tech-house" in styles else "", "electronica" if "electronica" in styles else "") if t]
    music = music or music_tags(title + " " + (desc or "")) or ["techno"]
    typ = "tardeo" if start and "12:00" <= start < "20:00" else "club"
    return event(title=title, date=ndate, start=start, end=endt, venue=venue, address=address, type=typ, music=music,
                 priceMin=pmin, priceMax=pmax, priceText=ptxt, lineup=lineup[:12], description=(desc[:400] if desc else None),
                 sources=[{"name": NAME, "url": url}], ticketUrl=url)
