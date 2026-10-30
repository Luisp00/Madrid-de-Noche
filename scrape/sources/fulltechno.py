"""Fulltechno (fulltechno.club): listado WooCommerce con fecha y estilo en las clases CSS; detalle con JSON-LD."""
import re
from scrape.common import get, soup, ld_json, event, parse_time, parse_price, in_window, music_tags, clean_text, night_date, log

NAME = "Fulltechno"
MIN_EVENTS = 20
LIST_URLS = ["https://fulltechno.club/poblacion/madrid/", "https://fulltechno.club/poblacion/madrid/page/2/"]

def scrape(today, end):
    out, seen = [], set()
    for lu in LIST_URLS:
        try: html = get(lu)
        except Exception as ex: log(NAME, "listado", ex); continue
        s = soup(html)
        for li in s.select("li.product, div.product"):
            cls = " ".join(li.get("class", []))
            m = re.search(r"ftc-fecha-(\d{4})(\d{2})(\d{2})", cls)
            if not m: continue
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            if not in_window(date, today, end): continue
            a = li.select_one("a[href*='/evento/']")
            if not a: continue
            url = a["href"].split("?")[0]
            if url in seen: continue
            seen.add(url)
            styles = re.findall(r"ftc-est-([a-z]+)", cls)
            title = clean_text((li.select_one(".woocommerce-loop-product__title, h2, h3") or a).get_text())
            price_txt = clean_text(li.select_one(".price").get_text()) if li.select_one(".price") else None
            ev = detail(url, date, title, styles, price_txt, today, end)
            if ev: out.append(ev)
    return out

def detail(url, date, title, styles, price_txt, today, end):
    venue = None; start = None; endt = None; address = None; desc = None; lineup = []
    try:
        html = get(url)
        for d in ld_json(html):
            if d.get("@type") in ("Event", "MusicEvent"):
                loc = d.get("location") or {}
                if isinstance(loc, dict):
                    venue = loc.get("name") or venue
                    ad = loc.get("address")
                    if isinstance(ad, dict): address = ", ".join(x for x in [ad.get("streetAddress"), ad.get("postalCode"), ad.get("addressLocality")] if x)
                    elif isinstance(ad, str): address = ad
                sd = d.get("startDate") or ""
                if "T" in sd: start = sd.split("T")[1][:5]
                ed = d.get("endDate") or ""
                if "T" in ed: endt = ed.split("T")[1][:5]
                if d.get("performer"):
                    perf = d["performer"] if isinstance(d["performer"], list) else [d["performer"]]
                    lineup = [p.get("name") for p in perf if isinstance(p, dict) and p.get("name")]
                desc = clean_text(d.get("description") or "")[:400] or None
                title = d.get("name") or title
        s = soup(html)
        txt = s.get_text(" ")
        if not venue:
            m = re.search(r"(?:Sala|Club|Lugar)\s*:\s*([^\n|·]{3,60})", txt)
            if m: venue = clean_text(m.group(1))
        if not start:
            m = re.search(r"(?:Hora|Apertura|Horario)\s*:?\s*(\d{1,2}[:.h]\d{2})", txt)
            if m: start = parse_time(m.group(1))
        if not price_txt:
            m = re.search(r"(\d+(?:[.,]\d+)?\s*€[^.\n]{0,40})", txt)
            if m: price_txt = clean_text(m.group(1))
    except Exception as ex:
        log(NAME, "detalle", url, ex)
    if not venue:
        m = re.search(r"-\s*([^-|]+?)\s*(?:madrid)?\s*$", title, re.I)
        venue = clean_text(m.group(1)) if m else None
    if not venue: return None
    pmin, pmax, free = parse_price(price_txt)
    music = [t for t in (styles or []) if t in ("techno", "house", "hardtechno")] or music_tags(title + " " + (desc or ""))
    if "hard" in (styles or []): music = ["hardtechno"] + [m for m in music if m != "hardtechno"]
    return event(title=title, date=night_date(date, start) if start else date, start=start, end=endt, venue=venue, address=address,
                 type="club", music=music or ["techno"], priceMin=pmin, priceMax=pmax, priceText=price_txt, free=free, lineup=lineup[:12],
                 description=desc, sources=[{"name": NAME, "url": url}], ticketUrl=url)
