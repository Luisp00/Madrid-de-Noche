#!/usr/bin/env python3
"""Rellena el precio de los eventos que los parsers dejan sin él, visitando la página de compra del evento en la ticketera.

Uso: python3 enrich.py run/data [--max 250] [--today YYYY-MM-DD] [--days 14]

Recorre run/data/*.json (salida de scrape.py), toma los eventos sin precio (priceMin y priceMax nulos) cuyo ticketUrl o alguna
url de `sources` es la ficha de un evento en una ticketera con página pública, la descarga con scrape.common.get (caché de 1 h,
time.sleep(0.4) entre páginas) y rellena priceMin, priceMax, priceText, free y status (y start, address y ageMin si faltan).
Reescribe los JSON in situ y deja run/data/_enrich_report.json (intentados, con precio nuevo, por host).

Por ticketera:
  - Xceed      xceed.me/…/event/<slug>/<id>        scrape.sources.xceed._detail + _price (JSON-LD con ofertas, edad, dirección)
  - DICE       dice.fm/event/…, link.dice.fm/…     JSON-LD MusicEvent (AggregateOffer); el enlace corto se cambia por la ficha canónica
  - WHAN       app.whan.es/event/<slug>            API /api/v1/event/<slug>?preview=1 + scrape.sources.whan.price_info
  - Fever      feverup.com/m/<id>                  scrape.sources.fever.plan_events (estado de la app con sesiones y precios)
  - Taquilla   taquilla.com/entradas/<slug>?event= scrape.sources.taquilla._sessions (microdatos lowPrice/highPrice por sesión)
  - PATT       tickets.nightlifemadrid.com/pass/<id> scrape.sources.nightlifemadrid.detail + price_info (API JSON)
  - resto      Eventbrite, Entradium, Wegow, geeticket, onebox, Tomaticket, Woutick, Enterticket, entradas.conciertos.club,
               AllEvents, Eventim Light, Ticketclub: JSON-LD Event/offers genérico (lowPrice/highPrice/price/availability).
  - Madrid en Vivo: la ficha (madridenvivo.com/evento/…) solo dice "Precio: A consultar"; se sigue su botón "Comprar entradas" si
    apunta a una de las ticketeras anteriores (prioridad baja: dos páginas por evento).
No se visitan ra.co, Fourvenues, Shotgun, Technobeatscloud, Ticketmaster ni Atrápalo (403/429/reto anti-bot); si cualquier web
responde 403/429 o un reto, se deja el evento como estaba y, tras 3 bloqueos, se deja de pedir a ese host.
Se omiten los eventos cuyo enlace de compra ya tiene precio en otro evento extraído (merge.py los fusiona por ese enlace).
Prioridad: eventos de los próximos 7 días, luego el resto; tope de --max páginas por ejecución.
"""
import sys, os, re, json, glob, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape import common
from scrape.common import get, ld_json, clean_text, night_date, log, FetchError

TABLE = re.compile(r"mesa|reservad|botella|bottle|table|\bvip\b|\bbox\b|palco|booth|cumplea|parking|guardarropa|cloakroom", re.I)
BLOCKED_HOSTS = ("ra.co", "fourvenues.com", "shotgun.live", "technobeatscloud.com", "ticketmaster.", "atrapalo.", "discotech.me")
GENERIC_HOSTS = ("eventbrite.", "entradium.com", "wegow.com", "geeticket", "oneboxtds", "tomaticket", "woutick", "enterticket",
                 "entradas.conciertos.club", "allevents.in", "eventim-light.com", "ticketclub.es", "tickets.oneboxtds.com")

def host_of(u):
    m = re.match(r"https?://([^/?#]+)", str(u or "").strip(), re.I)
    return m.group(1).lower().replace("www.", "") if m else ""

def n(x):
    try: v = round(float(str(x).replace(",", ".")), 2)
    except (TypeError, ValueError): return None
    return int(v) if v == int(v) else v

def blocked(ex):
    s = str(ex)
    return bool(re.search(r"HTTP (403|429)|challenge|Just a moment|captcha", s, re.I))

def challenge(html):
    return bool(re.search(r"<title>\s*(Just a moment|Attention Required|Checking your browser)", html[:5000], re.I))

