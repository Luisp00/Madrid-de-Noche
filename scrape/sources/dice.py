"""DICE (dice.fm): /browse/madrid-<id>?from=D&until=D devuelve por servidor un __NEXT_DATA__ con todos los eventos del día
(nombre, sala+dirección, fecha/hora locales, estado, precio en céntimos). Una petición por día (el listado sin fecha solo
trae 30 eventos y no pagina). Para los eventos nocturnos se completa con la ficha /event/{id} (JSON-LD MusicEvent:
precio mínimo/máximo, descripción, URL canónica). Basta common.get, no hace falta navegador."""
import re, json, time, datetime
from scrape.common import get, ld_json, event, parse_time, in_window, music_tags, clean_text, night_date, plain, log

NAME = "DICE"
MIN_EVENTS = 15
BROWSE = "https://dice.fm/browse/madrid-5d8cef380de1e404dc962211"
MAX_DETAIL = 45
EXCLUDE = re.compile(r"\b(tribut[eo]s?|tribute|karaoke|stand ?up|monologo|monólogo|comedia|comedy|musical|candlelight|clase|clases|workshop|taller|cena|cenas|teatro|magia|kids|infantil|brunch)\b", re.I)
PARTYISH = re.compile(r"tardeo|sesi[oó]n|session|party|fiesta|dj|open air|festival|bacalao|avispero|afterwork|after", re.I)
NIGHT_VENUES = ("club", "siroco", "sotano", "independance", "bassement", "specka", "cadavra", "lula", "kapital", "magno", "mondo", "lab ", "goya", "fabrik", "sol", "sala but", "berlin", "hangar", "nazca", "strong", "core", "barcelo", "joy eslava", "shoko", "stardust", "wagon", "villanos", "cuatro")
CONCERT_VENUES = ("riviera", "las ventas", "copernico", "clamores", "chango", "wagon", "palma", "autocine", "sala b", "caracol", "moby dick", "vesta", "galileo galilei", "cafe berlin", "but")

def _next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1))["props"]["pageProps"] if m else {}

def _hhmm(iso):
    return iso[11:16] if iso and len(iso) >= 16 else None

def _euros(c):
    if c is None: return None
    v = c / 100
    return int(v) if v == int(v) else round(v, 2)

def _detail(eid):
    out = {}
    try: h = get(f"https://dice.fm/event/{eid}")
    except Exception as ex: log(NAME, "detalle", eid, ex); return out
    for d in ld_json(h):
        if d.get("@type") in ("MusicEvent", "Event"):
            out["url"] = d.get("url")
            out["desc"] = clean_text(d.get("description") or "")[:400] or None
            off = d.get("offers") or {}
            if isinstance(off, dict) and off.get("lowPrice") is not None:
                try: out["low"], out["high"] = float(off["lowPrice"]), float(off.get("highPrice", off["lowPrice"]))
                except ValueError: pass
            out["performers"] = [p.get("name") for p in d.get("performer", []) if isinstance(p, dict) and p.get("name")]
    return out

def scrape(today, end):
    t0, e1 = datetime.date.fromisoformat(today), datetime.date.fromisoformat(end) + datetime.timedelta(days=1)
    raw, d = {}, t0
    while d <= e1:
        ds = d.isoformat()
        try: pp = _next_data(get(f"{BROWSE}?from={ds}&until={ds}"))
        except Exception as ex: log(NAME, "día", ds, ex); pp = {}
        for e in pp.get("events", []): raw[e["id"]] = e
        d += datetime.timedelta(days=1)
    cands = []
    for e in raw.values():
        if not e.get("venues"): continue
        v = e["venues"][0]
        st = e["dates"]["event_start_date"]
        start = _hhmm(st)
        if start == "23:59": start_real = None
        else: start_real = start
        date = night_date(st[:10], start)
        if not in_window(date, today, end): continue
        name = clean_text(e["name"]).replace("[ENTRADAS EN TAQUILLA] ", "")
        vn = clean_text(v["name"]); pv = plain(vn)
        if EXCLUDE.search(name) or re.search(r"\bteatro\b", pv) and not re.search(r"kapital|barcelo|magno|eslava", pv): continue
        if start < "20:00" and start >= "06:00":
            if not (PARTYISH.search(name) or any(k in pv for k in NIGHT_VENUES)) or any(k == pv or k in pv.split() for k in ("riviera", "copernico", "clamores", "chango")): continue
        cands.append((e, v, name, vn, date, start, start_real))
    # fichas: primero las sesiones tardías (más probables de ser club), hasta MAX_DETAIL
    order = sorted(cands, key=lambda c: (c[5] < "22:00" and c[5] >= "06:00", c[4]))
    det = {}
    for c in order[:MAX_DETAIL]:
        det[c[0]["id"]] = _detail(c[0]["id"]); time.sleep(0.4)
    out = []
    for e, v, name, vn, date, start, start_real in cands:
        dt = det.get(e["id"], {})
        endt = _hhmm(e["dates"].get("event_end_date"))
        pr = e.get("price") or {}
        pmin = pmax = None
        if dt.get("low") is not None: pmin, pmax = dt["low"], dt["high"]
        elif pr.get("amount") is not None: pmin = _euros(pr["amount"])
        elif pr.get("amount_from") is not None: pmin = _euros(pr["amount_from"])
        if pmin is not None:
            pmin = int(pmin) if float(pmin) == int(pmin) else pmin
            if pmax is not None: pmax = int(pmax) if float(pmax) == int(pmax) else pmax
            if pmax is not None and pmax <= pmin: pmax = None
            if pmin >= 100 and start >= "22:00":   # >=100 € en una sesión de club suele ser mesa/reservado, no entrada general
                pmin = pmax = None
        if pmin is None: ptxt = None
        elif pmin == 0: ptxt = "Gratis" if not pmax else f"Gratis - {pmax} €"
        elif pmax: ptxt = f"{pmin} - {pmax} € (DICE)"
        elif dt.get("low") is None and pr.get("amount") is None: ptxt = f"Desde {pmin} € (DICE)"
        else: ptxt = f"{pmin} € (DICE)"
        url = dt.get("url") or f"https://dice.fm/event/{e['id']}"
        typ = "club"
        if "06:00" <= start < "20:00": typ = "tardeo"
        elif start < "06:00" or start >= "22:00": typ = "club"
        else: typ = "concierto"   # 20:00-21:59: sesión de concierto (los DJ de club empiezan más tarde)
        stt = {"sold-out": "agotado", "on-sale": "disponible"}.get(e.get("status"), "desconocido")
        out.append(event(title=name, date=date, start=start_real, end=endt, venue=vn, address=v.get("address"), type=typ,
                         music=music_tags(name + " " + (dt.get("desc") or "")), priceMin=pmin, priceMax=pmax, priceText=ptxt,
                         free=(pmin == 0), lineup=dt.get("performers", [])[:12], description=dt.get("desc"), status=stt,
                         sources=[{"name": NAME, "url": url}], ticketUrl=url))
    log(NAME, f"{len(raw)} eventos brutos, {len(cands)} candidatos, {len(det)} fichas, {len(out)} salida")
    return out
