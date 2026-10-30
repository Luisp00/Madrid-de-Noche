"""Nightlife Madrid (nightlifemadrid.com): su web de entradas tickets.nightlifemadrid.com (plataforma PATT, SPA) lee de un API JSON
público (el mismo que usa la página en el navegador, sin clave):
  - GET  {API}/events/getpromoterevents/PATT?subdomain=nightlifemadrid -> todas las sesiones FECHADAS del promotor (nombre, inicio/fin
    UTC, club, música, dress code, edad). Las páginas por sala (/en/teatro-kapital/, /en/utopia/…) muestran este mismo listado: las
    "fiestas semanales" de Kapital/Utopia/Waves de nightlifemadrid.com no tienen sesiones a la venta y ya no se generan.
  - POST {API}/tickets/geteventdetailss {"eventId", "promoterName"} -> tipos de entrada (precio, plazas, phaseStatus) y dirección del club.
La ficha pública de cada sesión es https://tickets.nightlifemadrid.com/pass/{id}?handle=nightlifemadrid.
Pub crawls (Meet & Party, Fucking Monday): solo las 3 primeras noches (SPEC). Intercambios de idiomas fuera.
"""
import re, time, json, datetime
from zoneinfo import ZoneInfo
from scrape import common
from scrape.common import get, event, music_tags, clean_text, plain, night_date, in_window, log

NAME = "Nightlife Madrid"
MIN_EVENTS = 5
API = "https://everywhereback.azurewebsites.net"
PROMOTER = "nightlifemadrid"
WEB = "https://tickets.nightlifemadrid.com/pass/{id}?handle=" + PROMOTER
MADRID = ZoneInfo("Europe/Madrid")
MAX_DETAIL = 60
VENUES = {"icon": "Icon Madrid", "houdinni": "Houdinni", "manama": "Manamá", "calle 365": "Calle 365", "fucking monday": "Calle 365",
          "saint club": "Saint Club", "teatro eslava": "Joy Eslava", "boris club": "Boris Club"}
SKIP = re.compile(r"language|speak|intercambio|karaoke|clase|lesson|workshop", re.I)
CRAWL = re.compile(r"pub ?crawl|fucking monday", re.I)
TABLE = re.compile(r"mesa|reservad|botella|bottle|table|\bvip\b|booth|cumplea|reserve your spot|reserva tu plaza", re.I)   # "reserve your spot" 0 €: se paga en el sitio

def _venue(club):
    n = re.sub(r"\s+NL$", "", clean_text(club or ""))
    return VENUES.get(plain(n)) or (n.title() if n.isupper() and len(n) > 3 else n)

def _n(x):
    x = round(float(x), 2)
    return int(x) if x == int(x) else x

def detail(eid):
    """Detalle de una sesión (POST, con la caché de common). {} si falla."""
    key = f"POST {API}/tickets/geteventdetailss {eid}"
    txt = common._cached(key)
    if txt is None:
        for i in range(3):
            try:
                r = common.session().post(f"{API}/tickets/geteventdetailss", json={"eventId": eid, "promoterName": PROMOTER}, timeout=30)
                if r.status_code == 200:
                    txt = r.text; common._store(key, txt); break
                if r.status_code in (403, 404, 429): break
            except Exception as ex:
                log(NAME, "detalle", eid, str(ex)[:120])
            time.sleep(1.5 * (i + 1))
    try: return json.loads(txt) if txt else {}
    except ValueError: return {}