# ---------- extracción genérica JSON-LD ----------
def from_ld(html, label):
    """{priceMin, priceMax, priceText, free, status, start(ISO), address, ageMin, url} del primer Event con ofertas del JSON-LD."""
    best = None
    for d in ld_json(html):
        t = d.get("@type"); t = " ".join(t) if isinstance(t, list) else str(t or "")
        if "Event" not in t: continue
        out = {"url": d.get("url"), "startISO": d.get("startDate")}
        loc = d.get("location") or {}
        if isinstance(loc, list): loc = loc[0] if loc else {}
        ad = loc.get("address") if isinstance(loc, dict) else None
        if isinstance(ad, dict) and ad.get("streetAddress"):
            parts = [clean_text(ad.get("streetAddress"))] + [clean_text(ad.get(k) or "") for k in ("postalCode", "addressLocality") if ad.get(k) and str(ad.get(k)) not in str(ad.get("streetAddress"))]
            out["address"] = ", ".join(p for p in parts if p)
        elif isinstance(ad, str) and ad.strip(): out["address"] = clean_text(ad)
        m = re.match(r"\s*(\d{2})", str(d.get("typicalAgeRange") or ""))
        if m: out["ageMin"] = int(m.group(1))
        offers = d.get("offers") or []
        offers = [o for o in (offers if isinstance(offers, list) else [offers]) if isinstance(o, dict)]
        lows, highs, names, avs = [], [], [], []
        for o in offers:
            if TABLE.search(str(o.get("name") or "")): continue
            lo = n(o.get("lowPrice")) if o.get("lowPrice") not in (None, "") else n(o.get("price")) if o.get("price") not in (None, "") else None
            hi = n(o.get("highPrice")) if o.get("highPrice") not in (None, "") else lo
            if lo is None: continue
            lows.append(lo); highs.append(hi if hi is not None else lo)
            if o.get("name"): names.append(f"{clean_text(o['name'])[:40]} {lo:g} €")
            avs.append(str(o.get("availability") or "").rsplit("/", 1)[-1].lower())
        if lows:
            pmin, pmax = min(lows), max(highs)
            free = pmin == 0 or bool(d.get("isAccessibleForFree"))
            txt = " · ".join(dict.fromkeys(names)) if names and len(names) <= 4 else (f"{pmin:g} €" if pmax == pmin else f"{pmin:g} – {pmax:g} €")
            out.update(priceMin=pmin, priceMax=(pmax if pmax > pmin else None), priceText=f"{txt} ({label})"[:120], free=free)
            if avs and all("soldout" in a for a in avs): out["status"] = "agotado"
            elif any("limited" in a for a in avs): out["status"] = "ultimas"
            elif any(a in ("instock", "onlineonly", "presale", "preorder") for a in avs): out["status"] = "disponible"
            return out
        elif d.get("isAccessibleForFree") is True:
            out.update(priceMin=0, priceMax=None, priceText=f"Gratis ({label})", free=True)
            return out
        best = best or out
    return best or {}

# ---------- por ticketera ----------
def h_xceed(url, ev, ctx):
    from scrape.sources import xceed
    det = xceed._detail(url)
    if not det: raise FetchError(f"{url}: sin ficha")
    pmin, pmax, ptxt, free = xceed._price(det.get("offers", []), det.get("free"))
    out = {"address": det.get("address")}
    m = re.match(r"(\d+)", det.get("age") or "")
    if m: out["ageMin"] = int(m.group(1))
    if pmin is not None:
        out.update(priceMin=pmin, priceMax=pmax, priceText=ptxt, free=free)
        gen = [o for o in det.get("offers", []) if isinstance(o.get("price"), (int, float)) and not xceed.TABLE.search(o.get("name") or "")]
        avs = [str(o.get("availability") or "").lower() for o in gen]
        if avs and all("soldout" in a for a in avs): out["status"] = "agotado"
        elif any("instock" in a for a in avs): out["status"] = "disponible"
    return out

def h_dice(url, ev, ctx):
    h = get(url)
    if challenge(h): raise FetchError(f"{url}: challenge")
    out = from_ld(h, "DICE")
    if out.get("priceMin") is not None and out["priceMin"] >= 100 and (ev.get("start") or "23:00") >= "22:00":
        for k in ("priceMin", "priceMax", "priceText"): out.pop(k, None)   # ≥100 € en club: mesa/reservado (igual que dice.py)
    if out.get("url") and "dice.fm/event/" in out["url"]: out["canonical"] = out["url"].split("?")[0]
    return out

