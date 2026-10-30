"""Wurlitzer Ballroom (wurlitzerballroom.com/agenda): HTML servido (Next.js) con una tarjeta por concierto (fecha, título, géneros, puertas, precio, enlace de compra);
la ficha propia (/concierto/<slug>) aporta la descripción (JSON-LD MusicEvent)."""
import re, time
from scrape.common import get, soup, ld_json, event, in_window, clean_text, plain, music_tags, MONTHS, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Wurlitzer Ballroom"
MIN_EVENTS = 4
VENUE = "Wurlitzer Ballroom"
ADDRESS = "C/ Tres Cruces 12, 28013 Madrid"
ZONE = "Centro / Sol"
BASE = "https://wurlitzerballroom.com"
MAX_DETAIL = 40

# géneros propios de la sala -> etiquetas de música
EXTRA = [("rock", r"psicodel|psych|garage|post-?punk|shoe-?gaze|noise|hard ?core|stoner|krautrock|grunge|revival|mod\b|new wave|art punk|dream ?pop|rock and roll|avant"),
         ("indie", r"indie|dream ?pop|slowcore"), ("electronica", r"synt|edm|electr"), ("pop", r"\bpop\b"), ("otros", r"folk|americana|country|singer|blues")]

def _music(tags, title):
    txt = " ".join(tags) + " " + title
    out = music_tags(re.sub(r"garage|melodic", " ", plain(txt)))      # "garage" es rock aquí, no house
    p = plain(txt)
    for tag, rx in EXTRA:
        if re.search(rx, p) and tag not in out: out.append(tag)
    if "otros" in out and len(out) > 1: out.remove("otros")
    return out

def _month(label):
    return MONTHS.get(plain(label).strip(". "))

def scrape(today, end):
    try: html = get(BASE + "/agenda")
    except Exception as ex:
        log(NAME, "agenda", ex); return []
    s = soup(html)
    cards, year = [], None
    for el in s.find_all(["h2", "article"]):
        if el.name == "h2":
            m = re.search(r"(\d{4})", el.get_text())
            if m: year = int(m.group(1))
            continue
        if "flyer" not in (el.get("class") or []) or not year: continue
        day = el.select_one("header p.poster")
        mon = day.find("span") if day else None
        if not day or not mon: continue
        dm = re.match(r"\d{1,2}", day.get_text(strip=True))
        mo = _month(mon.get_text())
        if not dm or not mo: continue
        date = f"{year}-{mo:02d}-{int(dm.group(0)):02d}"
        a = el.select_one("h3 a")
        if not a: continue
        sup = el.select_one("p.font-display")
        tags = [clean_text(x.get_text()) for x in el.select("p.tag.mt-3 span")]
        line = el.select_one("p.border-t")
        spans = [clean_text(x.get_text()) for x in line.find_all("span")] if line else []
        doors = next((m.group(1) for x in spans if (m := re.search(r"Puertas\s*(\d{1,2}[:.]\d{2})", x))), None)
        price = next((x for x in spans if "€" in x), None)
        buy = next((b["href"] for b in el.select("a.link-arrow") if b.get("href", "").startswith("http")), None)
        after = el.find("p", string=re.compile(r"After DJ", re.I))
        cards.append(dict(date=date, title=clean_text(a.get_text()), href=a["href"], support=clean_text(sup.get_text()).lstrip("+ ").strip() if sup else "",
                          tags=tags, doors=doors.replace(".", ":") if doors else None, price=price, buy=buy, after=clean_text(after.get_text()) if after else None))
    log(NAME, "tarjetas:", len(cards))
    out, detail = [], 0
    for c in cards:
        if not in_window(c["date"], today, end): continue
        if excluded_title(c["title"], " ".join(c["tags"])): continue
        start = c["doors"]
        if start and start < "20:00": continue
        url = c["href"] if c["href"].startswith("http") else BASE + c["href"]
        desc = None
        if detail < MAX_DETAIL:
            detail += 1
            try:
                for ld in ld_json(get(url)):
                    if "Event" in str(ld.get("@type")) and ld.get("description"):
                        desc = re.sub(r"\s*The Telecopes - Biography & Pre…", "", ld["description"]); break
            except Exception as ex: log(NAME, "ficha", url, ex)
            time.sleep(0.4)
        sup, truncated = c["support"], len(c["support"]) >= 60      # la web recorta el segundo cartel a 60 caracteres
        names = [clean_text(x) for x in re.split(r"\s*\+\s*", c["title"]) if x.strip()]
        sups = [clean_text(x) for x in re.split(r"\s*\+\s*", sup) if x.strip()]
        if truncated and sups: sups = sups[:-1]
        names = [x for x in names if not re.search(r"concierto|fiesta|presenta|\bfest\b|festival", x, re.I)]
        lineup = names + sups if (sups or len(names) > 1) else []
        title = c["title"] + (f" + {sup}" if sup and not truncated else "")
        nums = euro_nums(c["price"]) if c["price"] else []
        pmin = min(nums) if nums else None
        pmax = max(nums) if nums and max(nums) > min(nums) else None
        parts = [f"Puertas {start}." if start else "", (clean_text(desc)[:300] if desc else ""), (c["after"] + "." if c["after"] else "")]
        out.append(event(title=title, date=c["date"], start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type="concierto",
                         music=_music(c["tags"], c["title"]), priceMin=pmin, priceMax=pmax,
                         priceText=c["price"] if nums else None,
                         lineup=lineup, description=(" ".join(x for x in parts if x)[:400] or None),
                         sources=[{"name": NAME, "url": url}], ticketUrl=c["buy"] or url))
    return out
