"""Maravillas Club (maravillasclub.com, WordPress): wp-json/wp/v2/posts (una petición). Cada concierto es un post cuyo texto empieza por
"Jueves 5 de noviembre de 2026 • Artista • Anticipada 10€ + gastos, taquilla 14€ • Apertura de puertas 21h, concierto 21:30h" con botón
ENTRADAS. El post "Clubbing" describe las sesiones (jueves 23:30–05:30, viernes y sábados 00–06, 15 € con copa en taquilla) y las noches
especiales con fecha ("Sábado 31/10/26 de 00h a 06h Halloween … 20€ con copa … 25€ con copa"): una sesión por jueves/viernes/sábado."""
import re, datetime, html as _html
from scrape.common import get, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Maravillas Club"
MIN_EVENTS = 4
VENUE = "Maravillas Club"
ADDRESS = "C/ San Vicente Ferrer 33, 28004 Madrid"
ZONE = "Malasaña / Chueca"
API = "https://www.maravillasclub.com/wp-json/wp/v2/posts?per_page=60"
WD = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "sabados": 5, "domingo": 6}

def _txt(h):
    h = re.sub(r"<(?:/p|br|/h\d|/div|/li)[^>]*>", "\n", h)
    return [clean_text(x) for x in _html.unescape(re.sub(r"<[^>]+>", " ", h)).split("\n") if clean_text(x)]

def _hm(h, m):
    return f"{int(h):02d}:{int(m or 0):02d}" if int(h) < 24 else None

def _club(post, today, end):
    lines = _txt(post["content"]["rendered"])
    url = post["link"]
    weekly, special = {}, {}
    for i, l in enumerate(lines):
        pl = plain(l)
        m = re.match(r"^(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)\w*\s+(\d{1,2})/(\d{1,2})/(\d{2,4})\s+de\s+(\d{1,2})(?::(\d{2}))?h\s+a\s+(\d{1,2})(?::(\d{2}))?h\s*(.*)$", pl)
        if m:
            y = int(m.group(3)); y = y + 2000 if y < 100 else y
            try: d = datetime.date(y, int(m.group(2)), int(m.group(1))).isoformat()
            except ValueError: continue
            block = " ".join(lines[i:i + 6])
            special[d] = dict(title=(clean_text(re.sub(r"^.*?\d{1,2}(?::\d{2})?h\s+a\s+\d{1,2}(?::\d{2})?h\s*", "", l)) or "Clubbing"),
                              start=_hm(m.group(4), m.group(5)), end=_hm(m.group(6), m.group(7)), block=block)
            continue
        m = re.match(r"^(jueves|viernes|sabados?)\s+de\s+(\d{1,2})(?::(\d{2}))?h\s+a\s+(\d{1,2})(?::(\d{2}))?h", pl)
        if m:
            block = " ".join(lines[i:i + 8])
            weekly[WD[m.group(1)]] = dict(start=_hm(m.group(2), m.group(3)), end=_hm(m.group(4), m.group(5)), block=block)
    out = []
    def mk(date, title, start, endt, block):
        nums = euro_nums(re.split(r"\*\*", block)[0])
        pmin = min(nums) if nums else None
        pmax = max(nums) if nums and max(nums) > pmin else None
        pt = "; ".join(x for x in re.findall(r"(?:De [^€]{3,30}?)?\d+\s*€ con copa", block))[:120] or None
        lu = re.search(r"(?:Dj Set:|Drags:)\s*([^•]+?)(?:Entrada|$)", block)
        return event(title=f"{title} · Maravillas Club" if title.lower() == "clubbing" else f"Clubbing: {title}", date=date, start=start, end=endt,
                     venue=VENUE, address=ADDRESS, zone=ZONE, type="club", music=music_tags(block) or ["pop"], priceMin=pmin, priceMax=pmax,
                     priceText=pt, description="Clubbing LGTBIQ+ con DJs y drags. Entradas solo en taquilla.", sources=[{"name": NAME, "url": url}], ticketUrl=url)
    d0, d1 = datetime.date.fromisoformat(today), datetime.date.fromisoformat(end)
    while d0 <= d1:
        ds = d0.isoformat()
        if ds in special:
            s = special[ds]; out.append(mk(ds, s["title"], s["start"], s["end"], s["block"]))
        elif d0.weekday() in weekly:
            w = weekly[d0.weekday()]; out.append(mk(ds, "Clubbing", w["start"], w["end"], w["block"]))
        d0 += datetime.timedelta(days=1)
    return out

def scrape(today, end):
    try: posts = get(API, json_=True)
    except Exception as ex: log(NAME, "wp-json", ex); return []
    out = []
    for p in posts:
        if p.get("slug") == "clubbing-en-maravillas" or plain(_html.unescape(p["title"]["rendered"])) == "clubbing":
            out += _club(p, today, end); continue
        lines = _txt(p["content"]["rendered"])
        head = " ".join(lines[:4])
        m = re.search(r"(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)\s+(\d{1,2})\s+de\s+([a-z]+)\s+(?:de\s+)?(\d{4})", plain(head))
        if not m or m.group(2) not in MONTHS: continue
        try: date = datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
        except ValueError: continue
        title = clean_text(_html.unescape(p["title"]["rendered"]))
        ph = plain(head)
        cm = re.search(r"conciertos?\s+(\d{1,2})(?::(\d{2}))?h", ph) or re.search(r"\bde\s+(\d{1,2})(?::(\d{2}))?h\s+a\s+\d", ph) or re.search(r"apertura de puertas\s+(\d{1,2})(?::(\d{2}))?h", ph)
        start = _hm(cm.group(1), cm.group(2)) if cm else None
        em = re.search(r"\bde\s+\d{1,2}(?::\d{2})?h\s+a\s+(\d{1,2})(?::(\d{2}))?h", ph)
        date = night_date(date, start)
        if not in_window(date, today, end): continue
        typ = "tardeo" if "tardeo" in plain(title) or (start and start < "20:00" and re.search(r"\bdjs?\b|fiesta", ph)) else "concierto"
        if typ == "concierto" and (not start or start < "20:00"): continue
        if excluded_title(title): continue
        pline = next((l for l in lines[:6] if re.search(r"€|gratuit|gratis|invitaci", l, re.I)), "")
        nums = euro_nums(pline)
        free = bool(re.search(r"gratuit|gratis", plain(pline)))
        pmin = 0 if free else (min(nums) if nums else None)
        pmax = max(nums) if nums and pmin is not None and max(nums) > pmin else None
        tk = re.search(r'href="(https?://(?!www\.maravillasclub)[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*(?:ENTRADAS|INVITACIONES)', p["content"]["rendered"])
        body = " ".join(lines[4:])
        out.append(event(title=title, date=date, start=start, end=(_hm(em.group(1), em.group(2)) if em else None), venue=VENUE, address=ADDRESS, zone=ZONE,
                         type=typ, music=music_tags(title + " " + body[:300]) or ["indie", "pop"], priceMin=pmin, priceMax=pmax,
                         priceText=(pline[:120] or None) if (nums or free) else None, free=free, description=(body[:400] or None),
                         status=("agotado" if re.search(r"agotad", ph) else "desconocido"),
                         sources=[{"name": NAME, "url": p["link"]}], ticketUrl=(tk.group(1) if tk else p["link"])))
    return out
