"""Bynova / Nova Nightlife (bynovanightlife.com).

- /en/nightclubs-madrid/ trae TODAS las fiestas fechadas (li.nvn-r agrupadas por noche en div.nvn-g[data-d]) con hora, edad, música,
  precio-desde, "Last tickets"/"Sold out" y enlace Fourvenues -> un objeto por fiesta.
- /en/whats-on/ lista por día de la semana las salas que Nova gestiona cada noche (lista gratis, precio-desde, zona) -> un objeto
  "<Día> en <Sala>" por sala y noche de la ventana que no tenga ya una fiesta nocturna en la agenda (status "desconocido").
- Cada página de club (/en/nightclubs-madrid/<slug>/) aporta dirección, dress code, edad, música y horario por día.
La web responde 429/reto anti-bot a veces: se prueba requests y luego Chromium; si sigue el reto devuelve [].
"""
import re, os, time, datetime
from bs4 import NavigableString, Comment
from scrape.common import get, browser, soup, ld_json, event, music_tags, parse_price, clean_text, plain, in_window, log

NAME = "Bynova"
MIN_EVENTS = 40
BASE = "https://bynovanightlife.com/en/"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
SKIP_SLUGS = {"free-guest-list", "open-tonight", "ya-tengo-plan", "hipodromo-zarzuela", "riviera-padana"} | {f"open-{d}" for d in DAYS}
ALIAS = {"fitz": "Fitz Club", "cristo social": "Cristo Social Club", "mon": "Sala Mon", "copernico": "Sala Copérnico", "green": "Green Social Club",
         "tiffanys": "Tiffany's The Club", "nazca club": "Nazca", "chango": "Changó Club", "chaman": "Chamán", "bonded": "Bonded Club",
         "epoka": "Epoka The Club", "rubicon": "Rubicón", "marabu": "Marabú", "manama": "Manamá", "banoi": "Banoi", "la riviera": "La Riviera"}
PROMOTER = {"ya tengo plan": [(r"pabblo", "Pabblo Club"), (r"green", "Green Social Club")],
            "madrid no descansa": [(r"rubicon", "Rubicón"), (r"las ventas", "Las Ventas"), (r"despecho", "Sala de Despecho")],
            "latidolatino": [(r"ponzano", "Marabú")], "bellaqueolab": [(r"ponzano", "Marabú"), (r".", "Global Club")]}
NOT_NIGHT = re.compile(r"\b(lessons?|clases?|workshops?|karaoke|bingo|tributo|tribute|cancelad[oa]s?|cancell?ed)\b")

def T(el, sep=""):
    """Texto de un elemento. La agenda va dentro de <template>: get_text() de bs4 ignora esas cadenas, así que se recorren a mano."""
    if el is None: return ""
    return clean_text(sep.join(str(x) for x in el.descendants if isinstance(x, NavigableString) and not isinstance(x, Comment)))

_fails = [0]   # páginas de club consecutivas bloqueadas: el reto anti-bot salta al encadenar peticiones; pasado el umbral se omiten (son opcionales)

def fetch(url, tries=3, chromium=True):
    """requests (con reintento si sale el reto anti-bot o 429) y, solo si requests falla del todo, Chromium."""
    last = None
    for i in range(tries):
        try:
            h = get(url, retries=2)
            if "Checking your browser" not in h[:3000]: return h
            last = "reto anti-bot"
            from scrape import common
            try: os.remove(common._cache_path("GET " + url))
            except OSError: pass
        except Exception as ex:
            last = str(ex)[:150]
            if "429" not in last and "HTTP" not in last: break
        time.sleep(4 * (i + 1))
    if not chromium: raise RuntimeError(f"{url}: {last}")
    try:
        h = browser(url, raw=True)
        if "Checking your browser" not in h[:3000]: return h
        last = "reto anti-bot (Chromium)"
    except Exception as ex: last = str(ex)[:150]
    raise RuntimeError(f"{url}: {last}")

def canon(name):
    name = clean_text(name).replace("’", "'")
    return ALIAS.get(plain(name)) or ALIAS.get(plain(name).replace("'", "")) or name

