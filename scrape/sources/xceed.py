"""Xceed (xceed.me): la web (Next.js) lee de un API JSON público, https://event-b2c.xceed.me/v2/events (cities[]=madrid,
orderBy=date, paginado con offset), que devuelve nombre, slug, id, inicio/fin (epoch), sala y géneros. Sin precio: este se
toma de la ficha https://xceed.me/es/madrid/event/{slug}/{id} (JSON-LD Event con ofertas, edad; el HTML trae vestimenta y la
dirección sale del JSON-LD de la sala). Basta common.get, no hace falta navegador."""
import re, json, time, datetime
from zoneinfo import ZoneInfo
from scrape.common import get, ld_json, soup, event, in_window, music_tags, clean_text, night_date, plain, log

NAME = "Xceed"
MIN_EVENTS = 10
API = "https://event-b2c.xceed.me/v2/events"
MADRID = ZoneInfo("Europe/Madrid")
MAX_DETAIL = 58
EXCLUDE = re.compile(r"\b(tribut[eo]s?|tribute|karaoke|stand ?up|monologo|monólogo|comedia|comedy|musical|candlelight|clase|clases|workshop|taller|cena|cenas|teatro|brunch|escape|vip sin esperas|cocktail class)\b", re.I)
TABLE = re.compile(r"mesa|reservado|botella|bottle|table|vip|box|palco|cumplea", re.I)

def _local(ts):
    return datetime.datetime.fromtimestamp(ts, MADRID)

def _list(today, end):
    t0 = datetime.datetime.combine(datetime.date.fromisoformat(today) - datetime.timedelta(days=1), datetime.time(12, 0), MADRID)
    limit_dt = datetime.datetime.combine(datetime.date.fromisoformat(end) + datetime.timedelta(days=1), datetime.time(7, 0), MADRID)
    items, offset = [], 0
    while True:
        q = f"{API}?cities[]=madrid&limit=24&offset={offset}&startTime={int(t0.timestamp())}&orderBy=date&sort=ASC"
        try: data = get(q, json_=True)["data"]
        except Exception as ex: log(NAME, "api", offset, ex); break
        page = data.get("items", [])
        if not page: break
        items.extend(page)
        if _local(page[-1]["startingTime"]) > limit_dt or len(items) >= data.get("meta", {}).get("total", 0): break
        offset += 24
        time.sleep(0.3)
    return [i for i in items if _local(i["startingTime"]) <= limit_dt]

def _detail(url):
    out = {}
    try: h = get(url)
    except Exception as ex: log(NAME, "detalle", url, ex); return out
    for d in ld_json(h):
        if d.get("@type") == "Event":
            out["age"] = d.get("typicalAgeRange")
            out["free"] = d.get("isAccessibleForFree")
            offers = d.get("offers") or []
            out["offers"] = [o for o in (offers if isinstance(offers, list) else [offers]) if isinstance(o, dict)]
            ad = ((d.get("location") or {}).get("address") or {})
            if isinstance(ad, dict) and ad.get("streetAddress"): out["address"] = clean_text(ad["streetAddress"])
            desc = clean_text(d.get("description") or "")
            if desc: out["desc"] = desc[:400]
    s = soup(h)
    for t in s(["script", "style"]): t.decompose()
    txt = clean_text(s.get_text(" "))
    m = re.search(r"Vestimenta\s+(.+?)\s+(?:Apertura de puertas|Edad m[ií]n|Ubicaci[oó]n)", txt)
    if m and len(m.group(1)) < 80: out["dress"] = m.group(1)
    m = re.search(r"Apertura de puertas\s+(\d{1,2}:\d{2})", txt)
    if m: out["doors"] = m.group(1)
    return out

def _price(offers, free_flag):
    gen = [o for o in offers if isinstance(o.get("price"), (int, float)) and not TABLE.search(o.get("name") or "")]
    if not gen:
        return (0, None, "Gratis", True) if free_flag else (None, None, None, False)
    av = [o for o in gen if "soldout" not in str(o.get("availability") or "").lower()]
    pool = av or gen                      # si todo está agotado se informa igualmente del precio
    prices = sorted(o["price"] for o in pool)
    pmin, pmax = prices[0], prices[-1]
    def n(x): return int(x) if x == int(x) else round(x, 2)
    pmin, pmax = n(pmin), n(pmax)
    txt = " · ".join(dict.fromkeys(f"{clean_text(o.get('name') or 'Entrada')}" + ("" if re.search(r"\d\s*€", o.get("name") or "") else f" {n(o['price'])} €") for o in pool))
    if av and any(o["price"] == 0 for o in gen if o not in av): txt = "Lista gratis agotada · " + txt   # la lista gratis se acabó: manda lo que queda
    return pmin, (pmax if pmax > pmin else None), txt[:120], pmin == 0

def scrape(today, end):
    items = _list(today, end)
    cands = []
    for it in items:
        v = it.get("venue") or {}
        if it.get("venueIsSecret") or not v.get("name") or (v.get("city") or {}).get("slug") != "madrid": continue
        ldt = _local(it["startingTime"])
        start = ldt.strftime("%H:%M")
        date = night_date(ldt.date().isoformat(), start)
        if not in_window(date, today, end): continue
        if EXCLUDE.search(it["name"]): continue
        cands.append((it, v, date, start, ldt))
    out, ndet = [], 0
    for it, v, date, start, ldt in cands:
        url = f"https://xceed.me/es/madrid/event/{it['slug']}/{it['legacyId']}"
        det = {}
        if ndet < MAX_DETAIL:
            det = _detail(url); ndet += 1; time.sleep(0.4)
        endt = _local(it["endingTime"]).strftime("%H:%M") if it.get("endingTime") else None
        pmin, pmax, ptxt, free = _price(det.get("offers", []), det.get("free"))
        age = None
        m = re.match(r"(\d+)", det.get("age") or "")
        if m: age = int(m.group(1))
        genres = " ".join(g.get("name", "") for g in it.get("musicGenres", []))
        music = music_tags(genres) or music_tags(it["name"])
        typ = "tardeo" if "06:00" <= start < "20:00" else "club"
        out.append(event(title=clean_text(it["name"]), date=date, start=start, end=endt, venue=clean_text(v["name"]), address=det.get("address"),
                         type=typ, music=music, priceMin=pmin, priceMax=pmax, priceText=ptxt, free=free, dressCode=det.get("dress"),
                         ageMin=age, lineup=[l.get("name") for l in it.get("lineup", []) if isinstance(l, dict) and l.get("name")][:12],
                         description=det.get("desc"), sources=[{"name": NAME, "url": url}], ticketUrl=url))
    log(NAME, f"{len(items)} del API, {len(cands)} candidatos, {ndet} fichas, {len(out)} salida")
    return out
