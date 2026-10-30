"""Teatro Barceló (teatrobarcelo.com, WordPress + EventON). El calendario de EventON sale vacío tanto con requests como con el
navegador y la API ajde_events no devuelve nada, así que se usan las fichas de las sesiones semanales (/sesiones/<día>-en-teatro-barcelo/):
"+25 | Barceló Saturdays | Todos los Sábados de 00.30 a 6.00 h." → una sesión por cada noche de ese día en la ventana (SPEC: eventos
recurrentes). Las sesiones especiales (Loco Bongo, La Movida de los 90…) no publican fechas y no se emiten. Precio: la web no lo da."""
import re, time, datetime
from scrape.common import get, soup, event, clean_text, plain, music_tags, log

NAME = "Teatro Barceló"
MIN_EVENTS = 4
VENUE = "Teatro Barceló"
ADDRESS = "C/ Barceló 11, 28004 Madrid"
ZONE = "Malasaña / Chueca"
BASE = "https://www.teatrobarcelo.com"
WEEKLY = ["lunes", "miercoles", "jueves", "viernes", "sabado"]
WD = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}

def _music_by_session(home):
    """{nombre de sesión: texto de géneros} de la portada ("BARCELÓ | Fridays | +25 | Reggaetón | Top 40 | Electrónica")."""
    t = clean_text(soup(home).get_text(" | ", strip=True))
    out = {}
    for m in re.finditer(r"((?:BARCELÓ \| )?[A-Za-zÁÉÍÓÚáéíóú]+) \| \+\d{2} \| ((?:[^|]+ \| ){1,4})", t):
        out[plain(m.group(1).replace("BARCELÓ | ", "Barceló "))] = m.group(2)
    return out

def scrape(today, end):
    try: mus = _music_by_session(get(BASE + "/"))
    except Exception as ex: log(NAME, "portada", ex); mus = {}
    sessions = []
    for d in WEEKLY:
        url = f"{BASE}/sesiones/{d}-en-teatro-barcelo/"
        try: html = get(url)
        except Exception as ex: log(NAME, "sesión", url, ex); continue
        time.sleep(0.4)
        txt = clean_text(soup(html).get_text(" | ", strip=True))
        m = re.search(r"\+(\d{2}) \| ([^|]{2,40}) \| (?:Todos los )?(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bados?|Domingos?)s? de (\d{1,2})[.:](\d{2}) a (\d{1,2})[.:](\d{2})", txt, re.I)
        if not m: log(NAME, "sin horario en", url); continue
        day = {"sabados": "sabado", "domingos": "domingo"}.get(plain(m.group(3)), plain(m.group(3)))
        if day not in WD: continue
        name = clean_text(m.group(2))
        g = mus.get(plain(name), "")
        sessions.append(dict(name=name, wd=WD[day], age=int(m.group(1)), url=url, music=music_tags(g + " " + name) or ["comercial", "reggaeton"],
                             start=f"{int(m.group(4)):02d}:{m.group(5)}", end=f"{int(m.group(6)):02d}:{m.group(7)}"))
    out = []
    d0, d1 = datetime.date.fromisoformat(today), datetime.date.fromisoformat(end)
    while d0 <= d1:
        for s in sessions:
            if d0.weekday() == s["wd"]:
                out.append(event(title=s["name"], date=d0.isoformat(), start=s["start"], end=s["end"], venue=VENUE, address=ADDRESS, zone=ZONE,
                                 type="club", music=s["music"], ageMin=s["age"], description=f"Sesión semanal de Teatro Barceló (+{s['age']}).",
                                 sources=[{"name": NAME, "url": s["url"]}], ticketUrl=s["url"]))
        d0 += datetime.timedelta(days=1)
    return out
