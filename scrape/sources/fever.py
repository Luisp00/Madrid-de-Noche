"""Fever (feverup.com/madrid): planes de vida nocturna.
Los listados y páginas de sala llevan el estado de la app (<script id="serverapp-state">) ya en el HTML inicial; las fichas /m/{ID}/en traen en ese
estado el detalle del plan, el calendario de fechas con precio mínimo y estado (recurrentes) y las sesiones con su precio (fecha única). Sin navegador."""
import re, json, time, datetime, html as _html
from scrape.common import get, browser, soup, ld_json, event, in_window, music_tags, clean_text, night_date, plain, log

NAME = "Fever"
MIN_EVENTS = 25
BASE = "https://feverup.com"
LISTINGS = ["https://feverup.com/madrid/vida-nocturna-clubs", "https://feverup.com/en/madrid/night-clubs",
            "https://feverup.com/en/madrid/themed-parties", "https://feverup.com/en/madrid/pub-crawl"]
VENUES = ["https://feverup.com/es/madrid/venue/fabrik", "https://feverup.com/en/madrid/venue/teatro-kapital", "https://feverup.com/en/madrid/venue/teatro-eslava",
          "https://feverup.com/en/madrid/venue/enbabia-infused", "https://feverup.com/es/madrid/venue/vg-fuenlabrada", "https://feverup.com/en/madrid/venue/independance-club"]
MAX_PLANS = 60

EXCLUDE = re.compile(r"bingo|shisha|cachimba|hookah|karaoke|escape ?room|dinner|cena\b|cenas\b|restaur|brunch|menu\b|menú|tasting|cata\b|degustaci|masterclass|workshop|taller|clase\b|class\b|course|"
                     r"flamenco|tablao|comedy|comedia|stand-?up|monólogo|monologo|magia|magic show|musical\b|theatre|teatro bellas|museum|museo|(?<!bars )(?<!bar )tour\b|visita|visit\b|"
                     r"paella|sangria|beerpong|beer pong|immersive|inmersiv|candlelight|tribut|drag show|prison island|detective|water lantern|stadium|supercopa|super cup|waitlist|"
                     r"hidden evidences|travesía mortal|jury experience|silent disco tour", re.I)
VIP_QUEUE = re.compile(r"vip.{0,25}(sin esperas|no waiting|sin colas|without waiting|no queue|skip)|(sin esperas|no waiting|without waiting|skip the line|fast ?pass)|fiesta vip|vip party", re.I)
PUB_CRAWL = re.compile(r"pub ?crawl|ruta de bares|bar crawl|bars tour|bar hopping", re.I)
VIP_TICKET = re.compile(r"bono cultural|\bbus\b|autob|transfer|mesa|table|vip|palco|box|backstage|reservad|bottle|botella|sofa|sofá|booth|zona|pack|grupo|group|premium|fast ?pass|skip|cumplea|birthday", re.I)
NOT_NIGHT_CAT_TERMS = re.compile(r"sightseeing|landmark|guided visit|museum|touristic|tourism|castle|escape room|cuisine|food|tasting|course|comedy|flamenco|karaoke|shisha|bingo", re.I)
NOT_NIGHT_CATS = {"food_and_drinks", "tasting", "art", "theater", "activities", "live_sports", "museum", "tour"}
STATUS = {"sold_out": "agotado", "low": "ultimas", "last": "ultimas", "very_low": "ultimas"}

def _state(html):
    m = re.search(r'<script id="serverapp-state"[^>]*>(.*?)</script>', html, re.S)
    if not m: return {}
    try: return json.loads(m.group(1))
    except Exception: return {}

def _plan_id(u):
    m = re.search(r"/m/(\d+)", u or ""); return m.group(1) if m else None

def collect(today, end):
    """IDs de planes (en orden de prioridad: salas, luego listados) con los datos del listado cuando los hay."""
    cand = {}
    def add(pid, **kw):
        c = cand.setdefault(pid, {"name": None, "first": "", "last": "", "venue": None})
        for k, v in kw.items():
            if v and not c.get(k): c[k] = v
    def walk(o):
        if isinstance(o, dict):
            if "id" in o and "name" in o and ("startDate" in o or "first_active_session_date" in o):
                loc = o.get("location") or {}
                add(str(o["id"]), name=(o["name"] or "").strip("﻿ "), first=o.get("startDate") or o.get("first_active_session_date"),
                    last=o.get("endDate") or o.get("last_active_session_date"), venue=loc.get("name") if isinstance(loc, dict) else None)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    def fetch(u):
        try: h = get(u)
        except Exception as ex:
            log(NAME, "listado", u, ex); return None
        if "serverapp-state" not in h:
            try: h = browser(u, raw=True, wait=4000)
            except Exception as ex: log(NAME, "navegador", u, ex); return None
        return h
    for u in VENUES:
        h = fetch(u)
        if not h: continue
        for k, v in _state(h).items():
            if k.startswith("venue-detail-plans"): walk(v)       # solo los planes de la sala (no los "cerca de")
    for u in LISTINGS:
        h = fetch(u)
        if not h: continue
        ids = [i for x in ld_json(h) if x.get("@type") == "ItemList" for it in x.get("itemListElement", []) if (i := _plan_id(it.get("url")))]
        if not ids: ids = re.findall(r"/m/(\d+)", h)
        for i in ids: add(i)
        st = _state(h)
        for k, v in st.items():
            if k.startswith("WhatPlanFilterService") or k.startswith("venue-detail-plans"): walk(v)
    out = []
    for pid, c in cand.items():
        f, l = (c["first"] or "")[:10], (c["last"] or "")[:10]
        if f and l and (l < today or f > end): continue
        if c["name"] and (EXCLUDE.search(c["name"]) or VIP_QUEUE.search(c["name"])): continue
        out.append((pid, c))
    return out

