"""Madrid en Vivo (madridenvivo.com): la agenda carga cada día por AJAX (POST load-eventos.php); se pide un día por petición (estilo "" = todos).
Fecha de la web = noche del evento (un pase de 00:30 en el día 31 es la madrugada del 1 → se deja en date=31, sin desplazar).
Detalle (máx. 60 páginas): ficha de los eventos Clubbing (estilos), página de sala (dirección) y fichas con precio "Evento ya realizado"."""
import re, time, datetime, collections, string
from scrape import common
from scrape.common import soup, event, in_window, clean_text, plain, music_tags, log
from scrape.sources._filtros import excluded_venue, excluded_title, euro_nums

NAME = "Madrid en Vivo"
MIN_EVENTS = 5
AJAX = "https://madridenvivo.com/wp-content/themes/base/codigo/includes/ajax/load-eventos.php"
MAX_DETAIL = 60
SKIP_GENRES = {"artes escenicas", "flamenco capital"}
GENRE_MUSIC = {"pop / rock": ["pop", "rock"], "musicas negras": ["otros"], "clubbing": []}


def day_html(d):
    """HTML del listado de un día (POST AJAX con caché de common)."""
    key = f"POST {AJAX} {d}"
    txt = common._cached(key)
    if txt is None:
        y, m, dd = d.split("-")
        last = None
        for i in range(3):
            try:
                r = common.session().post(AJAX, data=dict(buscar="", sala="", estilo="", dia=dd, mes=m, ano=y, destacados=0), timeout=30)
                if r.status_code == 200:
                    j = r.json()
                    if j.get("status") == 200:
                        txt = j.get("content") or ""; common._store(key, txt); break
                    last = f"status {j.get('status')}"
                else: last = f"HTTP {r.status_code}"
            except Exception as ex:
                last = str(ex)[:150]
            time.sleep(1.5 * (i + 1))
        if txt is None:
            log(NAME, "día", d, last); return ""
    return txt


def parse_day(html, d):
    out = []
    for it in soup(html).select(".item-evento.listado"):
        a = it.select_one("h3 a")
        if not a: continue
        genres = [clean_text(x.get_text()) for x in it.select(".item-evento__generos__enlace")]
        sala = it.select_one(".item-evento__sala a")
        pases = clean_text((it.select_one(".item-evento__pases") or it).get_text()) if it.select_one(".item-evento__pases") else ""
        times = [f"{int(h):02d}:{m}" for h, m in re.findall(r"(\d{1,2}):(\d{2})\s*h", pases)]
        pr = it.select_one(".item-evento__anticipada__texto")
        out.append(dict(date=d, title=clean_text(a.get_text()), url=a["href"], genres=genres, venue=clean_text(sala.get_text()) if sala else None,
                        venue_url=sala["href"] if sala and sala.get("href") else None, times=times, pases=pases,
                        price=clean_text(pr.get_text(" ")) if pr else ""))
    return out