def h_whan(url, ev, ctx):
    from scrape.sources import whan
    m = re.search(r"app\.whan\.es/event/([^/?#]+)", url)
    det = get(f"{whan.API}/event/{m.group(1)}?preview=1", json_=True)
    pi = whan.price_info(det)
    out = {"ageMin": pi["ageMin"], "dressCode": pi["dressCode"]}
    if pi["priceMin"] is not None:
        out.update(priceMin=pi["priceMin"], priceMax=pi["priceMax"], priceText=pi["priceText"], free=pi["free"])
    if pi["status"] != "desconocido": out["status"] = pi["status"]
    return out

def h_fever(url, ev, ctx):
    from scrape.sources import fever
    pid = re.search(r"/m/(\d+)", url).group(1)
    h = get(f"{fever.BASE}/m/{pid}/en")
    evs = fever.plan_events(pid, url, h, {}, ctx["today"], ctx["end"])
    best = next((e for _, e in evs if e["date"] == ev["date"]), None)
    if not best: return {}
    out = {k: best.get(k) for k in ("priceMin", "priceMax", "priceText", "free", "status", "start", "address", "ageMin")}
    if best.get("priceMin") is None: out = {k: v for k, v in out.items() if k not in ("priceMin", "priceMax", "priceText", "free")}
    return out

def h_taquilla(url, ev, ctx):
    from scrape.sources import taquilla
    m = re.search(r"[?&]event=(\d+)", url)
    if not m: return {}
    for s in taquilla._sessions(get(url)):
        if s["id"] != m.group(1): continue
        e = taquilla._to_event(s, ctx["lo"], ctx["end"])
        if e and e.get("priceMin") is not None:
            return {k: e.get(k) for k in ("priceMin", "priceMax", "priceText", "free", "status", "start", "address")}
    return {}

def h_patt(url, ev, ctx):
    from scrape.sources import nightlifemadrid as nm
    m = re.search(r"/pass/([0-9a-f]{24})", url)
    if not m: return {}
    return nm.price_info(nm.detail(m.group(1)))

def h_generic(url, ev, ctx):
    h = get(url)
    if challenge(h): raise FetchError(f"{url}: challenge")
    return from_ld(h, label_of(host_of(url)))

def h_madridenvivo(url, ev, ctx):
    """Ficha de Madrid en Vivo -> botón "Comprar entradas" -> ticketera conocida."""
    from scrape.common import soup
    s = soup(get(url))
    buy = next((a.get("href", "").strip() for a in s.select("a") if "comprar" in a.get_text(" ").lower() and a.get("href", "").startswith("http")), None)
    if not buy: return {}
    fn = handler_for(buy)
    if not fn or fn is h_madridenvivo: return {}
    time.sleep(0.4); ctx["pages"] += 1
    out = fn(buy, ev, ctx)
    if out.get("priceMin") is not None: out["canonical"] = buy
    return out

# Techno Airlines y Fulltechno no están: sus fichas enlazan casi siempre a RA (vetada) y gastan presupuesto sin resultado
FOLLOW_HOSTS = {"conciertos.club": r"/conciertos/", "laganzua.net": r"/conciertos/"}
def h_follow(url, ev, ctx):
    """Ficha de un agregador (Conciertos.club, Techno Airlines, Fulltechno, La Ganzúa) -> primer enlace de compra a una ticketera
    conocida (desenvuelve los enlaces de afiliado fever.pxf.io?u=...) -> su manejador."""
    from urllib.parse import urlparse, parse_qs, unquote
    from scrape.common import soup
    s = soup(get(url))
    seen = set()
    for a in s.select("a[href]"):
        href = a.get("href", "").strip()
        if not href.startswith("http"): continue
        if "pxf.io" in href or "u=" in href:
            q = parse_qs(urlparse(href).query).get("u")
            if q: href = unquote(q[0])
        if href in seen: continue
        seen.add(href)
        fn = handler_for(href)
        if not fn or fn in (h_follow, h_madridenvivo): continue
        time.sleep(0.4); ctx["pages"] += 1
        try: out = fn(href, ev, ctx)
        except FetchError: continue
        if out.get("priceMin") is not None or out.get("priceMax") is not None:
            out["canonical"] = href
            return out
        if ctx["pages"] >= ctx.get("maxPages", 10**9): break
    return {}

