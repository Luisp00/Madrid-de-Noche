"""Sala Galileo Galilei (salagalileo.es/programacion): listado HTML (Modern Events Calendar) con fecha, hora, categoría, precio y enlace de compra
(geeticket / oneboxtds / dice…). Solo conciertos ("CONCIERTO LIVE") a partir de las 20:00; se descartan humor, magia, familiar y tributos."""
import re
from scrape.common import get, soup, event, in_window, clean_text, plain, music_tags, MONTHS, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "Sala Galileo Galilei"
MIN_EVENTS = 3
VENUE = "Sala Galileo Galilei"
ADDRESS = "C/ Galileo 100, 28003 Madrid"
ZONE = "Chamberí"
URL = "https://salagalileo.es/programacion/"

def scrape(today, end):
    try: html = get(URL)
    except Exception as ex:
        log(NAME, "programacion", ex); return []
    out, n = [], 0
    for a in soup(html).select("article.mec-event-article"):
        n += 1
        txt = lambda sel: clean_text(a.select_one(sel).get_text(" ")) if a.select_one(sel) else None
        ym = next((re.search(r"mec-toggle-(\d{4})(\d{2})", c) for c in a.get("class", []) if c.startswith("mec-toggle-")), None)
        dm = re.match(r"(\d{1,2})\s+(\w+)", txt(".mec-start-date-label") or "")
        if not ym or not dm or MONTHS.get(plain(dm.group(2))) != int(ym.group(2)): continue
        date = f"{ym.group(1)}-{ym.group(2)}-{int(dm.group(1)):02d}"
        if not in_window(date, today, end): continue
        cat = txt(".mec-cat-tag")
        if plain(cat or "") != "concierto live": continue            # humor, familiar, magia, sin categoría…
        title = txt(".mec-event-title")
        if not title or excluded_title(re.sub(r"karaoke triste", "", title, flags=re.I)): continue
        start = txt(".mec-start-time")
        if not start or start < "20:00": continue
        link = a.select_one(".mec-event-title a")
        url = link["href"] if link else URL
        tk = a.select_one("a.mec-custom-ticket-button")
        nums = euro_nums(txt(".mec-event-cost-price") or "")
        desc = re.sub(r"\s*\[…\]$|\s*…$", "…", txt(".mec-event-description") or "") or None
        out.append(event(title=title, date=date, start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type="concierto",
                         music=music_tags(title), priceMin=(min(nums) if nums else None), priceMax=None,
                         priceText=(f"{nums[0]:.2f}".replace(".00", "").replace(".", ",") + " €" if nums else None), description=(desc[:400] if desc else None),
                         sources=[{"name": NAME, "url": url}], ticketUrl=(tk["href"] if tk and tk.get("href", "").startswith("http") else url)))
    log(NAME, "tarjetas:", n)
    return out
