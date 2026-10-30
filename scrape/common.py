"""Utilidades comunes de los parsers (scrape/sources/*.py).

Cada parser expone:
    NAME = "Fuente"            # nombre corto de la fuente tal como aparece en SPEC.md / la app
    MIN_EVENTS = 10            # por debajo de esto, la fuente se considera fallida (→ agente de respaldo)
    def scrape(today: str, end: str) -> list[dict]     # eventos con el esquema de SPEC.md

Acceso a la red: get(url) hace la petición con requests (proxy del entorno, reintentos, caché en disco);
browser(url) usa Chromium headless vía tools/fetch.js para webs con JavaScript o protección anti-bot.
"""
import os, re, json, time, hashlib, subprocess, datetime, unicodedata, sys
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("MDN_CACHE", os.path.join(ROOT, "run", "cache"))
CACHE_TTL = int(os.environ.get("MDN_CACHE_TTL", "3600"))   # segundos; 0 = sin caché
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_session = None

def log(*a):
    print(*a, file=sys.stderr, flush=True)

def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8", "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})
        ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
        if os.path.exists(ca): _session.verify = ca
    return _session

def _cache_path(key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest()[:24])

def _cached(key):
    p = _cache_path(key)
    if CACHE_TTL and os.path.exists(p) and time.time() - os.path.getmtime(p) < CACHE_TTL:
        return open(p, encoding="utf-8").read()
    return None

def _store(key, text):
    try: open(_cache_path(key), "w", encoding="utf-8").write(text)
    except Exception: pass

class FetchError(Exception): pass

def get(url, *, params=None, headers=None, timeout=30, retries=3, json_=False, ok_codes=(200,)):
    """GET con reintentos y caché. Devuelve texto (o dict/list si json_=True). Lanza FetchError."""
    key = "GET " + url + (json.dumps(params, sort_keys=True) if params else "")
    txt = _cached(key)
    if txt is None:
        last = None
        for i in range(retries):
            try:
                r = session().get(url, params=params, headers=headers, timeout=timeout)
                if r.status_code in ok_codes:
                    txt = r.text; _store(key, txt); break
                last = f"HTTP {r.status_code}"
                if r.status_code in (403, 404, 410): break
            except requests.RequestException as ex:
                last = str(ex)[:200]
            time.sleep(1.5 * (i + 1))
        if txt is None: raise FetchError(f"{url}: {last}")
    return json.loads(txt) if json_ else txt

def browser(url, *, raw=False, wait=2500, max_chars=400000, links=0, mobile=False, timeout=90):
    """Descarga con Chromium headless (tools/fetch.js). raw=True devuelve el HTML/JSON tal cual."""
    key = f"BROWSER{' RAW' if raw else ''} {url}"
    txt = _cached(key)
    if txt is None:
        cmd = ["node", os.path.join(ROOT, "tools", "fetch.js"), url, "--wait", str(wait), "--max", str(max_chars), "--links", str(links)]
        if raw: cmd.append("--raw")
        if mobile: cmd.append("--mobile")
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise FetchError(f"{url}: timeout navegador")
        txt = out.stdout
        if not txt or txt.startswith("ERROR:"): raise FetchError(f"{url}: {txt[:200] or out.stderr[:200]}")
        _store(key, txt)
    return txt

def soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml")

def ld_json(html):
    """Bloques <script type=application/ld+json> parseados (lista de dicts, aplanando @graph)."""
    out = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        items = d if isinstance(d, list) else [d]
        for it in items:
            if isinstance(it, dict) and "@graph" in it: out.extend(x for x in it["@graph"] if isinstance(x, dict))
            elif isinstance(it, dict): out.append(it)
    return out

# ---------- texto / fechas ----------
MONTHS = {"ene":1,"enero":1,"feb":2,"febrero":2,"mar":3,"marzo":3,"abr":4,"abril":4,"may":5,"mayo":5,"jun":6,"junio":6,"jul":7,"julio":7,"ago":8,"agosto":8,
          "sep":9,"sept":9,"septiembre":9,"setiembre":9,"oct":10,"octubre":10,"nov":11,"noviembre":11,"dic":12,"diciembre":12,
          "jan":1,"january":1,"february":2,"march":3,"april":4,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12,"dec":12}

def plain(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()).strip().lower()

def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()

def infer_year(month, day, today):
    """Año para una fecha sin año: la próxima ocurrencia a partir de (hoy - 30 días)."""
    t = datetime.date.fromisoformat(today)
    for y in (t.year, t.year + 1):
        try:
            d = datetime.date(y, month, day)
        except ValueError:
            continue
        if d >= t - datetime.timedelta(days=30): return y
    return t.year + 1

def parse_date(s, today):
    """'31 oct', '31/10/2026', '2026-10-31', 'sáb 31 oct 2026', 'October 31' -> 'YYYY-MM-DD' o None."""
    if not s: return None
    p = plain(s)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", p)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", p)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        y = int(y) if y else infer_year(mo, d, today)
        if y < 100: y += 2000
        try: return datetime.date(y, mo, d).isoformat()
        except ValueError: return None
    m = re.search(r"\b(\d{1,2})\s*(?:de\s+)?([a-z]{3,10})\.?(?:\s*(?:de\s+)?(\d{4}))?", p)
    if m and m.group(2) in MONTHS:
        d, mo = int(m.group(1)), MONTHS[m.group(2)]
        y = int(m.group(3)) if m.group(3) else infer_year(mo, d, today)
        try: return datetime.date(y, mo, d).isoformat()
        except ValueError: return None
    m = re.search(r"\b([a-z]{3,10})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", p)
    if m and m.group(1) in MONTHS:
        d, mo = int(m.group(2)), MONTHS[m.group(1)]
        y = int(m.group(3)) if m.group(3) else infer_year(mo, d, today)
        try: return datetime.date(y, mo, d).isoformat()
        except ValueError: return None
    return None