def _leaves(o, path, acc):
    """Sesiones (hojas con starts_at_iso) del selector de entradas, con las etiquetas de los niveles por los que se llega."""
    if isinstance(o, dict):
        if "starts_at_iso" in o and "price" in o: acc.append((path, o)); return
        lab = o.get("default_label") if isinstance(o.get("default_label"), str) else None
        for k, v in o.items(): _leaves(v, path + ([lab] if lab and k == "level" else []) if False else path + ([lab] if lab else []), acc)
    elif isinstance(o, list):
        for v in o: _leaves(v, path, acc)

def _text(htm):
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<br\s*/?>|</p>|</li>", ". ", htm or ""))))

def _tod(iso):
    return iso[11:16] if iso and "T" in iso else None

def scrape(today, end):
    cands = collect(today, end)
    log(NAME, "candidatos", len(cands))
    d0 = datetime.date.fromisoformat(today)
    out, dedup, nfetch = [], set(), 0
    singles = {}   # (sala, fecha) de planes de fecha única, para no repetir la sesión genérica de un recurrente
    for pid, c in cands:
        if nfetch >= MAX_PLANS: break
        url = f"{BASE}/m/{pid}/en"
        nfetch += 1; time.sleep(0.4)
        try: html = get(url)
        except Exception as ex: log(NAME, "ficha", url, ex); continue
        try: evs = plan_events(pid, url, html, c, today, end)
        except Exception as ex: log(NAME, "plan", pid, repr(ex)); continue
        for rec, e in evs:
            k = (e["title"].lower(), e["date"], e["venue"].lower())
            if k in dedup: continue
            dedup.add(k); out.append((rec, e))
    # un recurrente genérico no repite la noche en que su sala tiene un evento con nombre propio
    named = {(e["venue"].lower(), e["date"]) for rec, e in out if not rec}
    return [e for rec, e in out if not (rec and (e["venue"].lower(), e["date"]) in named)]

