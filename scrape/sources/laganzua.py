"""La Ganzúa (laganzua.net): listado paginado con JSON-LD MusicEvent por tarjeta (fecha+hora, sala, precio); la ficha añade la dirección de la sala."""
import re, time, json, datetime
from scrape.common import get, soup, event, in_window, clean_text, plain, night_date, music_tags, log
from scrape.sources._filtros import excluded_venue, excluded_title

NAME = "La Ganzúa"
MIN_EVENTS = 15
URLS = ["https://www.laganzua.net/conciertos/madrid"] + [f"https://www.laganzua.net/conciertos/madrid-pagina-{i}" for i in range(2, 7)]
MAX_DETAIL = 60

# género de La Ganzúa -> etiquetas de música
GENRE_RULES = [("hardtechno", r"hard ?techno"), ("techno", r"techno"), ("house", r"\bhouse\b"), ("electronica", r"electr|\bedm\b|synth|dance"),
               ("hiphop", r"hip ?hop|\brap\b"), ("trap", r"\btrap\b"), ("reggaeton", r"regg?aet"), ("urban", r"urban"), ("rnb", r"rhythm|r&b|\brnb\b|blues"),
               ("indie", r"indie"), ("rock", r"rock|punk|metal|grunge|hardcore|garage"), ("pop", r"\bpop\b"), ("latino", r"latin|salsa|bachata"),
               ("disco", r"funk|soul|disco"), ("flamenco", r"flamenc"), ("dancehall", r"dancehall"), ("dnb", r"drum|jungle")]

def genres_to_music(genres):
    p = plain(genres)
    out = []
    for tag, rx in GENRE_RULES:
        if re.search(rx, p) and tag not in out: out.append(tag)
    return out or ["otros"]

def scrape(today, end):
    cards, seen = [], set()
    for u in URLS:
        try: html = get(u)
        except Exception as ex:
            log(NAME, "listado", u, ex); break
        s = soup(html)
        lis = s.select("li[data-date]")
        if not lis: break
        last = ""
        for li in lis:
            last = li["data-date"][:10]
            cid = li.get("id")
            if cid in seen: continue
            seen.add(cid)
            ld = None
            sc = li.find("script", type="application/ld+json")
            if sc:
                try: ld = json.loads(sc.string or sc.get_text())
                except Exception: ld = None
            a = li.select_one("h2 a")
            if not a: continue
            genre = clean_text((li.select_one("p.datosp") or li).get_text()).lstrip("| ").strip()
            cards.append(dict(dt=li["data-date"], ld=ld or {}, url=a["href"], name=clean_text(a.get_text()), genre=genre))
        if last > end: break
    log(NAME, "tarjetas:", len(cards))

    sel = []
    for c in cards:
        date, tm = c["dt"][:10], c["dt"][11:16]
        if not in_window(date, today, end): continue
        ld = c["ld"]
        title = clean_text(ld.get("name") or re.sub(r"\s+en Madrid$", "", c["name"]))
        loc = ld.get("location") or {}
        venue = clean_text(loc.get("name") or "")
        if not venue or plain(venue) == "madrid": continue
        start = None if tm in ("23:59", "00:00") else tm
        electronic = bool(re.search(r"electr|techno|house|\bdj\b|dance", plain(c["genre"] + " " + title)))
        if excluded_venue(venue) or excluded_title(title, c["genre"]): continue
        if start and start < "20:00" and not electronic: continue
        if not start: continue  # sin hora publicada no podemos asegurar que sea nocturno
        c.update(title=title, venue=venue, start=start, date=date)
        sel.append(c)
    log(NAME, "seleccionados:", len(sel))

    out = []
    detail = 0
    for c in sel:
        address = None; price_txt = None
        ld = c["ld"]
        offer = ld.get("offers") or {}
        price = offer.get("price")
        try: price = float(price) if price not in (None, "") else None
        except (TypeError, ValueError): price = None
        if price is not None and price == int(price): price = int(price)
        start = c["start"]
        if detail < MAX_DETAIL:
            detail += 1
            try:
                h = get(c["url"])
                txt = soup(h).get_text("\n")
                m = re.search(r"Direcci[oó]n:\s*([^\n]+)", txt)
                if m: address = clean_text(m.group(1)).rstrip(",")
                m = re.search(r"Hora:\s*\n?\s*(\d{1,2}[:.]\d{2})", txt)
                if m and not start: start = m.group(1).replace(".", ":").zfill(5)
                m = re.search(r"Precio Entradas:\s*\n?\s*([^\n]+)", txt)
                if m: price_txt = clean_text(m.group(1))
            except Exception as ex:
                log(NAME, "ficha", c["url"], ex)
            time.sleep(0.4)
        if address and "madrid" not in plain(address): address = f"{address}, Madrid"
        ptxt = None
        if price is not None and price > 0:
            ptxt = f"Desde {str(price).replace('.', ',')} €"
        pmin = price if price is not None and price > 0 else None
        out.append(event(title=c["title"], date=night_date(c["date"], start), start=start, venue=c["venue"], address=address, type="concierto",
                         music=genres_to_music(c["genre"] + " " + c["title"]), priceMin=pmin, priceMax=None, priceText=ptxt,
                         description=(f"Género: {c['genre']}." if c["genre"] else None),
                         sources=[{"name": NAME, "url": c["url"]}], ticketUrl=c["url"]))
    return out
