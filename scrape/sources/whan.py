"""WHAN (app.whan.es), ticketera de clubs: la web es JS, pero su API JSON pública responde a requests sin clave.
Listado: /api/v1/public/explore?page[number]=N&page[size]=48 (meta.totalPages; todos los clubs de España, se filtra
attributes.club.province == "Madrid"; trae nombre, inicio/fin, musicType y club, sin slug ni precio).
Detalle: /api/v1/event/{id o slug}?preview=1 (máx. 60, los más próximos primero): slug, dressCode (a menudo con la edad: "+18, CASUAL"),
generalTicketsEnabled con tramos (price, sold, ticketsLeft), publicEventLists (listas gratis con hora límite en el nombre/notas) y reservados.
La web pública del evento es https://app.whan.es/event/{slug} (con el id, /event/{id}, redirige a la del slug)."""
import re, time, datetime
from zoneinfo import ZoneInfo
from scrape.common import get, event, clean_text, night_date, music_tags, in_window, plain, log

NAME = "WHAN"
MIN_EVENTS = 40
API = "https://app.whan.es/api/v1"
WEB = "https://app.whan.es/event/"
MADRID = ZoneInfo("Europe/Madrid")
MAX_DETAIL = 60
VENUES = {"istar": "Istar", "panthera": "Villa Panthera", "liberty club": "Liberty Supper Club", "nazca club": "Nazca", "rubicon": "Rubicón",
          "la flaca | tardeo": "La Flaca", "la flaca": "La Flaca"}
SKIP_VENUE = re.compile(r"restaurant|restaurante", re.I)
TABLE = re.compile(r"mesa|reservad|botella|bottle|table|vip|barra|cumplea|sunbed|cama\b", re.I)
WEEKDAY = re.compile(r"^(?:(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados?|domingos?|monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?)$", re.I)

def _n(x):
    x = round(float(x), 2)
    return int(x) if x == int(x) else x

def _dt(s):
    return datetime.datetime.fromisoformat(s).astimezone(MADRID)

def _venue(n):
    n = clean_text(n)
    key = plain(n)
    if key in VENUES: return VENUES[key]
    n = re.sub(r"\s*\|\s*tardeo$", "", n, flags=re.I)
    n = re.sub(r"^(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados?|domingos?)\s+de\s+", "", n, flags=re.I)  # "Martes De Sala De Despecho"
    return n.title() if n.isupper() else n

def _list(today, end):
    out, page, pages = [], 1, 1
    while page <= pages:
        try: d = get(f"{API}/public/explore?page[number]={page}&page[size]=48", json_=True)
        except Exception as ex: log(NAME, "explore", page, ex); break
        pages = min(int((d.get("meta") or {}).get("totalPages") or 1), 15)
        out.extend(d.get("data") or [])
        page += 1; time.sleep(0.3)
    cands = []
    for it in out:
        a = it.get("attributes") or {}
        club = a.get("club") or {}
        if club.get("province") != "Madrid" or not a.get("startDateTime") or SKIP_VENUE.search(club.get("name") or ""): continue
        s = _dt(a["startDateTime"]); start = s.strftime("%H:%M")
        date = night_date(s.date().isoformat(), start)
        if not in_window(date, today, end): continue
        cands.append((date, start, it))
    cands.sort(key=lambda c: (c[0], c[1]))
    log(NAME, f"{len(out)} en el listado, {len(cands)} de Madrid en ventana")
    return cands

def _age(dress):
    ages = [int(x) for x in re.findall(r"\+\s*(\d{2})\b", dress or "")]
    return min(ages) if ages else None

def _dress(dress):
    if not dress or plain(dress) in ("null", "none", "-") or "madrid" in plain(dress): return None, None  # "SKYLINEMADRID" es relleno
    parts = [clean_text(p) for p in re.split(r"[,;]", dress)]
    keep = [p for p in parts if p and not re.search(r"\+\s*\d{2}\b", p)]
    age_txt = None
    if len({int(x) for x in re.findall(r"\+\s*(\d{2})\b", dress)}) > 1:
        age_txt = "Edad: " + ", ".join(p for p in parts if re.search(r"\+\s*\d{2}\b", p))
    return (", ".join(keep) or None), age_txt

def _limit(txt):
    """Hora límite de una lista gratis ('GUEST LIST CHICAS 01:00', 'hasta las 19:00', 'antes de la 1,30') -> 'HH:MM' o None."""
    t = (txt or "").lower()
    m = re.search(r"(\d{1,2})\s*[:.,h]\s*(\d{2})\b", t)
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60: return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"(?:hasta|antes de|before|until)\s*(?:las?|de)?\s*(\d{1,2})\b(?!\s*[€x])", t)
    if m and int(m.group(1)) < 24: return f"{int(m.group(1)):02d}:00"
    return None