def plan_events(pid, url, html, c, today, end):
    st = _state(html)
    det = st.get(f"PlanService.getPlanDetail.{pid}") or {}
    name = (det.get("name") or c.get("name") or "").strip("﻿ ")
    cat = det.get("category") or ""
    cats = det.get("categories") or []
    if not name or EXCLUDE.search(name) or VIP_QUEUE.search(name) or cat in NOT_NIGHT_CATS: return []
    hard = re.compile(r"karaoke|escape room|comedy|flamenco|shisha|bingo|museum|sightseeing|landmark|guided visit|touristic", re.I)
    if any((hard if "Nightlife & Concerts" in cats else NOT_NIGHT_CAT_TERMS).search(x) for x in cats): return []
    name = clean_text(re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]", "", name))
    place = det.get("defaultPlace") or {}
    venue = clean_text(place.get("name") or c.get("venue") or "")
    slug = place.get("slug") or ""
    if slug == "teatro-kapital" or venue.lower() == "kapital": venue = "Teatro Kapital"
    venue = re.split(r"\s+[l|]\s+", venue)[0]
    venue = re.sub(r"^(.{4,}?)\s+Madrid$", r"\1", venue)
    if not venue: return []
    addr = clean_text(place.get("address") or "")
    if addr and "madrid" not in addr.lower(): addr += ", Madrid"
    desc_html = det.get("description") or ""
    dtext = _text(desc_html)
    pub = bool(PUB_CRAWL.search(name))
    if pub: cat = "otro"
    dsess = det.get("defaultSession") or {}
    # --- sesiones por fecha
    by_date = {}
    for k, v in st.items():
        if k.startswith("PlanService.getPlanAvailabilityForPlace.") and f".{pid}." in k:
            for dt, x in (v.get("dates") or {}).items():
                by_date.setdefault(dt, {}).update(price=x.get("minTicketPrice"), status=x.get("status"), cal=True)
    leaves = []
    for k, v in st.items():
        if k.startswith(("LEVEL_TICKET_SELECTOR_SESSIONS", "PlanService.getPlanSessionsForPlaceAndDate.")): _leaves(v, [], leaves)
    leaves = [(p, s) for p, s in leaves if s.get("ends_at_iso")]      # sin hora de fin = extras (autobús, guardarropa…)
    for path, s in leaves:
        dt = s["starts_at_iso"][:10]
        e = by_date.setdefault(dt, {})
        e.setdefault("sess", []).append((path, s))
    recurring = bool(det.get("multipleSessions")) and any(x.get("cal") for x in by_date.values())
    # --- hora típica: sesión por defecto o primera hoja
    st0, en0 = _tod(dsess.get("startsAtIso")), _tod(dsess.get("endsAtIso"))
    if not st0 and leaves: st0, en0 = _tod(leaves[0][1]["starts_at_iso"]), _tod(leaves[0][1].get("ends_at_iso"))
    if not by_date:
        f, l = (det.get("firstActiveSessionDate") or c.get("first") or "")[:10], (det.get("lastActiveSessionDate") or c.get("last") or "")[:10]
        if f and f == l: by_date[f] = {}
        elif f and l:       # solo rango de fechas, sin calendario: jueves-sábado
            d = max(datetime.date.fromisoformat(f), datetime.date.fromisoformat(today)); le = min(datetime.date.fromisoformat(l), datetime.date.fromisoformat(end))
            while d <= le:
                if d.weekday() in (3, 4, 5): by_date[d.isoformat()] = {}
                d += datetime.timedelta(days=1)
            recurring = True
    age = None
    m = re.search(r"(?:age requirement|edad(?: m[ií]nima)?)\W+(?:\+|mayores de\s*)?(\d{2})", dtext, re.I)
    if m: age = int(m.group(1))
    elif re.search(r"\b(\d{2})\s*\+", dtext): age = int(re.search(r"\b(\d{2})\s*\+", dtext).group(1))
    desc = dtext
    desc = re.sub(r"^(?:Tickets? for|Entradas? para)[^.]{0,80}?(?=General|Access|Acceso|Entrada|\w+ )", "", desc)
    desc = clean_text(re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", desc))[:400] or None
    res = []
    window3 = (datetime.date.fromisoformat(today) + datetime.timedelta(days=2)).isoformat()
    for dt, x in sorted(by_date.items()):
        sess = x.get("sess") or []
        # hora de la sesión de ese día (si se ve) o la típica
        if sess: st_, en_ = _tod(sess[0][1]["starts_at_iso"]), _tod(sess[0][1].get("ends_at_iso"))
        else: st_, en_ = st0, en0
        sdate = night_date(dt, st_) if st_ else dt
        if not in_window(sdate, today, end): continue
        if pub and sdate > window3: continue
        if st_ and "06:00" <= st_ < "20:00" and en_ and "06:00" <= en_ <= "23:00" and cat == "concert": continue
        if st_ and "06:00" <= st_ < "12:00": continue                    # sesiones de mañana (matinales solo con mesas, visitas…)
        gen = [s for p, s in sess if not any(VIP_TICKET.search(l or "") for l in p) and not VIP_TICKET.search(s.get("label_without_format") or "")]
        avail = [s for s in gen if s.get("has_available_tickets", True)]
        prices = [s["price"] for s in (avail or gen) if isinstance(s.get("price"), (int, float))]
        pmin = pmax = None
        if prices: pmin, pmax = min(prices), max(prices)
        elif x.get("price") is not None: pmin = x["price"]
        elif det.get("priceInfo") and not recurring: pmin = (det["priceInfo"] or {}).get("amount")
        if pmax == pmin: pmax = None
        ptxt = None
        if pmin is not None:
            ptxt = (f"{pmin:g} €" if pmax is None and prices and len(set(prices)) == 1 and not x.get("cal") else f"Desde {pmin:g} €" + (f" hasta {pmax:g} €" if pmax else ""))
            if pmin == 0: ptxt = "Gratis" if pmax is None else ptxt
        if sess and not gen and not x.get("cal"): continue                # fecha con solo mesas/VIP
        stat = "desconocido"
        if sess:
            if gen and not avail: stat = "agotado"
            elif any(s.get("last_tickets") for s in avail): stat = "ultimas"
            elif avail: stat = "disponible"
        if x.get("status") in STATUS: stat = STATUS[x["status"]]
        elif stat == "desconocido" and x.get("cal"): stat = "disponible"
        res.append((recurring and not pub, event(
            title=name, date=sdate, start=st_, end=en_, venue=venue, address=addr or None, type="otro" if pub else ("festival" if re.search(r"festival|fest\b", name, re.I) else "concierto" if cat == "concert" or "Concert" in cats else "tardeo" if st_ and "12:00" <= st_ < "20:00" else "club"),
            music=music_tags(" ".join([name] + cats)) , priceMin=pmin, priceMax=pmax, priceText=ptxt, ageMin=age,
            description=desc, status=stat, sources=[{"name": NAME, "url": f"{BASE}/m/{pid}"}], ticketUrl=f"{BASE}/m/{pid}")))
    return res
