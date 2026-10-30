"""Resident Advisor (ra.co): la web da 403 a los navegadores, pero su GraphQL público (https://ra.co/graphql) responde a un POST
JSON sin clave. `eventListings` con areas:{eq:41} (Madrid) y listingDate entre hoy y fin, pageSize 100 paginando por `page` hasta
cubrir totalResults. Trae hora de inicio/fin, cost (texto libre del promotor), minimumAge, géneros, line-up, sala+dirección y los
tramos de entrada (priceRetail con comisión, validType SOLDOUT/VALID/NOLONGERONSALE), de donde salen el precio y el estado.
La respuesta cruda de cada página se guarda en la caché de common (clave propia) para no repetir la llamada."""
import re, json, time
from scrape.common import session, _cached, _store, FetchError, event, clean_text, night_date, music_tags, log

NAME = "Resident Advisor"
MIN_EVENTS = 60
URL = "https://ra.co/graphql"
AREA = 41  # Madrid
PAGE_SIZE = 100
HEADERS = {"Content-Type": "application/json", "Referer": "https://ra.co/events/es/madrid"}
QUERY = ('{ eventListings(filters:{areas:{eq:%d},listingDate:{gte:"%s",lte:"%s"}},pageSize:%d,page:%d){ totalResults data{ event{ '
         'id title date startTime endTime cost minimumAge isTicketed contentUrl genres{name} artists{name} venue{name address} '
         'tickets(queryType:AVAILABLE){title priceRetail validType} } } } }')
# tramos que no son entrada general (mesas, VIP, backstage, bonos que exigen otra entrada...)
NOT_GENERAL = re.compile(r"mesa|table|reservad|botella|bottle|vip|backstage|bono|needs general|guestlist upgrade|locker|guardarropa|cloak|parking|donation|merch|after ?party pass", re.I)
LIVE = re.compile(r"\b(live|concert|concierto|band|rock|punk|metal|indie|jazz)\b", re.I)

def _n(x):
    x = round(float(x), 2)
    return int(x) if x == int(x) else x

def _page(today, end, page):
    key = f"RA GRAPHQL area={AREA} {today} {end} size={PAGE_SIZE} page={page}"
    txt = _cached(key)
    if txt is None:
        body = {"query": QUERY % (AREA, today, end, PAGE_SIZE, page)}
        last = None
        for i in range(4):
            try:
                r = session().post(URL, json=body, headers=HEADERS, timeout=40)
            except Exception as ex:
                last = str(ex)[:200]; time.sleep(2 * (i + 1)); continue
            if r.status_code in (403, 429):
                raise FetchError(f"{URL}: HTTP {r.status_code} (bloqueado por Cloudflare/rate limit de RA)")
            if r.status_code == 200 and '"eventListings"' in r.text and '"errors"' not in r.text[:60]:
                txt = r.text; _store(key, txt); break
            last = f"HTTP {r.status_code} {r.text[:120]!r}"
            time.sleep(2 * (i + 1))
        if txt is None: raise FetchError(f"{URL} página {page}: {last}")
    return json.loads(txt)["data"]["eventListings"]

def _fetch_all(today, end):
    items, seen, page, total = [], set(), 1, None
    while True:
        res = _page(today, end, page)
        total = res.get("totalResults") or 0
        rows = [d["event"] for d in res.get("data") or [] if d.get("event")]
        if not rows: break
        for e in rows:
            if e["id"] not in seen: seen.add(e["id"]); items.append(e)
        if len(seen) >= total or page >= 20: break
        page += 1; time.sleep(0.5)
    log(NAME, f"{len(items)} de {total} en el listado")
    return items

def _cost(cost):
    """Texto libre ('18€', '5€ - 15€', '16,18,20', '1€/13€/15€', '0', '€') -> (min, max) o (None, None)."""
    s = clean_text(cost)
    if not s or not re.search(r"\d", s): return (None, None)
    if re.fullmatch(r"\d+[.,]\d{1,2}\s*€?", s): nums = [float(s.replace(",", ".").replace("€", ""))]
    else: nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:\.\d{1,2})?", s.replace(",", " "))]
    nums = [n for n in nums if n <= 300]
    if not nums: return (None, None)
    lo, hi = _n(min(nums)), _n(max(nums))
    return (lo, hi if hi > lo else None)

