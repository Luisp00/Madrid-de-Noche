"""Discotech (app.discotech.me/madrid/events): Next.js con SSR; el HTML inicial trae un JSON-LD ItemList (20 eventos por página, ?page=N)
y el flujo RSC (self.__next_f) con datos extra (edad, enlace externo de entradas). Sin precios."""
import re, json
from scrape.common import get, browser, ld_json, event, parse_time, in_window, music_tags, clean_text, night_date, plain, log

NAME = "Discotech"
MIN_EVENTS = 20
URL = "https://app.discotech.me/madrid/events"
MAX_PAGES = 12
BAD = re.compile(r"tributo|tribute|karaoke|stand ?up|monolog|comedia|candlelight|clase|taller|workshop|bingo|shisha|drag show|musical\b", re.I)
VENUE_FIX = {"sala but - mondo disko": "Sala But", "lab madrid": "LAB theCLUB"}

def _page(n):
    url = URL + (f"?page={n}" if n > 1 else "")
    try: html = get(url)
    except Exception:
        html = browser(url, raw=True, wait=10000)
    if "ItemList" not in html:
        html = browser(url, raw=True, wait=10000)
    return html

def _rsc_events(html):
    """Registros 'Event' del flujo RSC de Next: {id: {...}} (ages, has_tickets, external_ticket_url...)."""
    out = {}
    try:
        buf = "".join(json.loads('"' + c + '"') for c in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S))
    except Exception:
        return out
    for m in re.finditer(r'\{"_type":"Event","id":(\d+),', buf):
        i = m.start(); depth = 0
        for j in range(i, min(len(buf), i + 6000)):
            c = buf[j]
            if c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try: out[m.group(1)] = json.loads(buf[i:j + 1])
                    except Exception: pass
                    break
    return out

def scrape(today, end):
    items, extra, seen = [], {}, set()
    for p in range(1, MAX_PAGES + 1):
        try: html = _page(p)
        except Exception as ex: log(NAME, "página", p, ex); break
        page = [x["item"] for d in ld_json(html) if d.get("@type") == "ItemList" for x in d.get("itemListElement", []) if x.get("item")]
        if not page: break
        extra.update(_rsc_events(html))
        items += [i for i in page if i.get("url") not in seen]
        seen.update(i.get("url") for i in page)
        if page[-1]["startDate"][:10] > end: break
    out = []
    for it in items:
        sd = it.get("startDate") or ""
        if "T" not in sd: continue
        title = clean_text(re.sub(r"^\[[^\]]*TAQUILLA\]\s*", "", it.get("name") or "", flags=re.I))
        desc = clean_text(it.get("description") or "")
        loc = it.get("location") or {}
        venue = VENUE_FIX.get(plain(loc.get("name")), clean_text(loc.get("name") or ""))
        if not title or not venue or BAD.search(title) or BAD.search(desc[:200]): continue
        start = sd.split("T")[1][:5]
        date = night_date(sd[:10], start)
        if not in_window(date, today, end): continue
        pl = plain(title + " " + desc)
        if start < "17:00" or (start < "20:00" and not re.search(r"tardeo|festival|fest\b|hallowfest|weekender|party|fiesta|after", pl)): continue
        ad = loc.get("address") or {}
        street = clean_text(ad.get("streetAddress") or "")
        address = ", ".join(x for x in [street, clean_text(" ".join(y for y in [ad.get("postalCode"), ad.get("addressLocality")] if y))] if x) or None
        ed = it.get("endDate") or ""
        endt = ed.split("T")[1][:5] if "T" in ed else None
        age = None
        m = re.search(r"\b(1[68]|2[01])\s*\+", desc)
        ex = extra.get(re.search(r"/events/(\d+)", it.get("url", "")).group(1) if re.search(r"/events/(\d+)", it.get("url", "")) else "", {})
        if m: age = int(m.group(1))
        elif ex.get("ages"):
            m = re.search(r"(\d{2})", str(ex["ages"])); age = int(m.group(1)) if m else None
        ticket = ex.get("external_ticket_url") if ex.get("has_tickets") and ex.get("external_ticket_url") else it.get("url")
        dur = None
        if endt:
            h1, m1 = map(int, start.split(":")); h2, m2 = map(int, endt.split(":"))
            dur = ((h2 * 60 + m2) - (h1 * 60 + m1)) % 1440
        typ = ("tardeo" if "tardeo" in pl else "after" if re.search(r"\bafter(party|\b)", pl) else "festival" if re.search(r"festival|hallowfest", plain(title))
               else "concierto" if (dur is not None and dur <= 240 and start < "22:00") or re.search(r"concierto|en concierto", pl) and not re.search(r"\bdj\b|fiesta|party", pl) else "club")
        desc_s = re.sub(r"\s*This is an? \d+\+ event\.?", "", desc).strip()[:400] or None
        out.append(event(title=title, date=date, start=start, end=endt, venue=venue, address=address, type=typ,
                         music=music_tags(title + " " + desc_s if desc_s else title), ageMin=age, description=desc_s,
                         sources=[{"name": NAME, "url": it["url"]}], ticketUrl=ticket))
    return out