def label_of(host):
    for k, v in (("eventbrite", "Eventbrite"), ("entradium", "Entradium"), ("wegow", "Wegow"), ("geeticket", "Geeticket"), ("onebox", "Onebox"),
                 ("tomaticket", "Tomaticket"), ("woutick", "Woutick"), ("enterticket", "Enterticket"), ("conciertos.club", "Conciertos.club"),
                 ("allevents", "AllEvents"), ("eventim", "Eventim"), ("ticketclub", "Ticketclub")):
        if k in host: return v
    return host

def handler_for(u):
    h = host_of(u)
    if not h or any(b in h for b in BLOCKED_HOSTS): return None
    if "xceed.me" in h and re.search(r"/madrid/event/[^/]+/\d+", u): return h_xceed     # otra ciudad (xceed.me/es/malaga/…): no
    if h in ("dice.fm", "link.dice.fm") and (h == "link.dice.fm" or "/event/" in u): return h_dice
    if h == "app.whan.es" and "/event/" in u: return h_whan
    if "feverup.com" in h and re.search(r"/m/\d+", u): return h_fever
    if "taquilla.com" in h and "event=" in u: return h_taquilla
    if h == "tickets.nightlifemadrid.com" and "/pass/" in u: return h_patt
    if any(g in h for g in GENERIC_HOSTS) and re.search(r"/(e|event|events|evento|eventos|entrada|entradas|es/events)/|/rest/entrada/", u): return h_generic
    if h == "madridenvivo.com" and "/evento/" in u: return h_madridenvivo
    for fh, pat in FOLLOW_HOSTS.items():
        if h.endswith(fh) and re.search(pat, u): return h_follow
    return None

def apply(ev, info):
    """Copia lo extraído al evento. Devuelve True si gana precio."""
    gained = False
    if info.get("priceMin") is not None or info.get("priceMax") is not None:
        ev["priceMin"], ev["priceMax"] = info.get("priceMin"), info.get("priceMax")
        if ev["priceMin"] is None and ev["priceMax"] is not None: ev["priceMin"], ev["priceMax"] = ev["priceMax"], None
        if info.get("priceText"): ev["priceText"] = info["priceText"][:120]
        ev["free"] = bool(info.get("free")) or ev["priceMin"] == 0
        gained = True
    if info.get("status") in ("disponible", "ultimas", "agotado"): ev["status"] = info["status"]
    if not ev.get("start"):
        st = info.get("start")
        iso = info.get("startISO") or ""
        if not st and "T" in iso and not iso.split("T")[1].startswith(("00:00", "23:59")): st = iso.split("T")[1][:5]
        # solo si la fecha de la ficha corresponde a la noche del evento
        if st and (not iso or night_date(iso[:10], st) == ev["date"]): ev["start"] = st
    if not ev.get("address") and info.get("address"): ev["address"] = info["address"][:160]
    if ev.get("ageMin") is None and isinstance(info.get("ageMin"), int): ev["ageMin"] = info["ageMin"]
    if not ev.get("dressCode") and info.get("dressCode"): ev["dressCode"] = info["dressCode"]
    can = info.get("canonical")
    if can and gained and host_of(ev.get("ticketUrl")) in ("link.dice.fm", "madridenvivo.com"):
        ev["ticketUrl"] = can     # enlace corto de DICE / ficha de agregador -> página de compra del evento
    return gained

def madrid_today():
    from zoneinfo import ZoneInfo
    now = datetime.datetime.now(ZoneInfo("Europe/Madrid"))
    return (now - datetime.timedelta(hours=6)).strftime("%Y-%m-%d")