def _lists(det):
    """Listas gratis -> (hay_lista, texto)."""
    parts, notes = [], []
    for l in det.get("publicEventLists") or []:
        try: price = float(l.get("price") or 0)
        except ValueError: price = 1
        if price != 0 or l.get("public") is False or l.get("guestLeft") == 0: continue
        name = clean_text(l.get("name")).replace("⁠", "")
        who = " chicas" if re.search(r"chicas|girls|only girls|ladies", name, re.I) else (" chicos" if re.search(r"chicos|boys", name, re.I) else "")
        lim = _limit(name) or _limit(l.get("notes"))
        parts.append(f"Lista gratis{who}" + (f" hasta {lim}" if lim else ""))
        if l.get("notes"): notes.append(clean_text(l["notes"]))
    return list(dict.fromkeys(parts)), notes

def _tickets(det):
    tks = det.get("generalTicketsEnabled") or det.get("generalTicketsEnabledToBeSold") or []
    avail_p, all_p, parts, flags = [], [], [], []
    for t in tks:
        nm = clean_text(t.get("name")).replace("⁠", "")
        try: base = float(t.get("price") or 0)
        except ValueError: continue
        if TABLE.search(nm) or base >= 300: continue
        tiers = t.get("tiers") or [{"price": t.get("price"), "ticketsLeft": 0 if t.get("completed") else 1, "closed": False}]
        prices = [float(x["price"]) for x in tiers if x.get("price") not in (None, "")]
        av = [float(x["price"]) for x in tiers if x.get("price") not in (None, "") and (x.get("ticketsLeft") or 0) > 0 and not x.get("closed")]
        sellable = bool(av) and not t.get("saleDisabled") and not t.get("completed")
        all_p += prices
        if sellable: avail_p += av
        flags.append(sellable)
        p = _n(min(av or prices or [base]))
        label = nm if re.search(r"\d\s*€", nm) else f"{nm} {p} €"
        parts.append(label + ("" if sellable else " (agotada)"))
    return all_p, avail_p, list(dict.fromkeys(parts)), flags

def _type(name, a, s, e):
    if re.search(r"festival", name, re.I) or re.search(r"festival", a.get("eventType") or "", re.I): return "festival"
    if re.search(r"tardeo", name, re.I): return "tardeo"
    if s.hour >= 6 and s.hour < 21 and e and e < s.replace(hour=0, minute=0) + datetime.timedelta(days=1, hours=2) and e > s: return "tardeo"
    return "club"

def price_info(det):
    """Precio, estado, dress code, edad y nota a partir del detalle del API (/event/{id}?preview=1). Lo usan scrape() y enrich.py."""
    dress, age_txt = _dress(det.get("dressCode"))
    lists, notes = _lists(det)
    all_p, avail_p, tparts, flags = _tickets(det)
    pool = avail_p or all_p
    pmin, pmax, status = None, None, "desconocido"
    if pool: pmin, pmax = _n(min(pool)), _n(max(pool))
    if flags: status = "disponible" if any(flags) else "agotado"
    if lists: pmin = 0
    if pmax is not None and pmax <= (pmin or 0): pmax = None
    if lists and pool and pmax is None and pool and _n(min(pool)) > 0: pmax = _n(max(pool))
    ptxt = " · ".join(lists + tparts)[:120] or None
    if len(" · ".join(lists + tparts)) > 120: ptxt = ptxt[:117].rstrip(" ·") + "…"
    desc = []
    if notes: desc.append(notes[0][:200])
    res = [float(x["price"]) for x in det.get("floorImagesEnabled") or [] if x.get("price") and not x.get("salesClosed")]
    if res: desc.append(f"Reservados desde {_n(min(res))} €.")
    if age_txt: desc.append(age_txt)
    return {"priceMin": pmin, "priceMax": pmax, "priceText": ptxt, "status": status, "dressCode": dress, "lists": lists,
            "free": bool(lists) or pmin == 0, "ageMin": _age(det.get("dressCode")), "desc": desc}

def scrape(today, end):
    cands = _list(today, end)
    out, ndet = [], 0
    for date, start, it in cands:
        a = it["attributes"]
        s = _dt(a["startDateTime"]); e = _dt(a["endDateTime"]) if a.get("endDateTime") else None
        det = {}
        if ndet < MAX_DETAIL:
            try: det = get(f"{API}/event/{it['id']}?preview=1", json_=True)
            except Exception as ex: log(NAME, "detalle", it["id"], ex)
            ndet += 1; time.sleep(0.4)
        venue = _venue(a["club"]["name"])
        name = clean_text(det.get("name") or a.get("name"))
        if WEEKDAY.match(name): name = f"{name} en {venue}"
        slug = det.get("slug")
        url = WEB + (slug or it["id"])
        pi = price_info(det)
        pmin, pmax, ptxt, status, dress, lists = pi["priceMin"], pi["priceMax"], pi["priceText"], pi["status"], pi["dressCode"], pi["lists"]
        desc = pi["desc"]
        out.append(event(title=name, date=date, start=start, end=e.strftime("%H:%M") if e else None, venue=venue,
                         type=_type(name, a, s, e), music=music_tags(det.get("musicType") or a.get("musicType") or ""),
                         priceMin=pmin, priceMax=pmax, priceText=ptxt, free=bool(lists) or pmin == 0, dressCode=dress, ageMin=_age(det.get("dressCode")),
                         description=clean_text(" ".join(desc))[:400] or None, status=status, sources=[{"name": NAME, "url": url}], ticketUrl=url))
    log(NAME, f"{ndet} fichas, {len(out)} eventos")
    return out
