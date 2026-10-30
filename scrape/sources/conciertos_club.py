"""Conciertos.club: una sola página /madrid con todos los conciertos (microdatos schema.org MusicEvent).
Hora fiable en el listado; "00:00" = hora desconocida (la ficha tampoco la da). Dirección: ficha de la sala (/madrid/locales/...)."""
import re, time, collections, urllib.parse
from scrape.sources._filtros import excluded_venue, excluded_title
from scrape.common import (get, soup, event, in_window, clean_text, plain, night_date, music_tags, log)

NAME = "Conciertos.club"
MIN_EVENTS = 100
BASE = "https://conciertos.club"
LIST_URL = BASE + "/madrid"
MAX_DETAIL = 60

# género del listado -> etiquetas de música (lista cerrada de SPEC.md)
STYLE_MUSIC = {
    "pop-rock/indie": ["indie", "rock"], "rock/rock alternativo": ["rock"], "metal/rock duro": ["rock"], "punk/hardcore": ["rock"],
    "post-punk": ["rock"], "rock and roll/garage": ["rock"], "blues/rnb": ["rnb"], "soul/funk": ["disco"], "jazz/swing": ["otros"],
    "cantautores": ["pop"], "urbana/reggaeton/trap": ["urban", "reggaeton"], "hip-hop": ["hiphop"], "pop": ["pop"], "pop latino": ["latino", "pop"],
    "musica latina": ["latino"], "electronica/dance": ["electronica"], "pop electronico": ["electronica", "pop"], "mestizaje/fusion": ["variado"],
    "varios": ["variado"], "reggae/ska": ["otros"], "americana/folk rock/country": ["otros"], "world music/musica etnica": ["otros"],
    "folk": ["otros"], "versiones/tributos": ["otros"], "musica experimental": ["electronica"], "musica ligera": ["pop"],
}
# géneros "nocturnos": admiten entrar sin hora conocida si la sala es de conciertos conocida
NIGHT_STYLES = {"pop-rock/indie", "rock/rock alternativo", "metal/rock duro", "punk/hardcore", "post-punk", "rock and roll/garage", "blues/rnb",
                "soul/funk", "urbana/reggaeton/trap", "hip-hop", "electronica/dance", "pop electronico", "mestizaje/fusion"}
SKIP_STYLES = {"clasica", "danza/ballet"}

KNOWN_VENUES = [
    "la riviera", "sala but", "sala mon", "mon live", "copernico", "sala el sol", "moby dick", "siroco", "cafe berlin", "chango", "wurlitzer",
    "gruta 77", "clamores", "galileo galilei", "fun house", "rockville", "villanos", "honky tonk", "maravillas", "intruso", "la coquette",
    "cadillac solitario", "sala vesta", "el perro de la parte de atras", "moe", "big mama", "sala uni", "sala olvido", "revi live", "fulanita de tal",
    "hangar 48", "live las ventas", "las ventas", "cadavra", "sala nazca", "sala wagon", "sala caracol", "independance", "teatro kapital", "teatro barcelo",
    "sala sol", "jazzville", "el despertar", "movistar arena", "palacio de vistalegre", "wizink", "mondo disko", "sala strong", "madreams", "lab the club",
    "tributo", "sala fenix", "sala x", "sala clamores", "taboo", "sala sidecar", "ritmo y compas", "sala lemon", "el sotano", "cafe la palma",
    "cafe central", "sala 0", "rincon del arte nuevo", "garito", "la boite", "sala la fabrik", "fabrik", "sala mirador", "sala charada", "sala changai",
]
CLUB_VENUES = ["cadavra", "sala wagon", "siroco", "nazca", "mondo", "kapital", "lab the club", "sala strong", "fabrik"]


def _style_key(style):
    return plain(style or "").lstrip("/ ").strip()


def parse_listing(html, today, end):
    s = soup(html)
    out = []
    for li in s.select("li[itemprop=itemListElement]"):
        a = li.select_one("a.nombre")
        tm = li.select_one(".time")
        if not a or not tm: continue
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2})", tm.get_text(" "))
        if not m: continue
        date = f"20{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        if not in_window(date, today, end): continue
        hm = re.search(r"(\d{1,2}):(\d{2})", tm.get_text(" "))
        start = f"{int(hm.group(1)):02d}:{hm.group(2)}" if hm else None
        if start == "00:00": start = None  # marcador de "hora desconocida"
        strong = a.select_one("strong")
        name = clean_text(strong.get("title") or strong.get_text()) if strong else clean_text(a.get_text(" "))
        sub = clean_text(a.get_text(" ").replace(name, "", 1)) if strong else ""
        meta_name = li.select_one("meta[itemprop=name]:not([content=''])")  # el último meta name es el del evento
        for mn in li.select(".microdatos > meta[itemprop=name]"):
            meta_name = mn
        title = clean_text(meta_name["content"]) if meta_name and meta_name.get("content") else clean_text(a.get_text(" "))
        title = title.rstrip(". ").strip() or title
        est = li.select_one(".estilo")
        style = clean_text(est.get_text()).lstrip("/ ").strip() if est else ""
        loc = li.select_one(".microdatos [itemprop=location] > meta[itemprop=name]")
        loc_a = li.select_one("a.local")
        venue = clean_text(loc["content"]) if loc and loc.get("content") else clean_text((loc_a.get_text() if loc_a else "").rsplit(".", 1)[0])
        locality = clean_text(loc_a.get_text()).rsplit(".", 1)[-1].strip() if loc_a else "Madrid"
        href = a["href"]
        url = href if href.startswith("http") else BASE + href
        venue_href = loc_a["href"] if loc_a and loc_a.get("href") else None
        pw = li.select_one(".precio_wrap")
        buy = li.select_one("a.comprarentradas")
        ticket = None
        if buy and buy.get("href"):
            ticket = buy["href"]
            q = urllib.parse.parse_qs(urllib.parse.urlparse(ticket).query)
            if q.get("u"): ticket = q["u"][0]
        out.append(dict(date=date, start=start, name=name, sub=sub, title=title, style=style, venue=venue, locality=locality, url=url,
                        venue_href=venue_href, price=pw, ticket=ticket))
    return out