def parse_time(s):
    """'23:30', '23.30h', '11:30 PM', '00h' -> 'HH:MM' o None."""
    if not s: return None
    m = re.search(r"\b(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|h)?\b", str(s).lower())
    if not m: return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    if h > 23 or mi > 59: return None
    return f"{h:02d}:{mi:02d}"

def night_date(date, start):
    """Si la hora es de madrugada (00:00-05:59) la noche es la del día anterior."""
    if date and start and start < "06:00":
        return (datetime.date.fromisoformat(date) - datetime.timedelta(days=1)).isoformat()
    return date

def parse_price(s):
    """'Desde 15 €', '12,50€', 'Gratis', '15-25 €' -> (min, max, free). (None, None, False) si no hay precio."""
    if s is None: return (None, None, False)
    p = plain(str(s).replace("€", " eur ").replace("euros", " eur ").replace("euro", " eur "))
    is_free = bool(re.search(r"\b(gratis|gratuit[oa]?|free|lista gratis|entrada libre)\b", p))
    if "eur" not in p:
        return (0, None, True) if is_free else (None, None, False)
    # números que no forman parte de una hora (1:00) ni de una fecha (31/10)
    nums = [float(x.replace(",", ".")) for x in re.findall(r"(?<![\d:/.])(\d+(?:[.,]\d{1,2})?)(?![\d:/])(?!\s*(?:h\b|am\b|pm\b|%))", p)]
    nums = [int(n) if n == int(n) else round(n, 2) for n in nums if n <= 500]
    if not nums: return (0, None, True) if is_free else (None, None, False)
    free = is_free or 0 in nums
    pos = [n for n in nums if n > 0]
    if re.search(r"\b(desde|from|a partir)\b", p): return (0 if free else (min(pos) if pos else 0), None, free)
    if not pos: return (0, None, True)
    if free: return (0, max(pos), True)
    return (min(pos), max(pos) if len(pos) > 1 else None, False)

def in_window(date, today, end):
    return bool(date) and today <= date <= end

def music_tags(text):
    """Etiquetas de música (lista cerrada de SPEC.md) detectadas en un texto libre."""
    p = plain(text)
    tags = []
    rules = [("reggaeton", r"regg?aet[oó]n|perreo"), ("latino", r"\blatin[oa]?\b|bachata|cumbia"), ("comercial", r"comercial|commercial|mainstream|\bhits\b|de todo|top ?40"),
             ("pop", r"\bpop\b"), ("hardtechno", r"hard ?techno|industrial|schranz"), ("techno", r"\btechno\b|tech ?house|minimal|hardgroove"), ("house", r"\bhouse\b|melodic|garage"),
             ("afro", r"afro"), ("electronica", r"electr[oó]nic|\bedm\b|\bdance\b|trance|breaks|synth"), ("hiphop", r"hip ?hop|\brap\b"), ("trap", r"\btrap\b"),
             ("rnb", r"r&b|rnb"), ("dancehall", r"dancehall"), ("indie", r"\bindie\b"), ("rock", r"\brock\b|punk|metal"), ("dnb", r"drum ?(?:and|&|n) ?bass|\bdnb\b|jungle"),
             ("disco", r"\bdisco\b|funk|soul|nu-?disco"), ("salsa", r"\bsalsa\b"), ("flamenco", r"flamenc"), ("remember", r"remember|\b80s\b|\b90s\b|\b2000s\b|cantaditas|retro"),
             ("urban", r"\burban[oa]?\b")]
    for tag, rx in rules:
        if re.search(rx, p) and tag not in tags: tags.append(tag)
    return tags

def event(**kw):
    """Objeto evento con todos los campos de SPEC.md (los no indicados quedan a null/[]/false)."""
    e = {"title": None, "date": None, "start": None, "end": None, "venue": None, "address": None, "zone": "Otros", "type": "club",
         "music": [], "priceMin": None, "priceMax": None, "priceText": None, "free": False, "dressCode": None, "ageMin": None,
         "lineup": [], "description": None, "status": "desconocido", "sources": [], "ticketUrl": None}
    e.update({k: v for k, v in kw.items() if k in e})
    if e["priceMin"] == 0: e["free"] = True
    if e["sources"] and not e["ticketUrl"]: e["ticketUrl"] = e["sources"][0]["url"]
    return e

def validate(events, today, end):
    """Filtra objetos inválidos o fuera de ventana; devuelve (válidos, motivos)."""
    ok, bad = [], {}
    for e in events:
        r = None
        if not isinstance(e, dict) or not e.get("title") or not e.get("venue"): r = "sin título o sala"
        elif not e.get("date") or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(e["date"])): r = "fecha inválida"
        elif not in_window(e["date"], today, end): r = "fuera de ventana"
        elif not e.get("sources") or not e["sources"][0].get("url", "").startswith("http"): r = "sin url de fuente"
        if r: bad[r] = bad.get(r, 0) + 1
        else: ok.append(e)
    return ok, bad
