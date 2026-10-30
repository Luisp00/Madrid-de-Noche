"""Techno Airlines (technoairlines.com): guía de electrónica. Los listados mensuales /events/madrid/AAAA-MM son HTML servido
por el servidor (basta common.get). Cada fila trae fecha (en el slug), título, sala, hora y line-up parcial; las páginas
/club/{slug} traen dirección (JSON-LD NightClub) y la lista de sus próximos eventos con enlace de compra (RA/DICE/...);
las fichas /event/{slug} dan el enlace de compra y el line-up completo para el resto. Sin precio en ninguna página."""
import re, time, datetime
from scrape.common import get, soup, ld_json, event, parse_time, in_window, music_tags, clean_text, night_date, plain, log

NAME = "Techno Airlines"
MIN_EVENTS = 40
BASE = "https://www.technoairlines.com"
MAX_DETAIL = 40
CONCERT_VENUES = ("wagon", "la riviera", "las ventas", "conde duque", "cafe berlin", "sala sol", "el sol", "moby dick", "sala but concierto")
SKIP_VENUE = re.compile(r"powered by|^(madrid|tba|secret location|tbc|por anunciar|spain)$|secret location|\btba\b", re.I)

def _month_urls(today, end):
    d = datetime.date.fromisoformat(today).replace(day=1)
    e = datetime.date.fromisoformat(end)
    out = []
    while d <= e:
        out.append(f"{BASE}/events/madrid/{d:%Y-%m}")
        d = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return out

def _real_time(t):
    return None if (not t or t == "23:59") else t

def _clubs():
    """{plain(nombre): {url, address, events:{event_url: ticket_url}}} desde las fichas de club enlazadas en el listado."""
    html = get(f"{BASE}/events/madrid")
    urls = sorted({a["href"].split("?")[0] for a in soup(html).select("a[href*='/club/']")})
    clubs = {}
    for u in urls:
        try: h = get(u)
        except Exception as ex: log(NAME, "club", u, ex); continue
        info = {"url": u, "address": None, "name": None, "events": {}}
        for d in ld_json(h):
            if d.get("@type") == "NightClub":
                info["name"] = d.get("name")
                ad = d.get("address") or {}
                if isinstance(ad, dict): info["address"] = clean_text(ad.get("streetAddress")) or None
            elif d.get("@type") == "ItemList":
                for it in d.get("itemListElement", []):
                    ev = it.get("item") or {}
                    off = ev.get("offers") or {}
                    if ev.get("url"): info["events"][ev["url"]] = {"ticket": off.get("url") if isinstance(off, dict) else None,
                                                                    "performers": [p.get("name") for p in ev.get("performer", []) if isinstance(p, dict) and p.get("name")],
                                                                    "end": ev.get("endDate")}
        if info["name"]: clubs[plain(info["name"])] = info
        time.sleep(0.4)
    return clubs

def _rows(today, end):
    rows, seen = [], set()
    for mu in _month_urls(today, end):
        try: html = get(mu)
        except Exception as ex: log(NAME, "listado", mu, ex); continue
        for li in soup(html).select("li.tev-row"):
            a = li.select_one("a.tev-tt")
            if not a: continue
            url = a["href"].split("?")[0]
            m = re.search(r"(\d{4}-\d{2}-\d{2})$", url)
            if not m or url in seen or "/event/" not in url: continue
            date = m.group(1)
            if not in_window(date, today, (datetime.date.fromisoformat(end) + datetime.timedelta(days=1)).isoformat()): continue
            seen.add(url)
            small = li.select_one("small")
            venue, tm = None, None
            if small:
                t = clean_text(small.get_text())
                mm = re.match(r"(.+?)\s*·\s*(\d{1,2}:\d{2})$", t)
                if mm: venue, tm = clean_text(mm.group(1)), mm.group(2)
                else: venue = t
            ln = li.select_one(".tev-ln")
            rows.append({"url": url, "date": date, "title": clean_text(a.get_text()), "venue": venue, "time": tm,
                         "lineup_txt": clean_text(ln.get_text()) if ln else "", "big": "is-big" in li.get("class", [])})
    return rows

def _detail(url):
    out = {}
    try: h = get(url)
    except Exception as ex: log(NAME, "detalle", url, ex); return out
    for d in ld_json(h):
        if d.get("@type") in ("MusicEvent", "Event"):
            off = d.get("offers") or {}
            out["ticket"] = off.get("url") if isinstance(off, dict) else None
            out["performers"] = [p.get("name") for p in d.get("performer", []) if isinstance(p, dict) and p.get("name")]
            out["start"], out["end"] = d.get("startDate"), d.get("endDate")
    return out

def scrape(today, end):
    clubs = _clubs()
    rows = _rows(today, end)
    out, ndet = [], 0
    for r in rows:
        venue = r["venue"]
        if not venue or SKIP_VENUE.search(venue): continue
        pv = plain(venue)
        club = clubs.get(pv)
        info = club["events"].get(r["url"]) if club else None
        det = {}
        if info is None and ndet < MAX_DETAIL:
            det = _detail(r["url"]); ndet += 1; time.sleep(0.4)
        elif info: det = {"ticket": info["ticket"], "performers": info["performers"], "end": info["end"]}
        start = _real_time(parse_time(r["time"]) if r["time"] else None)
        endt = None
        if start and det.get("end") and "T" in det["end"]: endt = det["end"].split("T")[1][:5]
        title = r["title"]
        if re.search(r"\b(tribut[eo]|karaoke|workshop|masterclass|clase)\b", plain(title)): continue
        if any(c in pv for c in CONCERT_VENUES) and start and start < "20:00": continue
        date = night_date(r["date"], start) if start else r["date"]
        if not in_window(date, today, end): continue
        lineup = det.get("performers") or [x.strip() for x in r["lineup_txt"].split(",") if x.strip() and not re.match(r"^\+\d+ more$", x.strip())]
        lineup = [x for x in lineup if not re.match(r"^\+\d+", x)]
        typ = "club"
        if start and "06:00" <= start < "20:00":
            typ = "festival" if re.search(r"festival|takeover|open air", plain(title)) else "tardeo"
        elif any(c in pv for c in CONCERT_VENUES): typ = "concierto"
        music = music_tags(title) or ["electronica"]
        ticket = det.get("ticket") or r["url"]
        out.append(event(title=title, date=date, start=start, end=endt, venue=venue, address=club["address"] if club else None,
                         type=typ, music=music, lineup=lineup[:12], sources=[{"name": NAME, "url": r["url"]}], ticketUrl=ticket))
    log(NAME, f"{len(rows)} filas, {ndet} fichas, {len(clubs)} clubs, {len(out)} eventos")
    return out