def club_info(slug, cache={}):
    if slug in cache: return cache[slug]
    info = {"address": None, "dress": None, "age": None, "music": [], "hours": {}, "entry": {}, "list": {}}
    if _fails[0] >= 3: cache[slug] = info; return info
    time.sleep(1.5)
    try:
        h = fetch(f"{BASE}nightclubs-madrid/{slug}/", tries=2, chromium=False)
        _fails[0] = 0
    except Exception as ex:
        _fails[0] += 1
        log(NAME, "club", slug, ex, "(omitidas las demás páginas de club)" if _fails[0] >= 3 else ""); cache[slug] = info; return info
    s = soup(h)
    for d in s.select("div"):
        sp, st = d.find("span", recursive=False), d.find("strong", recursive=False)
        if sp and st:
            k, v = clean_text(sp.get_text()), clean_text(st.get_text())
            if k == "Dress code": info["dress"] = v
            elif k == "Minimum age":
                m = re.search(r"\d+", v); info["age"] = int(m.group()) if m else None
            elif k == "Music": info["music"] = music_tags(v)
    m = re.search(r"The address is\s*<strong>(.*?)</strong>", h)
    if m: info["address"] = clean_text(re.sub(r"<[^>]+>", "", m.group(1)))
    else:
        for d in ld_json(h):
            ad = d.get("address")
            if isinstance(ad, dict) and ad.get("streetAddress"):
                info["address"] = ", ".join(x for x in [ad.get("streetAddress"), ad.get("postalCode"), ad.get("addressLocality")] if x); break
    for tr in s.select("table.vp-table tbody tr"):
        td = [clean_text(x.get_text()) for x in tr.find_all("td")]
        if len(td) >= 4:
            day = plain(td[0])
            hm = re.search(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", td[1])
            if hm: info["hours"][day] = (hm.group(1).zfill(5), hm.group(2).zfill(5))
            info["list"][day] = td[2] if re.search(r"\d", td[2]) else None
            pm = re.search(r"€\s*(\d+(?:[.,]\d+)?)", td[3])
            if pm: info["entry"][day] = float(pm.group(1).replace(",", "."))
    cache[slug] = info
    return info

def tnorm(t):
    m = re.search(r"(\d{1,2}):(\d{2})", t or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None

def num(x): return int(x) if float(x) == int(float(x)) else x

def scrape(today, end):
    try: agenda = fetch(BASE + "nightclubs-madrid/")
    except Exception as ex:
        log(NAME, "agenda no accesible (reto anti-bot / 429):", ex); return []
    s = soup(agenda)
    out, nightly = [], set()
    clubs_needed = []
    for g in s.select("div.nvn-g[data-d]"):
        date = g["data-d"]
        if not in_window(date, today, end): continue
        for li in g.select("li.nvn-r"):
            a = li.select_one("a.nvn-n"); v = li.select_one(".nvn-v")
            if not a or not v: continue
            vl = v.select_one("a.nvn-vl")
            vname = T(vl) if vl else clean_text(T(v).replace(T(v.select_one("i")), ""))
            slug = None
            if vl:
                m = re.search(r"/nightclubs-madrid/([^/]+)/", vl.get("href", "")); slug = m.group(1) if m else None
            title = T(a)
            for rx, v2 in PROMOTER.get(plain(vname), []):   # marca/promotora -> sala real según el título
                if re.search(rx, plain(title)): vname = v2; break
            if not title or not vname or NOT_NIGHT.search(plain(title)): continue
            tb = li.select_one(".nvn-time")
            start = tnorm(T(tb.select_one("b"))) if tb and tb.select_one("b") else None
            endt = tnorm(T(tb.select_one("span"))) if tb and tb.select_one("span") else None
            age_i = v.select_one("i"); am = re.search(r"\d+", T(age_i)) if age_i else None
            buy = li.select_one(".nvn-buy"); btxt = T(buy, " ") if buy else ""
            pmin = None; free = False; ptxt = None
            pm = re.search(r"€\s*(\d+(?:[.,]\d+)?)", btxt)
            if pm: pmin = num(float(pm.group(1).replace(",", "."))); ptxt = f"desde {pmin} €"
            if re.search(r"free guest list", btxt, re.I): free, pmin, ptxt = True, 0, "Lista gratis"
            status = "agotado" if "is-so" in li.get("class", []) or "Sold out" in btxt else ("ultimas" if "Last tickets" in btxt else ("disponible" if buy and buy.select_one(".nvn-btn") else "desconocido"))
            url = a["href"].split("?")[0]
            gen = li.select_one(".nvn-gen")
            tardeo = bool(start and "06:00" <= start < "20:00") or "afterwork" in plain(title) or "tardeo" in plain(title)
            out.append({"slug": slug, "ev": dict(title=title, date=date, start=start, end=endt, venue=canon(vname), type="tardeo" if tardeo else "club",
                        music=music_tags(T(gen)) if gen else music_tags(title), priceMin=pmin, priceText=ptxt, free=free, ageMin=int(am.group()) if am else None,
                        status=status, sources=[{"name": NAME, "url": url}], ticketUrl=url)})
            if start and (start >= "21:00" or start < "06:00") and slug: nightly.add((slug, date))
    # Salas por día de la semana (/whats-on/): una sesión por sala y noche sin fiesta nocturna propia
    try: wo = soup(fetch(BASE + "whats-on/"))
    except Exception as ex:
        log(NAME, "whats-on", ex); wo = None
    synth = []
    if wo:
        t0, t1 = datetime.date.fromisoformat(today), datetime.date.fromisoformat(end)
        for sec in wo.select("section.ag-day"):
            if sec.get("id") not in DAYS: continue
            wd = DAYS.index(sec["id"])
            d = t0
            while d <= t1:
                if d.weekday() == wd:
                    for li in sec.select("ul.ag-list li"):
                        a = li.find("a"); sp = li.find("span")  # /whats-on/ no usa template
                        m = re.search(r"/nightclubs-madrid/([^/]+)/", a.get("href", "")) if a else None
                        if not m or m.group(1) in SKIP_SLUGS or (m.group(1), d.isoformat()) in nightly: continue
                        synth.append((m.group(1), clean_text(a.get_text()), clean_text(sp.get_text()) if sp else "", d, wd))
                d += datetime.timedelta(days=1)
    for slug, name, txt, d, wd in synth:
        info = club_info(slug)
        day_en = DAYS[wd]
        toks = [t.strip() for t in txt.split("·")]
        start, endt = info["hours"].get(day_en, (None, None))
        pmin = info["entry"].get(day_en); free = False; lst = None; age = info["age"]; extra_music = []; tardeo = False
        for t in toks:
            tl = t.lower().replace("’", "'")
            m = re.match(r"(?:open bar )?from €(\d+(?:[.,]\d+)?)", tl)
            if m: pmin = float(m.group(1).replace(",", ".")); continue
            m = re.match(r"(?:after-work|afternoon party|from) (?:from )?(\d{1,2}:\d{2})", tl)
            if m:
                start = tnorm(m.group(1)); tardeo = "after" in tl or start < "20:00"; continue
            if re.match(r"\+\d+$", tl): age = int(tl[1:]); continue
            if re.search(r"\blist\b", tl):
                free = True; lst = tnorm(tl); continue
        if free is False and info["list"].get(day_en): free = True; lst = tnorm(info["list"][day_en])
        for t in toks[:-1]:
            if not re.search(r"€|list|\+\d|from \d|after|afternoon", t.lower()): extra_music += music_tags(t)
        parts = []
        if free: parts.append("Lista gratis" + (f" hasta {lst}" if lst else ""))
        if pmin is not None: parts.append(f"entrada desde {num(pmin)} €")
        title = f"{DAYS_ES[wd]} en {canon(name)}"
        out.append({"slug": slug, "ev": dict(title=title, date=d.isoformat(), start=start, end=endt, venue=canon(name), address=info["address"], type="tardeo" if tardeo else "club",
                    music=list(dict.fromkeys(extra_music + info["music"])), priceMin=0 if free else (num(pmin) if pmin is not None else None),
                    priceText=" · ".join(parts)[:120] or None, free=free, dressCode=info["dress"], ageMin=age, status="desconocido",
                    description=(f"Horario habitual según Nova. " + ("Nova gestiona la lista gratuita. " if free else "")).strip(),
                    sources=[{"name": NAME, "url": f"{BASE}nightclubs-madrid/{slug}/"}], ticketUrl=f"{BASE}nightclubs-madrid/{slug}/")})
    # direcciones y dress code para las fiestas fechadas (una página por club, máx. ~60)
    slugs = []
    for o in out:
        if o["slug"] and o["slug"] not in slugs and o["slug"] not in SKIP_SLUGS: slugs.append(o["slug"])
    for o in out:
        sl = o["slug"]
        if sl and sl in slugs[:60]:
            info = club_info(sl)
            ev = o["ev"]
            ev.setdefault("address", None); ev.setdefault("dressCode", None)
            ev["address"] = ev["address"] or info["address"]; ev["dressCode"] = ev["dressCode"] or info["dress"]
            if not ev.get("ageMin"): ev["ageMin"] = info["age"]
            if not ev.get("music"): ev["music"] = info["music"]
    res = [event(**o["ev"]) for o in out]
    log(NAME, len(res), "eventos", f"({len(res) - len(synth)} fechados + {len(synth)} por sala/noche)")
    return res
