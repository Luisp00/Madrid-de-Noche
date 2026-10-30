"""Sala But, Sala Mon y Sala Copérnico (webs propias de cada sala; un módulo, venue correcto en cada evento).
- Sala But (salabut.es, WordPress/Elementor): /agenda-conciertos/ y /agenda-sesiones/ con bloques e-child (título, "5 NOVIEMBRE 2026",
  aviso "CAMBIO DE SALA – X" y botón COMPRAR ENTRADAS). No publica hora ni precio: start/price null. Los conciertos vendidos por
  Ochoymedio se omiten (ochoymedio.py los da con hora y precio). Las sesiones de Mondo Disko las da mondodisko.py.
- Sala Mon (monmadrid.es enlaza a monmadrid-web.vercel.app, HTML servido): /eventos (fecha, título, géneros, descripción con
  "🕚 23:45h – Cierre", enlace Fourvenues) y /entradas ("Desde las 23:59" por noche y "Entradas desde 15 €" genérico).
- Copérnico (conciertoscopernico.com, WordPress): /conciertos-copernico/ enlaza las fichas "<artista>-<día>-de-<mes>/" (el año de
  publicación de WP no es el del concierto: se deduce); el texto de la ficha (wp-json por slug) da a veces "Comienzo 21:00" y la ticketera."""
import re, time, datetime, html as _html
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, MONTHS, infer_year, log
from scrape.sources._filtros import excluded_title
from scrape.sources._salas import resolve

NAME = "Grupo Mon"
MIN_EVENTS = 4
BUT = resolve("Sala But")
MON = resolve("Sala Mon")
COP = resolve("Sala Copérnico")
BUT_URL = "https://www.salabut.es"
MON_URL = "https://monmadrid-web.vercel.app"
COP_URL = "https://conciertoscopernico.com"

def _fix(t):
    """Páginas UTF-8 que requests decodifica como Latin-1 ('CopÃ©rnico')."""
    if "Ã" in t:
        try: return t.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError): pass
    return t

def _date(txt, today, year=True):
    m = re.search(r"(\d{1,2})\s+(?:de\s+)?([a-z]+)\.?(?:\s+(?:de\s+)?(\d{4}))?", plain(txt))
    if not m or m.group(2) not in MONTHS: return None
    d, mo = int(m.group(1)), MONTHS[m.group(2)]
    y = int(m.group(3)) if m.group(3) else infer_year(mo, d, today)
    try: return datetime.date(y, mo, d).isoformat()
    except ValueError: return None

def _ev(venue, **kw):
    return event(venue=venue[0], address=venue[1], zone=venue[2], **kw)

# ---------- Sala But ----------
def _but(today, end):
    out = []
    for path, typ in (("/agenda-conciertos/", "concierto"), ("/agenda-sesiones/", "club")):
        url = BUT_URL + path
        try: html = get(url)
        except Exception as ex: log(NAME, "Sala But", path, ex); continue
        for box in soup(html).select(".e-con.e-child"):
            heads = [clean_text(h.get_text(" ")) for h in box.select(".elementor-heading-title")]
            a = box.select_one("a.elementor-button[href]")
            if not heads or not a: continue
            date = next((_date(h, today) for h in heads if re.search(r"\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóú]+\s+\d{4}", h)), None)
            if not date or not in_window(date, today, end): continue
            tk = a["href"].strip()
            if "ochoymedioclub.com" in tk or "mondodisko.es" in tk: continue
            title = next((h for h in heads if not re.search(r"\d{4}$", h) and plain(h) not in ("madrid", "") and not plain(h).startswith("cambio de sala")), None)
            venue = BUT
            moved = next((h for h in heads if plain(h).startswith("cambio de sala")), None)
            if moved:
                i = heads.index(moved)
                dest = re.sub(r"(?i)^cambio de sala\s*[–-]?\s*", "", moved) or (heads[i + 1] if i + 1 < len(heads) else "")
                r = resolve(dest)
                if not r: continue
                venue = r
            if not title:
                host = re.sub(r"^www\.", "", re.match(r"https?://([^/]+)", tk).group(1)) if tk.startswith("http") else ""
                title = {"yassparty.com": "Yass Party", "locobongo.es": "Loco Bongo"}.get(host)
                if not title: continue
            if excluded_title(title) or re.search(r"experiencia|tribut|homenaje", plain(tk + " " + title)): continue
            out.append(_ev(venue, title=title, date=date, type=typ, music=music_tags(title),
                           sources=[{"name": "Sala But", "url": url}], ticketUrl=tk if tk.startswith("http") else url))
    return out