def main():
    args = sys.argv[1:]
    opt = lambda k, d: args[args.index(k) + 1] if k in args else d
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    data_dir = pos[0] if pos else "run/data"
    maxp = int(opt("--max", "250"))
    rep0 = {}
    try: rep0 = json.load(open(os.path.join(data_dir, "_scrape_report.json")))
    except Exception: pass
    today = opt("--today", None) or rep0.get("today") or madrid_today()
    end = rep0.get("end") or (datetime.date.fromisoformat(today) + datetime.timedelta(days=int(opt("--days", "14")))).isoformat()
    week = (datetime.date.fromisoformat(today) + datetime.timedelta(days=6)).isoformat()
    try:
        import merge as M
        tkey = M.ticket_key
    except Exception:
        tkey = lambda u: (u or "").split("?")[0].rstrip("/").lower() or None
    files = {}
    for f in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        if os.path.basename(f).startswith("_"): continue
        try: files[f] = json.load(open(f))
        except Exception as ex: log("enrich: no se pudo leer", f, ex)
    def urls(e): return [u for u in [e.get("ticketUrl")] + [s.get("url") for s in e.get("sources") or []] if u]
    def has_price(e): return e.get("priceMin") is not None or e.get("priceMax") is not None
    priced = {k for evs in files.values() for e in evs if has_price(e) for k in map(tkey, urls(e)) if k}
    # candidatos agrupados por url (una página sirve a todos los eventos que enlazan a ella)
    groups, skipped_cov, skipped_none = {}, 0, 0
    for f, evs in files.items():
        for e in evs:
            if has_price(e) or not e.get("date") or not (today <= e["date"] <= end): continue
            us = urls(e)
            if any(tkey(u) in priced for u in us if tkey(u)): skipped_cov += 1; continue
            pick = next(((u, fn) for u in us for fn in [handler_for(u)] if fn), None)
            if not pick: skipped_none += 1; continue
            u, fn = pick
            key = (u.split("#")[0], e["date"] if fn is h_fever else None)
            groups.setdefault(key, {"fn": fn, "url": u, "events": [], "date": e["date"]})["events"].append(e)
    lowp = lambda g: g["fn"] is h_madridenvivo
    order = sorted(groups.values(), key=lambda g: (lowp(g), g["date"] > week, g["date"], -len(g["events"])))
    ctx = {"today": today, "end": end, "lo": (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat(), "pages": 0}
    rep = {"today": today, "end": end, "maxPages": maxp, "candidates": sum(len(g["events"]) for g in groups.values()), "urls": len(groups),
           "skippedAlreadyPricedLink": skipped_cov, "skippedNoTicketPage": skipped_none, "attempted": 0, "gained": 0, "statusSet": 0,
           "pages": 0, "byHost": {}, "blockedHosts": []}
    blocks = {}
    for g in order:
        if ctx["pages"] >= maxp: break
        h = host_of(g["url"])
        hr = rep["byHost"].setdefault(h, {"attempted": 0, "gained": 0, "blocked": 0, "errors": 0})
        if blocks.get(h, 0) >= 3: continue
        hr["attempted"] += len(g["events"]); rep["attempted"] += len(g["events"])
        key = "GET " + g["url"]
        if common._cached(key) is None: time.sleep(0.4)
        ctx["pages"] += 1
        try:
            info = g["fn"](g["url"], g["events"][0], ctx) or {}
        except Exception as ex:
            if blocked(ex): blocks[h] = blocks.get(h, 0) + 1; hr["blocked"] += 1
            else: hr["errors"] += 1
            log("enrich:", g["url"][:90], str(ex)[:120]); continue
        for e in g["events"]:
            st0 = e.get("status")
            if apply(e, info): hr["gained"] += 1; rep["gained"] += 1
            elif e.get("status") != st0: rep["statusSet"] += 1
    rep["pages"] = ctx["pages"]
    rep["blockedHosts"] = sorted(h for h, c in blocks.items() if c >= 3)
    for f, evs in files.items():
        json.dump(evs, open(f, "w"), ensure_ascii=False, indent=0)
    json.dump(rep, open(os.path.join(data_dir, "_enrich_report.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ("candidates", "urls", "attempted", "gained", "statusSet", "pages", "skippedAlreadyPricedLink", "skippedNoTicketPage")}, ensure_ascii=False))
    print("por host:", json.dumps({h: (v["attempted"], v["gained"]) for h, v in rep["byHost"].items()}, ensure_ascii=False))

if __name__ == "__main__":
    main()