def price_of(pw):
    """-> (min, max, free, text, agotado)"""
    if pw is None: return None, None, False, None, False
    txt = clean_text(pw.get_text(" ").replace("\xa0", " ").replace("Comprar entradas", ""))
    p = plain(txt)
    agot = "agotad" in p
    if not txt or agot and not re.search(r"\d", txt):
        return None, None, False, ("Entradas agotadas" if agot else None), agot
    if "entrada libre" in p or "gratis" in p or "invitacion" in p:
        return 0, None, True, txt[:120], agot
    ant = pw.select_one(".precio_ant"); taq = pw.select_one(".precio_taq")
    if ant and taq:
        try:
            a_ = float(ant.get_text().strip().replace(",", ".")); t_ = float(taq.get_text().strip().replace(",", "."))
            a_ = int(a_) if a_ == int(a_) else a_; t_ = int(t_) if t_ == int(t_) else t_
            extra = re.sub(r"^[\d.,\s/€]+", "", txt).strip()
            text = f"Anticipada {a_} € · Taquilla {t_} €" + (f" {extra}" if extra else "")
            return min(a_, t_), max(a_, t_), False, text[:120], agot
        except ValueError:
            pass
    # common.plain() elimina el símbolo €, así que parse_price no ve estos precios: extraigo los números a mano
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d{1,2})?", txt.split("€")[0] if "€" in txt else "")]
    if not nums: return None, None, False, txt[:120] or None, agot
    nums = [int(n) if n == int(n) else n for n in nums]
    return min(nums), (max(nums) if len(nums) > 1 and max(nums) != min(nums) else None), False, txt[:120], agot


def venue_address(href):
    try:
        h = get(BASE + href)
    except Exception as ex:
        log(NAME, "sala", href, ex); return None
    txt = soup(h).get_text("\n")
    m = re.search(r"Direcci[oó]n:\s*\n\s*(.+?)\s*\n\s*(\d{5}\s+[^\n]+)", txt)
    if m: return clean_text(f"{m.group(1).rstrip(',')}, {m.group(2)}")
    return None


def scrape(today, end):
    try:
        html = get(LIST_URL, timeout=90)
    except Exception as ex:
        log(NAME, "listado", ex); return []
    rows = parse_listing(html, today, end)
    log(NAME, "filas en ventana:", len(rows))
    sel = []
    drop = collections.Counter()
    for r in rows:
        pv = plain(r["venue"]); pt = plain(r["title"] + " " + r["sub"]); sk = _style_key(r["style"])
        if r["locality"] not in ("Madrid", "") and not re.search(r"alcala|leganes|torrejon|getafe|alcobendas|fuenlabrada|mostoles|alcorcon|pozuelo|majadahonda|rivas|coslada|torrelodones", plain(r["locality"])):
            drop["fuera de Madrid"] += 1; continue
        if excluded_title(r["title"], r["sub"]): drop["título excluido"] += 1; continue
        if excluded_venue(r["venue"]): drop["sala con butaca"] += 1; continue
        if sk in SKIP_STYLES: drop["género"] += 1; continue
        electronic = sk in ("electronica/dance", "pop electronico") or bool(re.search(r"\bdj\b|\bdjs\b|dj set", pt))
        club = bool(re.search(r"\bdj\b|\bdjs\b|dj set|sesion|b2b", pt)) or (electronic and any(c in pv for c in CLUB_VENUES))
        if r["start"]:
            if not (r["start"] >= "20:00" or electronic): drop["antes de las 20:00"] += 1; continue
        else:
            known = any(k in pv for k in KNOWN_VENUES)
            if not (sk in NIGHT_STYLES and known): drop["sin hora y no nocturno/sala desconocida"] += 1; continue
        r["club"] = club
        sel.append(r)
    log(NAME, "descartes:", dict(drop), "seleccionados:", len(sel))

    # direcciones: ficha de sala (una por sala), priorizando las salas con más eventos
    cnt = collections.Counter(r["venue_href"] for r in sel if r["venue_href"])
    addr = {}
    for href, _ in cnt.most_common(MAX_DETAIL):
        addr[href] = venue_address(href)
        time.sleep(0.4)

    out = []
    for r in sel:
        sk = _style_key(r["style"])
        music = list(STYLE_MUSIC.get(sk, []))
        for t in music_tags(r["title"]):
            if t not in music and t in ("techno", "house", "hardtechno", "reggaeton", "trap", "dnb"): music.append(t)
        mn, mx, free, ptxt, agot = price_of(r["price"])
        date, start = r["date"], r["start"]
        if start: date = night_date(date, start)
        desc = f"Género: {r['style']}." if r["style"] else None
        if r["sub"]: desc = ((r["sub"] + ". ") if r["sub"] else "") + (desc or "")
        if not start: desc = ((desc or "") + " Hora no publicada.").strip()
        out.append(event(title=r["title"], date=date, start=start, venue=r["venue"], address=addr.get(r["venue_href"]),
                         type="club" if r["club"] else "concierto", music=music or ["otros"], priceMin=mn, priceMax=mx, priceText=ptxt, free=free,
                         lineup=[], description=(desc or None) and desc[:400], status="desconocido",
                         sources=[{"name": NAME, "url": r["url"]}], ticketUrl=r["ticket"] or r["url"]))
    return out