# ---------- Sala Mon ----------
def _mon(today, end):
    starts, generic = {}, None
    try:
        h2 = get(MON_URL + "/entradas")
        t2 = clean_text(soup(h2).get_text(" "))
        g = re.search(r"Entradas desde (\d+)\s*€ con ([^.]{3,40})", t2)
        if g: generic = f"Entradas desde {g.group(1)} € con {g.group(2)} (dato general de la web)"
        for m in re.finditer(r"([A-ZÁÉ]{3}\s+\d{2}\s+[A-Z]{3}\s+\d{4})\s+Desde las\s+(\d{1,2}:\d{2})", t2):
            starts[_date(m.group(1), today)] = m.group(2)
    except Exception as ex: log(NAME, "Sala Mon entradas", ex)
    try: html = get(MON_URL + "/eventos")
    except Exception as ex: log(NAME, "Sala Mon eventos", ex); return []
    out = []
    for h in soup(html).select("h2"):
        card = h.find_parent(class_=re.compile(r"\bgroup\b"))
        if not card: continue
        ps = [clean_text(p.get_text(" ")) for p in card.select("p")]
        dtxt = next((p for p in ps if re.match(r"^[A-ZÁÉ]{3}\s+\d{2}\s+[A-Z]{3}\s+\d{4}$", p)), None)
        date = _date(dtxt, today) if dtxt else None
        if not date or not in_window(date, today, end): continue
        title = clean_text(h.get_text(" "))
        desc = next((p for p in ps if len(p) > 60), "")
        tags = next((p for p in ps if "·" in p and len(p) < 60), "")
        tm = re.search(r"(\d{1,2})[:.](\d{2})\s*h?\s*[–-]", desc)
        start = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else starts.get(date)
        a = card.select_one("a[href*='fourvenues']") or card.select_one("a[href^='http']")
        tk = a["href"] if a else MON_URL + "/eventos"
        typ = "tardeo" if start and "14:00" <= start < "21:00" else "club"
        d2 = re.sub(r"\s*Aviso: las imágenes.*$", "", desc)
        out.append(_ev(MON, title=title, date=date, start=start, type=typ,
                       music=music_tags(tags + " " + title) or ["reggaeton", "comercial"], ageMin=(18 if "+18" in desc else None),
                       description=(" ".join(x for x in [d2[:300], generic] if x) or None)[:400],
                       sources=[{"name": "Sala Mon", "url": MON_URL + "/eventos"}], ticketUrl=tk))
    return out

# ---------- Copérnico ----------
def _cop(today, end):
    try: html = _fix(get(COP_URL + "/conciertos-copernico/"))
    except Exception as ex: log(NAME, "Copérnico", ex); return []
    hi = (datetime.date.fromisoformat(end) + datetime.timedelta(days=1)).isoformat()
    cands = {}
    for href in re.findall(r'href="(https://conciertoscopernico\.com/([a-z0-9-]+?)-(\d{1,2})-de-([a-z]+)/)"', html):
        url, slug, d, mon = href
        if mon not in MONTHS or url in cands: continue
        try: date = datetime.date(infer_year(MONTHS[mon], int(d), today), MONTHS[mon], int(d)).isoformat()
        except ValueError: continue
        if today <= date <= hi: cands[url] = date
    if not cands: return []
    slugs = ",".join(u.rstrip("/").rsplit("/", 1)[1] for u in cands)
    posts = {}
    try:
        for p in get(COP_URL + "/wp-json/wp/v2/posts", params={"slug": slugs, "per_page": 50}, json_=True):
            posts[p.get("link")] = p
    except Exception as ex: log(NAME, "Copérnico wp-json", ex)
    out = []
    for url, date in cands.items():
        p = posts.get(url) or {}
        title = clean_text(_html.unescape((p.get("title") or {}).get("rendered") or ""))
        title = clean_text(re.sub(r"\s*[–-]\s*\d{1,2}\s+de\s+\w+\s*$", "", title)) or url.rstrip("/").rsplit("/", 1)[1].replace("-", " ").upper()
        content = (p.get("content") or {}).get("rendered") or ""
        text = clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", content)))
        if excluded_title(title) or re.search(r"\btributo\b|\bhomenaje\b|tribute", plain(text[:300])): continue
        m = re.search(r"(?:comienzo|inicio|hora|concierto)[^0-9]{0,12}(\d{1,2})[:.](\d{2})", text, re.I)
        start = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
        if start and start < "20:00": continue
        if not in_window(date, today, end): continue
        links = [l for l in re.findall(r'href="(https?://[^"]+)"', content) if "conciertoscopernico.com" not in l]
        links += [l for l in re.findall(r"(https?://\S+)", text) if "conciertoscopernico.com" not in l]
        out.append(_ev(COP, title=title, date=date, start=start, type="concierto", music=[t for t in music_tags(title + " " + text[:400]) if t not in ("house", "techno", "electronica")],
                       description=(text[:400] or None), sources=[{"name": "Sala Copérnico", "url": url}],
                       ticketUrl=(links[0].rstrip(".,)") if links else url)))
    return out

def scrape(today, end):
    out = []
    for f in (_but, _mon, _cop):
        try: out += f(today, end)
        except Exception as ex: log(NAME, f.__name__, ex)
    return out
