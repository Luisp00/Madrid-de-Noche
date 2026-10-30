"""Helper compartido por siroco.py y salaelsol.py (WordPress + Events Manager): feed .ics + ficha propia de cada evento.
El prefijo "_" hace que scrape.py no lo trate como fuente.

El .ics da título, descripción, categoría (Clubbing / Conciertos) y URL de la ficha; la hora real y los precios solo están en la ficha
(bloque "Fecha / Hora / Entradas anticipadas / Entradas taquilla / Planta / Tipo" y botón "Tickets")."""
import re, time, datetime
from scrape.common import (get, soup, event, in_window, clean_text, plain, night_date, music_tags, log)
from scrape.sources._filtros import excluded_title, euro_nums

MAX_DETAIL = 60

def _unescape(s):
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), s)

def parse_ics(text):
    """Lista de dicts {summary, description, url, categories, date, time} (hora local de DTSTART)."""
    text = re.sub(r"\r?\n[ \t]", "", text)           # desdoblar líneas plegadas
    out = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        block = block.split("END:VEVENT")[0]
        props = {}
        for line in block.splitlines():
            m = re.match(r"^([A-Z-]+)(?:;[^:]*)?:(.*)$", line)
            if m and m.group(1) not in props: props[m.group(1)] = m.group(2)
        ds = props.get("DTSTART", "")
        m = re.match(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", ds)
        if not m or not props.get("URL"): continue
        out.append(dict(summary=clean_text(_unescape(props.get("SUMMARY", ""))), description=_unescape(props.get("DESCRIPTION", "")).strip(),
                        url=props["URL"].strip(), categories=[c.strip() for c in _unescape(props.get("CATEGORIES", "")).split(",") if c.strip()],
                        date=f"{m.group(1)}-{m.group(2)}-{m.group(3)}", time=(f"{m.group(4)}:{m.group(5)}" if m.group(4) else None)))
    return out

def _times(s):
    """'21.00 - 23.30h' -> ['21:00', '23:30']; '00 - 5:30hs' -> ['00:00', '05:30']; '21h a 00h' -> ['21:00', '00:00']."""
    res = []
    for m in re.finditer(r"(?<![\d:.])(\d{1,2})(?:[:.](\d{2}))?(?![\d:.]\d)", s or ""):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h < 24 and mi < 60: res.append(f"{h:02d}:{mi:02d}")
    return res

def _fields(html):
    """{'Hora': '...', 'Entradas anticipadas': '...', ...} del bloque de datos de la ficha, y enlace 'Tickets'."""
    s = soup(html)
    fields = {}
    for st in s.select(".evento-informacion-recuadro strong, .info-box strong"):
        label = clean_text(st.get_text()).rstrip(":").strip()
        val = ""
        for sib in st.next_siblings:
            n = getattr(sib, "name", None)
            if n in ("br", "strong"): break
            val += sib.get_text(" ") if n else str(sib)
        if label and label not in fields: fields[label] = clean_text(val)
    a = s.select_one("a.Tickets, a.Tickets-bottom")
    ticket = a["href"].strip() if a and a.get("href", "").startswith("http") else None
    return fields, ticket

def _lineup(title):
    t = re.sub(r"\s\[[^\]]*\]|\s\([^)]*\)", " ", title)
    if ":" in t: t = t.split(":", 1)[1]
    parts = [clean_text(p) for p in re.split(r"\s+\+\s*|\s*\+\s+", t)]
    parts = [re.sub(r"\*+$", "", p).strip() for p in parts if p]
    if parts: parts[0] = re.sub(r"^.*?\b\w{4,}\.\s+(?=\S)", "", parts[0])      # "Notorious session. DJ Zeten" -> "DJ Zeten"
    return parts if len(parts) >= 2 else []

def _short(txt, n=330):
    txt = clean_text(txt)
    if len(txt) <= n: return txt
    cut = txt[:n]
    m = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:m + 1] if m > n // 2 else cut.rsplit(" ", 1)[0] + "…")

def scrape_ics(*, name, ics_url, venue, address, zone, today, end, club_music, concert_music, club_planta=False):
    try:
        evs = parse_ics(get(ics_url))
    except Exception as ex:
        log(name, "ics", ex); return []
    log(name, "eventos en el .ics:", len(evs))
    lo = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
    hi = (datetime.date.fromisoformat(end) + datetime.timedelta(days=1)).isoformat()   # una sesión de madrugada del día D+1 es de la noche D
    out, detail = [], 0
    for e in evs:
        if not (lo <= e["date"] <= hi): continue
        cats = e["categories"]
        if "Clubbing" in cats: typ = "club"
        elif "Conciertos" in cats: typ = "concierto"
        else: continue                                    # Fast expos, exposiciones…
        title = e["summary"]
        status = "desconocido"
        if re.search(r"[-–(\[]\s*sold[ -]?out\s*[)\]]?\s*$|[-–]\s*agotad[oa]\s*$", title, re.I):
            title = re.sub(r"\s*[-–(\[]\s*(sold[ -]?out|agotad[oa])\s*[)\]]?\s*$", "", title, flags=re.I); status = "agotado"
        if excluded_title(title): continue
        fields, ticket, start, endt = {}, None, None, None
        if detail < MAX_DETAIL:
            detail += 1
            try: fields, ticket = _fields(get(e["url"]))
            except Exception as ex: log(name, "ficha", e["url"], ex)
            time.sleep(0.4)
        ts = _times(fields.get("Hora", ""))
        if ts: start = ts[0]; endt = ts[1] if len(ts) > 1 else None
        elif e["time"]: start = e["time"]
        if not start: continue
        # la fecha del feed es el día natural del inicio: una sesión de 00:00-05:59 es de la noche anterior
        date = night_date(e["date"], start)
        if not in_window(date, today, end): continue
        if typ == "concierto" and start < "20:00": continue

        ant, taq = fields.get("Entradas anticipadas", ""), fields.get("Entradas taquilla", "")
        nums = euro_nums(ant) + euro_nums(taq)
        free = bool(re.search(r"\b(gratis|gratuit[oa]|entrada libre|free)\b", plain(ant + " " + taq)))
        pmin = 0 if free else (min(nums) if nums else None)
        if free and nums: pmax = max(nums)
        else: pmax = max(nums) if nums and max(nums) > min(nums) else None
        if re.search(r"agotad|sold", plain(ant + " " + taq)): status = "agotado"
        parts = []
        if ant: parts.append(f"Anticipada {ant}")
        if taq: parts.append(f"Taquilla {taq}")
        ptxt = (" · ".join(parts)[:120]) if (nums or free) and parts else None

        desc = _short(e["description"])
        planta = fields.get("Planta")
        if club_planta and planta: desc = f"{planta}. {desc}".strip()
        if not nums and not free: pmin = pmax = None
        out.append(event(title=title, date=date, start=start, end=endt, venue=venue, address=address, zone=zone, type=typ,
                         music=(music_tags(title + " " + e["description"][:250]) or (club_music if typ == "club" else concert_music)),
                         priceMin=pmin, priceMax=pmax, priceText=ptxt, free=free, lineup=_lineup(title), description=(desc[:400] or None),
                         status=status, sources=[{"name": name, "url": e["url"]}], ticketUrl=(ticket.split()[0] if ticket and ticket.split() else None) or e["url"]))
    return out