def _tickets(tks):
    """(priceMin, priceMax, priceText, status) de los tramos de venta."""
    tks = [t for t in tks or [] if isinstance(t.get("priceRetail"), (int, float))]
    gen = [t for t in tks if not NOT_GENERAL.search(t.get("title") or "")] or []
    pool = gen or tks
    live = [t for t in pool if t["validType"] in ("VALID", "SOLDOUT")]
    status = "desconocido"
    if live:
        status = "disponible" if any(t["validType"] == "VALID" for t in live) else "agotado"
    if not gen: return (None, None, None, status)
    pr = [t for t in gen if t["validType"] == "VALID"] or [t for t in gen if t["validType"] == "SOLDOUT"] or gen
    prices = [_n(t["priceRetail"]) for t in pr]
    lo, hi = min(prices), max(prices)
    parts = []
    for t in gen:
        if t["validType"] == "NOLONGERONSALE": continue
        nm = clean_text(t["title"]); p = _n(t["priceRetail"])
        s = f"{nm} {p} €" if p else f"{nm} (gratis)"
        if t["validType"] == "SOLDOUT": s += " agotada"
        parts.append(s)
    txt = " · ".join(parts)
    if len(txt) > 120: txt = txt[:117].rstrip(" ·") + "…"
    return (lo, hi if hi > lo else None, txt or None, status)

def _address(a):
    a = clean_text(a)
    # RA a veces pega número y código postal ("C. de Galileo, 2628015 Madrid")
    a = re.sub(r"(?<!\d)(\d{1,3})(28\d{3})(?!\d)", r"\1, \2", a)
    return a or None

def scrape(today, end):
    items = _fetch_all(today, end)
    out = []
    for e in items:
        v = e.get("venue") or {}
        st, en = e.get("startTime") or "", e.get("endTime") or ""
        start = st[11:16] if len(st) >= 16 else None
        endt = en[11:16] if len(en) >= 16 else None
        base = (st or e.get("date") or "")[:10]
        date = night_date(base, start) if start else (e.get("date") or "")[:10]
        venue = re.sub(r"^(?:TBA\s*-\s*)?(?:secret location\s*-\s*)?", "", clean_text(v.get("name")), flags=re.I)
        if not venue or re.fullmatch(r"tba|secret location|por confirmar", venue, re.I) or not e.get("title") or not date: continue
        lo, hi, ptxt, status = _tickets(e.get("tickets"))
        if lo is None:
            lo, hi = _cost(e.get("cost"))
            if lo is not None: ptxt = "Gratis" if lo == 0 and hi is None else f"{lo}–{hi} €" if hi else f"{lo} €"
        genres = [g["name"] for g in e.get("genres") or [] if g.get("name")]
        typ = "concierto" if any(LIVE.search(g) for g in genres) else "club"
        if start and "12:00" <= start < "20:00" and endt and (endt > start or endt <= "02:00"):
            typ = "festival" if re.search(r"festival", e["title"], re.I) else "tardeo"
        url = "https://ra.co" + (e.get("contentUrl") or f"/events/{e['id']}")
        out.append(event(title=clean_text(e["title"]), date=date, start=start, end=endt, venue=venue, address=_address(v.get("address")),
                         type=typ, music=music_tags(" ".join(genres)), priceMin=lo, priceMax=hi, priceText=ptxt, free=(lo == 0),
                         ageMin=e.get("minimumAge") or None, lineup=[a["name"] for a in e.get("artists") or [] if a.get("name")][:12],
                         status=status, sources=[{"name": NAME, "url": url}], ticketUrl=url))
    log(NAME, f"{len(out)} eventos")
    return out