def price_info(det):
    """-> dict(priceMin, priceMax, priceText, free, status, address, ageMin, dressCode) a partir del detalle (vacío si no hay entradas)."""
    out = {}
    ev = det.get("event") or {}
    loc = clean_text(((ev.get("club") or {}).get("location")) or "")
    if loc: out["address"] = re.sub(r",\s*Spain$", "", loc)
    m = re.search(r"(\d{2})", str(ev.get("Age") or ""))
    if m: out["ageMin"] = int(m.group(1))
    if ev.get("DressCode"): out["dressCode"] = clean_text(ev["DressCode"])[:80]
    tks = [t for t in det.get("tickets") or [] if t.get("visible", True) and not t.get("isWaitlist") and not t.get("hidePrice")
           and isinstance(t.get("price"), (int, float)) and not TABLE.search(t.get("ticketType") or "")]
    if not tks: return out
    avail = [t for t in tks if (t.get("numberOfTicketsLeft") or 0) > 0 and not str(t.get("phaseStatus") or "").startswith("closed")]
    pool = avail or tks
    paid = [t["price"] for t in pool if t["price"] > 0]
    free = any(t["price"] == 0 for t in pool)
    pmin = 0 if free else (_n(min(paid)) if paid else None)
    pmax = _n(max(paid)) if paid and (free or max(paid) > min(paid)) else None
    parts = []
    for t in pool:
        nm = clean_text(t.get("ticketType") or "Entrada")
        parts.append(nm if t["price"] == 0 and re.search(r"free|gratis|list", nm, re.I) else f"{nm} {_n(t['price'])} €")
    out.update(priceMin=pmin, priceMax=pmax, priceText=" · ".join(dict.fromkeys(parts))[:120] or None, free=free,
               status=("disponible" if avail else "agotado") if not any(t.get("FewTicketsLeft") for t in avail) else "ultimas")
    return out

def scrape(today, end):
    try: d = get(f"{API}/events/getpromoterevents/PATT?subdomain={PROMOTER}", json_=True)
    except Exception as ex:
        log(NAME, "listado", ex); return []
    t3 = (datetime.date.fromisoformat(today) + datetime.timedelta(days=2)).isoformat()
    cands = []
    for ev in d.get("events") or []:
        name = clean_text(ev.get("eventName"))
        if not name or not ev.get("dateAndHour") or SKIP.search(name): continue
        s = datetime.datetime.fromisoformat(ev["dateAndHour"].replace("Z", "+00:00")).astimezone(MADRID)
        start = s.strftime("%H:%M")
        date = night_date(s.date().isoformat(), start)
        crawl = bool(CRAWL.search(name)) or plain((ev.get("club") or {}).get("name")) == "fucking monday"
        if not in_window(date, today, end) or (crawl and date > t3): continue
        cands.append((date, start, s, crawl, name, ev))
    cands.sort(key=lambda c: (c[0], c[1]))
    out = []
    for i, (date, start, s, crawl, name, ev) in enumerate(cands):
        info = {}
        if i < MAX_DETAIL:
            info = price_info(detail(ev["_id"])); time.sleep(0.4)
        e = ev.get("dateAndHourEnd")
        endt = datetime.datetime.fromisoformat(e.replace("Z", "+00:00")).astimezone(MADRID).strftime("%H:%M") if e else None
        venue = _venue((ev.get("club") or {}).get("name"))
        tard = "06:00" <= start < "20:00"
        desc = clean_text(ev.get("description") or "")[:400] or None
        url = WEB.format(id=ev["_id"])
        age = info.get("ageMin")
        if age is None:
            m = re.search(r"(\d{2})", str(ev.get("Age") or "")); age = int(m.group(1)) if m else None
        out.append(event(title=name, date=date, start=start, end=endt, venue=venue, address=info.get("address"),
                         type="tardeo" if tard else ("fiesta" if crawl else "club"),
                         music=music_tags(" ".join(ev.get("music_type") or []) + " " + name), priceMin=info.get("priceMin"),
                         priceMax=info.get("priceMax"), priceText=info.get("priceText"), free=bool(info.get("free")),
                         dressCode=info.get("dressCode") or (clean_text(ev["DressCode"])[:80] if ev.get("DressCode") else None), ageMin=age,
                         lineup=[clean_text(x) for x in ev.get("DJ_name") or [] if x][:12], description=desc,
                         status=info.get("status", "desconocido"), sources=[{"name": NAME, "url": url}], ticketUrl=url))
    log(NAME, f"{len(d.get('events') or [])} sesiones del promotor, {len(out)} en ventana")
    return out
