"""Technoparty (technoparty.es): agenda de techno/electrónica. El listado /agenda/madrid/?pag=N trae título, sala, DJs, estilos y las sesiones
(data-vivo = [[inicio_epoch, fin_epoch], ...]); la ficha aporta dirección (JSON-LD), edad mínima, dress code, descripción y line-up. No publica precios."""
import re, json, time, datetime
from scrape.common import get, soup, ld_json, event, in_window, music_tags, clean_text, night_date, parse_date, log

NAME = "Technoparty"
MIN_EVENTS = 5
LIST_URL = "https://technoparty.es/agenda/madrid/"
MAX_PAGES = 30
MAX_DETAIL = 150
NOT_MADRID = re.compile(r"barcelona|valencia|sevilla|bilbao|ibiza", re.I)
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Madrid")
except Exception:
    _TZ = None

def _local(ts):
    d = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    if _TZ: return d.astimezone(_TZ)
    # sin tzdata: CET/CEST aproximado (último domingo de marzo a último domingo de octubre)
    off = 2 if datetime.datetime(d.year, 3, 25) <= d.replace(tzinfo=None) < datetime.datetime(d.year, 10, 25) else 1
    return d + datetime.timedelta(hours=off)

def _venue_name(n):
    n = re.sub(r"^(?:TBA|TBC)\s*[–-]\s*", "", clean_text(n))
    n = re.sub(r"\s+[–-]\s+Madrid$", "", n)
    return n.title() if n.isupper() and len(n) > 4 else n

GENRES = {"hard techno": "hardtechno", "hard dance": "hardtechno", "hard groove": "techno", "hard bounce": "hardtechno", "acid techno": "techno", "hardcore": "hardtechno",
          "schranz": "hardtechno", "industrial": "hardtechno", "afro house": "afro", "afro tech": "afro", "amapiano": "afro", "música electrónica": "electronica",
          "edm": "electronica", "trance": "electronica", "psytrance": "electronica", "breakbeat": "electronica", "electro": "electronica", "drum and bass": "dnb",
          "disco": "disco", "nu-disco": "disco", "remember": "remember", "indie dance": "indie", "latin tech": "latino", "uk garage": "house", "bakalao": "remember"}

def _music(pills, title):
    out = []
    for g in pills:
        k = g.lower()
        tags = [GENRES[k]] if k in GENRES else (["techno", "house"] if k in ("tech house", "melodic techno", "melodic house") else music_tags(g))
        if k in ("tech house", "melodic house") : tags = ["house", "techno"]
        for t in tags:
            if t not in out: out.append(t)
    return out or music_tags(title)

def _etype(tipo, horario, start):
    t = (tipo or "").lower(); h = (horario or "").lower()
    if "bar" == t: return "bar"
    if "festival" in t or t == "open air": return "festival"
    if "after" in t or "matinal" in h or "mañaneo" in h: return "after"
    if "tardeo" in h or (start and "12:00" <= start < "20:00"): return "tardeo"
    if t in ("boat party", "pool party", "rooftop", "playa", "íntima"): return "fiesta"
    return "club"

