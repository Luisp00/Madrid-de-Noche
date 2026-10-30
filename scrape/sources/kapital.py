"""Teatro Kapital (teatrokapital.com). La web (WordPress) no publica agenda: su botón "Entradas" lleva a Ticketclub
(marca blanca de Fever, plan 121772). Esa página trae en el estado Angular (<script id="ng-state">) el calendario de noches abiertas
con el precio mínimo de la entrada general de cada noche y su estado (sold_out), y la sesión del primer día (hora 23:00–06:00).
Las mesas VIP no cuentan para el precio. Un evento por noche abierta."""
import re, json, datetime
from scrape.common import get, event, in_window, clean_text, log

NAME = "Teatro Kapital"
MIN_EVENTS = 4
VENUE = "Teatro Kapital"
ADDRESS = "C/ Atocha 125, 28012 Madrid"
ZONE = "Atocha"
SITE = "https://teatrokapital.com/"
PLAN = "https://ticketclub.es/es/plans/121772"

def _state(html):
    m = re.search(r'<script id="ng-state" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}

def _hours(st):
    """(inicio, fin, texto de lo que incluye la entrada general) de la sesión que trae la página."""
    for k, v in st.items():
        if not k.startswith("PLAN_SESSIONS_"): continue
        for t in (v.get("level") or {}).get("items", []):
            for grp in (t.get("level") or {}).get("items", []):
                if "mesa" in (grp.get("default_label") or "").lower(): continue
                for it in (grp.get("level") or {}).get("items", []):
                    val = it.get("value") or {}
                    s, e = val.get("starts_at_iso", ""), val.get("ends_at_iso", "")
                    det = clean_text(re.sub(r"<[^>]+>", " ", val.get("details") or ""))
                    det = re.sub(r"&oacute;", "ó", det)
                    return (s[11:16] or None), (e[11:16] or None), det
    return None, None, ""

def scrape(today, end):
    try: site = get(SITE)
    except Exception as ex: log(NAME, "web", ex); site = ""
    m = re.search(r'https://ticketclub\.es/(?:es/)?plans/(\d+)', site)
    plan = f"https://ticketclub.es/es/plans/{m.group(1)}" if m else PLAN
    try: html = get(plan)
    except Exception as ex: log(NAME, "ticketclub", ex); return []
    st = _state(html)
    dates = {}
    for k, v in st.items():
        if k.startswith("PLAN_AVAILABILITY_") and isinstance(v, dict): dates.update(v.get("dates") or {})
    if not dates: log(NAME, "sin calendario en ng-state"); return []
    start, endt, det = _hours(st)
    start, endt = start or "23:00", endt or "06:00"     # la propia ficha: "Hora: de 23:00 a 6:00"
    incl = "2 consumiciones antes de la 1:00, después 1" if re.search(r"2 consumiciones", det) else None
    out = []
    for d in sorted(dates):
        info = dates[d]
        if not in_window(d, today, end): continue
        p = info.get("minTicketPrice")
        status = "agotado" if info.get("status") == "sold_out" else "disponible"
        ptxt = (f"Desde {p} € entrada general" + (f" ({incl})" if incl else "")) if p is not None else None
        out.append(event(title="Teatro Kapital", date=d, start=start, end=endt, venue=VENUE, address=ADDRESS, zone=ZONE, type="club",
                         music=["comercial", "reggaeton", "house"], priceMin=p, priceMax=None, priceText=(ptxt[:120] if ptxt else None),
                         ageMin=18, description="Siete plantas con estilos distintos (main room, reggaeton, karaoke, cóctel bar); mesas VIP aparte.",
                         status=status, sources=[{"name": NAME, "url": plan}], ticketUrl=plan))
    return out
