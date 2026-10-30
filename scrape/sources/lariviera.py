"""La Riviera (salariviera.com): API REST de The Events Calendar (/wp-json/tribe/events/v1/events) con hora de inicio, coste y web de venta.
La sala publica la hora de apertura de puertas como "recinto" de cada evento ("Apertura Puertas: 19:30 pm")."""
import re, html, datetime
from scrape.common import get, event, in_window, clean_text, plain, music_tags, parse_time, log
from scrape.sources._filtros import excluded_title, euro_nums

NAME = "La Riviera"
MIN_EVENTS = 4
VENUE = "La Riviera"
ADDRESS = "Paseo Bajo de la Virgen del Puerto s/n, 28005 Madrid"
ZONE = "La Latina"
API = "https://salariviera.com/wp-json/tribe/events/v1/events"

def _strip_html(s):
    return clean_text(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))

def scrape(today, end):
    items, url, params = [], API, {"start_date": today, "end_date": end, "per_page": 50}
    for _ in range(5):
        try: d = get(url, params=params, json_=True)
        except Exception as ex:
            log(NAME, "rest", ex); break
        items += d.get("events", [])
        url, params = d.get("next_rest_url"), None
        if not url: break
    log(NAME, "eventos REST:", len(items))
    out = []
    for e in items:
        title = clean_text(html.unescape(e.get("title") or ""))
        sd = e.get("start_date") or ""
        date, start = sd[:10], sd[11:16] or None
        if not title or not in_window(date, today, end) or e.get("all_day"): continue
        if excluded_title(title): continue
        if start and start < "20:00": continue
        doors = None
        v = e.get("venue") or {}
        m = re.search(r"(\d{1,2})[:.](\d{2})", (v.get("venue") if isinstance(v, dict) else "") or "")
        if m: doors = f"{int(m.group(1)):02d}:{m.group(2)}"
        cost = clean_text(html.unescape(e.get("cost") or ""))
        nums = euro_nums(cost) or [float(x) for x in (e.get("cost_details") or {}).get("values", []) if str(x).replace(".", "", 1).isdigit()]
        free = bool(re.search(r"\b(gratis|gratuit[oa]|free|entrada libre)\b", plain(cost)))
        pmin = 0 if free else (min(nums) if nums else None)
        pmax = max(nums) if nums and max(nums) > (pmin or 0) else None
        desc = _strip_html(e.get("description") or e.get("excerpt"))[:330]
        desc = " ".join(x for x in [f"Apertura de puertas {doors}." if doors else "", desc] if x) or None
        site = (e.get("website") or "").strip()
        out.append(event(title=title, date=date, start=start, venue=VENUE, address=ADDRESS, zone=ZONE, type="concierto",
                         music=music_tags(title), priceMin=pmin, priceMax=pmax, priceText=(cost[:120] if (nums or free) and cost else None), free=free,
                         description=desc, sources=[{"name": NAME, "url": e["url"]}], ticketUrl=(site if site.startswith("http") else e["url"])))
    return out