def scrape(today, end):
    cards = {}
    for p in range(1, MAX_PAGES + 1):
        url = LIST_URL + (f"?pag={p}" if p > 1 else "")
        try: html = get(url)
        except Exception as ex: log(NAME, "listado", url, ex); break
        arts = soup(html).select("article.t26-ft")
        new = [a for a in arts if a.get("data-id") not in cards]
        if not new: break
        for a in new: cards[a["data-id"]] = a
        if p > 1:   # la 1ª página mezcla destacados; a partir de la 2ª el orden es cronológico
            last = None
            for a in new:
                v = json.loads(a.get("data-vivo") or "[]")
                if v: last = _local(v[0][0]).date().isoformat()
            if last and last > end: break
    out, dedup, nfetch = [], set(), 0
    addr_by_venue, venue_of = {}, {}
    for a in cards.values():
        try:
            t = a.select_one("a.t26-ft__t"); url = t["href"].split("?")[0]
            loc = clean_text((a.select_one(".t26-ft__l") or a).get_text())
            city = loc.split("·")[-1].strip() if "·" in loc else ""
            if NOT_MADRID.search(loc): continue
            sessions = []
            for s, e in json.loads(a.get("data-vivo") or "[]"):
                ls, le = _local(s), _local(e)
                sessions.append((ls.date().isoformat(), ls.strftime("%H:%M"), le.strftime("%H:%M")))
            if not sessions:
                d = parse_date(a.get("data-fecha", "").split(" ", 1)[-1], today)
                if d: sessions = [(d, None, None)]
            sessions = [(night_date(d, st) if st else d, st, en) for d, st, en in sessions]
            sessions = [x for x in sessions if in_window(x[0], today, end)]
            if not sessions: continue
            card = {"title": clean_text(t.get_text()), "sub": clean_text((a.select_one(".t26-ft__s") or t).get_text()) if a.select_one(".t26-ft__s") else None,
                    "venue": clean_text((a.select_one(".t26-ft__club span") or a).get_text()) if a.select_one(".t26-ft__club span") else loc.split("·")[0].strip(),
                    "djs": [x.strip() for x in (a.select_one(".t26-ft__dj").get_text() if a.select_one(".t26-ft__dj") else "").split("·") if x.strip()],
                    "pills": [clean_text(x.get_text()) for x in a.select(".t26-pil")],
                    "ticket": (a.select_one("a.t26-entradas") or {}).get("href") if a.select_one("a.t26-entradas") else None}
            det = {}
            if nfetch < MAX_DETAIL:
                nfetch += 1; time.sleep(0.4)
                try: det = detail(url)
                except Exception as ex: log(NAME, "detalle", url, ex)
            if not sessions[0][1] and det.get("start"):   # sin sesión en el listado: hora del JSON-LD
                d0 = det["date"]; sessions = [(night_date(d0, det["start"]), det["start"], det.get("end"))]
                sessions = [x for x in sessions if in_window(x[0], today, end)]
            venue = _venue_name(det.get("venue") or card["venue"])
            addr = det.get("address")
            vkey = (a.select_one(".t26-ft__l") or {}).get("href") if a.select_one(".t26-ft__l") else venue
            if addr: addr_by_venue.setdefault(vkey, addr)
            if (not venue or venue.lower() in ("tba", "madrid", "por anunciar") or venue.lower().startswith("powered by") or NOT_MADRID.search(venue)
                    or (addr and (NOT_MADRID.search(addr) or re.search(r"\bcarrer\b|\b08\d{3}\b", addr, re.I)))): continue
            if re.search(r"tribut", card["title"], re.I): continue
            title = card["title"]
            if card["sub"] and card["sub"].lower() not in title.lower() and len(card["sub"]) < 60 and card["sub"] not in card["djs"]: title += " · " + card["sub"]
            lineup = det.get("lineup") or card["djs"]
            for d, st, en in sessions:
                if st and "06:00" <= st < "20:00" and en and "06:00" <= en <= "23:00": continue   # sesiones de tarde breves: no son ocio nocturno
                k = (card["title"].lower(), d, venue.lower())
                if k in dedup: continue
                dedup.add(k)
                tk = card["ticket"] if card["ticket"] and card["ticket"].startswith("http") else url
                venue_of[len(out)] = vkey
                out.append(event(title=title, date=d, start=st, end=en, venue=venue, address=addr, type=_etype(det.get("tipo"), det.get("horario"), st),
                                 music=_music(card["pills"], title), dressCode=det.get("dress"), ageMin=det.get("age"), lineup=lineup[:12],
                                 description=det.get("desc"), sources=[{"name": NAME, "url": url}], ticketUrl=tk))
        except Exception as ex:
            log(NAME, "tarjeta", ex)
    for i, e in enumerate(out):      # dirección conocida de la sala para las fichas que no se descargaron
        if not e["address"]: e["address"] = addr_by_venue.get(venue_of.get(i))
    return out

def detail(url):
    html = get(url)
    d = {}
    for x in ld_json(html):
        if x.get("@type") in ("MusicEvent", "Event"):
            sd = x.get("startDate") or ""
            if "T" in sd: d["date"], d["start"] = sd[:10], sd.split("T")[1][:5]
            ed = x.get("endDate") or ""
            if "T" in ed: d["end"] = ed.split("T")[1][:5]
            loc = x.get("location") or {}
            if isinstance(loc, dict):
                if loc.get("name"): d["venue"] = loc["name"]
                ad = loc.get("address") or {}
                if isinstance(ad, dict):
                    street = ad.get("streetAddress") or ""
                    if street and street.lower() != "madrid":
                        parts = [street, (ad.get("postalCode") or "")]
                        d["address"] = ", ".join(p for p in parts if p) + (" Madrid" if ad.get("postalCode") else ", Madrid")
            perf = x.get("performer") or []
            perf = perf if isinstance(perf, list) else [perf]
            d["lineup"] = [p.get("name") for p in perf if isinstance(p, dict) and p.get("name")]
            break
    txt = clean_text(soup(html).get_text(" "))
    m = re.search(r"Dress code\s*(.*?)\s*Ambiente", txt)
    if m and m.group(1).strip() not in ("—", "", "Sin código / Libre"): d["dress"] = m.group(1).strip()[:80]
    m = re.search(r"Edad mínima\s*\+?(\d{2})", txt)
    if m: d["age"] = int(m.group(1))
    m = re.search(r"Tipo de evento\s*(.*?)\s*Horario\s*(\w+)", txt)
    if m: d["tipo"], d["horario"] = m.group(1).strip(), m.group(2)
    m = re.search(r"\bInfo\s+(.{20,}?)(?:\s+Cartel e información|\s+Dónde\b|\s+Próximos eventos|$)", txt)
    if m: d["desc"] = m.group(1).strip()[:400]
    return d