def nice_title(t):
    """Los títulos de la web van en MAYÚSCULAS: pasa a capitalizado (DJ/B2B se respetan)."""
    letters = [c for c in t if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.6: return t
    out = string.capwords(t.lower())
    return re.sub(r"\b(Dj|Djs|B2b|Vip|Uk|Us|Ii|Iii)\b", lambda m: {"Djs": "DJs"}.get(m.group(1), m.group(1).upper() if m.group(1) in ("Dj", "B2b", "Vip", "Uk", "Us") else m.group(1)), out)


def pick_start(times):
    if not times: return None
    late = [t for t in times if t >= "20:00" or t < "06:00"]
    return late[0] if late else times[0]


def price_fields(txt):
    p = plain(txt)
    if not txt or "a consultar" in p or "realizado" in p: return None, None, False, None
    if re.search(r"entrada libre|gratis|gratuit", p) and not euro_nums(txt): return 0, None, True, clean_text(txt)[:120]
    nums = euro_nums(txt)
    if not nums: return None, None, False, clean_text(txt)[:120]
    desde = bool(re.search(r"\bdesde\b|a partir", p))
    pmax = max(nums) if len(nums) > 1 and max(nums) != min(nums) and not desde else None
    return min(nums), pmax, bool(re.search(r"entrada libre|gratis", p)), clean_text(txt)[:120]


def scrape(today, end):
    d0 = datetime.date.fromisoformat(today); d1 = datetime.date.fromisoformat(end)
    rows = []
    d = d0
    while d <= d1:
        ds = d.isoformat()
        rows += parse_day(day_html(ds), ds)
        d += datetime.timedelta(days=1)
    log(NAME, "filas:", len(rows))
    sel = []
    drop = collections.Counter()
    for r in rows:
        if not r["venue"]: drop["sin sala"] += 1; continue
        gl = {plain(g) for g in r["genres"]}
        if gl & SKIP_GENRES: drop["género escénico/flamenco"] += 1; continue
        if excluded_venue(r["venue"]) or excluded_title(r["title"]): drop["sala/título excluido"] += 1; continue
        club = "clubbing" in gl or bool(re.search(r"\bdjs?\b|dj set|tardeo", plain(r["title"])))
        r["start"] = pick_start(r["times"])
        if not r["start"]: drop["sin hora"] += 1; continue
        if r["start"] < "20:00" and r["start"] >= "06:00" and not club: drop["antes de las 20:00"] += 1; continue
        r["club"] = club
        sel.append(r)
    log(NAME, "descartes:", dict(drop), "seleccionados:", len(sel))

    budget = [MAX_DETAIL]
    def fetch(url):
        if budget[0] <= 0: return None
        budget[0] -= 1
        try: h = common.get(url)
        except Exception as ex:
            log(NAME, "detalle", url, ex); return None
        time.sleep(0.4)
        return h

    # 1) fichas de eventos Clubbing: estilos (#Indie #Pop) y descripción
    ficha = {}
    for r in sel:
        if r["club"] and r["url"] not in ficha:
            h = fetch(r["url"])
            if h:
                t = soup(h)
                txt = t.get_text("\n")
                est = re.findall(r"#\s*([^\s#]+(?: [^\s#]+)?)", txt[txt.find("Estilos"):txt.find("Estilos") + 200]) if "Estilos:" in txt else []
                m = re.search(r"Precio:\s*\n\s*([^\n]+)", txt)
                ficha[r["url"]] = dict(estilos=[clean_text(x) for x in est][:6], price=clean_text(m.group(1)) if m else None)
    # 2) dirección: página de sala (las salas con más eventos primero)
    cnt = collections.Counter(r["venue_url"] for r in sel if r["venue_url"])
    addr = {}
    for vu, _ in cnt.most_common():
        if budget[0] <= 12: break
        h = fetch(vu)
        if not h: continue
        m = re.search(r"Direcci[oó]n:\s*</strong>\s*([^<]+)", h)
        if m:
            a = clean_text(m.group(1)).rstrip(",")
            a = re.sub(r"\b(\d{5}),\s*Madrid\.?$", r"\1 Madrid", a).rstrip(".")
            addr[vu] = a
    # 3) precio de las fichas con "Evento ya realizado" (la lista no lo muestra)
    for r in sel:
        if "realizado" in plain(r["price"]) and r["url"] not in ficha:
            h = fetch(r["url"])
            if h:
                txt = soup(h).get_text("\n")
                m = re.search(r"Precio:\s*\n\s*([^\n]+)", txt)
                ficha[r["url"]] = dict(estilos=[], price=clean_text(m.group(1)) if m else None)

    out = []
    for r in sel:
        f = ficha.get(r["url"]) or {}
        ptxt_src = r["price"] if "realizado" not in plain(r["price"]) else (f.get("price") or "")
        if plain(ptxt_src).startswith("precio a consultar"): ptxt_src = ""
        mn, mx, free, ptxt = price_fields(ptxt_src)
        gl = [plain(g) for g in r["genres"]]
        music = []
        for g in ([] if r["club"] else gl):  # en sesiones DJ el género "Pop / Rock" de la web no describe la música
            for t in GENRE_MUSIC.get(g, []):
                if t not in music: music.append(t)
        for t in music_tags(" ".join([r["title"]] + f.get("estilos", []))):
            if t not in music: music.append(t)
        title = r["title"]
        typ = "tardeo" if re.search(r"tardeo", plain(title)) else ("club" if r["club"] else "concierto")
        desc = None
        if len(r["times"]) > 1: desc = r["pases"][:200]
        out.append(event(title=nice_title(title), date=r["date"], start=r["start"], venue=r["venue"], address=addr.get(r["venue_url"]),
                         type=typ, music=music or ["variado"], priceMin=mn, priceMax=mx, priceText=ptxt, free=free, description=desc,
                         sources=[{"name": NAME, "url": r["url"]}], ticketUrl=r["url"]))
    return out
