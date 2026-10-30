#!/usr/bin/env python3
"""Fusiona data/*.json en eventos únicos y genera los lotes de escritura para la base de datos del artifact.

Uso: python3 -I merge.py data/ EXISTENTE out/ [--today YYYY-MM-DD]
  data/      archivos *.json de los agentes extractores (arrays de eventos según SPEC.md).
  EXISTENTE  estado actual de la BD. Admite tres formas:
               - un directorio tal como lo deja `ArtifactData` con `out_dir`: …/events/<id>.json
                 (contenido = data del documento) MÁS un archivo `versions.txt` con las versiones
                 de los documentos, que la herramienta imprime pero no guarda en los archivos:
                 basta pegar en él el texto del resultado (líneas con "<id> … version N" o
                 '"<id>" N'); opcionalmente …/meta/seen.json (mapa id → última fecha vista),
               - un archivo JSON con un array [{"id","version","data"}],
               - o "-" / inexistente si la BD está vacía.
             Sin versiones no se puede escribir sobre documentos existentes: el script se niega a
             generar lotes si hay documentos y ninguna versión (salvo --force).
  out/       se escriben:
               merged.json            eventos únicos (depuración)
               docs/<id>.json         documento completo de cada evento nuevo o cambiado
               batch_NN.json          lotes de ≤50 escrituras para `ArtifactData` action "batch"
                                      (campo `writes`), con los documentos EN LÍNEA (`data`)
               batchf_NN.json         los mismos lotes pero referenciando docs/<id>.json con `file_path`
                                      (mucho más barato en contexto si la herramienta lo admite)
               seen.json              nuevo mapa id → última fecha vista, para `set` en meta/seen
               status.json            propuesta de documento meta/status (completar lastUpdated)
               summary.json           estadísticas (también se imprimen por stdout)
Avisos (precios intercambiados, descartes) van a stderr; las estadísticas a stdout.

Reglas de fusión con la BD:
  - Un evento ya existente conserva su id aunque cambie el título (misma sala + fecha + título parecido).
  - Los campos "estables" (dirección, dress code, edad, descripción, line-up, hora de cierre) se
    conservan del documento existente si la extracción de hoy no los trae.
  - Precio, estado y enlace vienen siempre de la extracción de hoy (el más barato gana).
  - Los eventos sin cambios no generan escritura. La fecha de la última extracción en que apareció cada
    evento se guarda en el documento meta/seen (mapa id → fecha) y, en los documentos escritos, en `lastSeen`.
    Los no vistos hoy:
      · fecha pasada (anterior a ayer)                      → se borran
      · futuros no vistos en 3 extracciones seguidas, si al menos una de sus fuentes sí se extrajo hoy
        (o no vistos en 7 días, sea cual sea la fuente)     → se borran (cancelados / duplicados viejos)
      · el resto                                           → se dejan tal cual
  - Si dos documentos existentes corresponden al mismo evento de hoy, se conserva uno y el otro se borra.
"""
import json, re, sys, os, glob, hashlib, unicodedata, datetime

MUSIC = {"reggaeton","latino","comercial","pop","techno","house","electronica","hiphop","trap","rnb","afro","dancehall","indie","rock","dnb","hardtechno","disco","salsa","flamenco","remember","urban","variado","otros"}
MUSIC_ALIAS = {"reggaetón":"reggaeton","reggaeton":"reggaeton","latin":"latino","latino":"latino","commercial":"comercial","comercial":"comercial","mainstream":"comercial","hits":"comercial","pop":"pop","techno":"techno","tech house":"house","tech-house":"house","house":"house","afrohouse":"afro","afro house":"afro","afrobeats":"afro","afro":"afro","electronic":"electronica","electrónica":"electronica","electronica":"electronica","edm":"electronica","dance":"electronica","hip hop":"hiphop","hip-hop":"hiphop","hiphop":"hiphop","rap":"hiphop","trap":"trap","r&b":"rnb","rnb":"rnb","dancehall":"dancehall","indie":"indie","rock":"rock","drum and bass":"dnb","drum & bass":"dnb","dnb":"dnb","hard techno":"hardtechno","hardtechno":"hardtechno","industrial techno":"hardtechno","disco":"disco","funk":"disco","funky":"disco","nu-disco":"disco","salsa":"salsa","bachata":"salsa","flamenco":"flamenco","remember":"remember","80s":"remember","90s":"remember","2000s":"remember","urban":"urban","urbano":"urban","variado":"variado","mixed":"variado","otros":"otros","minimal":"techno","melodic":"house","ebm":"electronica","synth":"electronica","punk":"rock","metal":"rock","jazz":"otros","soul":"disco","garage":"house","breaks":"electronica","trance":"electronica","hardgroove":"techno"}
TYPES = {"club","concierto","fiesta","after","bar","tardeo","festival","otro"}
STATUS = {"disponible","ultimas","agotado","desconocido"}
# claves = strip(nombre); se comprueba primero la coincidencia exacta
VENUE_ALIAS = {
 "kapital":"Teatro Kapital","teatro kapital":"Teatro Kapital","fabrik":"Fabrik","fabrik madrid":"Fabrik","teatro barcelo":"Teatro Barceló","barcelo":"Teatro Barceló","shoko":"Shoko","shoko madrid":"Shoko","shôko":"Shoko","joy eslava":"Joy Eslava","teatro eslava":"Joy Eslava","mondo":"Mondo Disko","mondo disko":"Mondo Disko","club coco":"Club Cocó","goya social club":"Goya Social Club","panda":"Panda Club","panda club":"Panda Club","vandido":"Vandido","independance":"Independance Club","independance club":"Independance Club","sala but":"Sala But","but":"Sala But","sala mon":"Sala Mon","mon":"Sala Mon","copernico":"Sala Copérnico","sala copernico":"Sala Copérnico","siroco":"Siroco","lab the club":"LAB theCLUB","lab theclub":"LAB theCLUB","lab":"LAB theCLUB","lab madrid":"LAB theCLUB","nazca":"Nazca","nazca club":"Nazca","lula":"Lula Club","lula club":"Lula Club","the bassement":"The Bassement","bassement":"The Bassement","specka":"Specka","la riviera":"La Riviera","sala riviera":"La Riviera","sala caracol":"Sala Caracol","caracol":"Sala Caracol","sala el sol":"Sala El Sol","el sol":"Sala El Sol","sala sol":"Sala El Sol","moby dick":"Moby Dick","moby dick club":"Moby Dick","medias puri":"Medias Puri","unas chung lee":"Uñas Chung Lee","cadavra":"Cadavra","icon":"Icon Madrid","icon madrid":"Icon Madrid","gabana":"Gabana 1800","gabana 1800":"Gabana 1800","liberty supper club":"Liberty Supper Club","liberty":"Liberty Supper Club","rubicon":"Rubicón","istar":"Istar","istar club":"Istar","graf":"Graf","club graf":"Graf","villa panthera":"Villa Panthera","teatro magno":"Teatro Magno","fitz":"Fitz Club","fitz club":"Fitz Club","stardust":"Stardust","boite":"Boite","boite live":"Boite","blackhaus":"Blackhaus","vg fuenlabrada":"VG Fuenlabrada","hangar 48":"Hangar 48","ya'sta":"Ya'sta Club","yasta":"Ya'sta Club","ya'sta club":"Ya'sta Club","lab the club madrid":"LAB theCLUB","cafe berlin":"Café Berlín","berlin club":"Café Berlín","berlinclub":"Café Berlín","chango":"Changó","sala chango":"Changó","ochoymedio":"Ochoymedio","b12":"B12","bodeguita de enmedio":"Bodeguita de Enmedio","mitty":"Mitty","cats":"Mitty","posh":"Posh (Liberata)","liberata":"Posh (Liberata)","enbabia":"Enbabia","leona bar":"Leona Bar","houdinni":"Houdinni","todos los santos":"Todos los Santos Club","sala wagon":"Sala Wagon","wagon":"Sala Wagon","marula":"Marula Café","marula cafe":"Marula Café","new garamond":"New Garamond","opium":"Opium Madrid","opium madrid":"Opium Madrid",
 # alias añadidos tras QA
 "strong":"Sala Strong","sala strong":"Sala Strong","strong club":"Sala Strong",
 "live las ventas":"Las Ventas","las ventas":"Las Ventas",
 "mondo disko sala but":"Sala But","sala but mondo":"Sala But","sala but mondo disko":"Sala But",
 "core":"Core","core club":"Core","core madrid":"Core",
 "tiffany s":"Tiffany's The Club","tiffanys":"Tiffany's The Club","tiffany s the club":"Tiffany's The Club",
 "jazzville cafe":"Jazzville","sala vesta":"Sala Vesta","vesta":"Sala Vesta",
 "el despertar":"El Despertar Café","el despertar cafe":"El Despertar Café",
 "movistar arena":"Movistar Arena","wizink center":"Movistar Arena","palacio de los deportes":"Movistar Arena",
}

# ---------- zonas ----------
ZONE_BY_CP = {
 "28004":"Malasaña / Chueca","28012":"Centro / Sol","28013":"Centro / Sol","28014":"Centro / Sol","28005":"La Latina","28045":"Atocha",
 "28015":"Argüelles / Moncloa","28008":"Argüelles / Moncloa","28003":"Chamberí","28010":"Chamberí","28001":"Salamanca","28006":"Salamanca",
 "28009":"Salamanca","28028":"Salamanca","28007":"Retiro","28020":"Tetuán / Azca","28002":"Chamartín","28016":"Chamartín","28036":"Chamartín",
 "28018":"Vallecas","28038":"Vallecas","28031":"Vallecas","28026":"Usera / Carabanchel","28019":"Usera / Carabanchel","28025":"Usera / Carabanchel",
 "28034":"Otros norte","28042":"Barajas","28023":"Aravaca / Pozuelo","28970":"Humanes (Fabrik)","28942":"Fuenlabrada","28943":"Fuenlabrada",
 "28922":"Alcorcón","28100":"Alcobendas","28220":"Majadahonda","28046":"Chamartín","28035":"Otros norte","28029":"Otros norte","28039":"Tetuán / Azca",
 "28011":"Argüelles / Moncloa","28017":"Salamanca","28027":"Chamartín","28030":"Retiro","28033":"Chamartín","28037":"Otros","28040":"Argüelles / Moncloa",
 "28041":"Usera / Carabanchel","28043":"Chamartín","28044":"Usera / Carabanchel","28047":"Usera / Carabanchel",
}
# sala canónica → zona (manda sobre el código postal; SPEC.md "Salas conocidas")
VENUE_ZONE = {
 "Teatro Kapital":"Atocha","Fabrik":"Humanes (Fabrik)","Teatro Barceló":"Malasaña / Chueca","Shoko":"La Latina","Opium Madrid":"Chamberí","Joy Eslava":"Centro / Sol",
 "Mondo Disko":"Centro / Sol","Club Cocó":"Centro / Sol","Goya Social Club":"Salamanca","Panda Club":"Chamartín","Vandido":"Salamanca","Independance Club":"Atocha",
 "Oh My Club":"Tetuán / Azca","Sala But":"Malasaña / Chueca","Sala Mon":"Argüelles / Moncloa","Sala Copérnico":"Argüelles / Moncloa","Siroco":"Malasaña / Chueca",
 "LAB theCLUB":"Chamartín","Nazca":"Tetuán / Azca","Lula Club":"Centro / Sol","The Bassement":"Argüelles / Moncloa","Specka":"Tetuán / Azca","La Riviera":"La Latina",
 "Sala Caracol":"Atocha","Sala El Sol":"Centro / Sol","Moby Dick":"Chamartín","Medias Puri":"Centro / Sol","Uñas Chung Lee":"Centro / Sol","Toni 2":"Centro / Sol",
 "Cadavra":"Centro / Sol","Icon Madrid":"Salamanca","Gabana 1800":"Salamanca","Liberty Supper Club":"Chamberí","Rubicón":"Salamanca","Istar":"Centro / Sol","Graf":"Centro / Sol",
 "Villa Panthera":"Chamartín","Teatro Magno":"Centro / Sol","Fitz Club":"Argüelles / Moncloa","Stardust":"Centro / Sol","Boite":"Centro / Sol","Core":"Centro / Sol",
 "Blackhaus":"Aravaca / Pozuelo","VG Fuenlabrada":"Fuenlabrada","Ya'sta Club":"Malasaña / Chueca","Sala Wagon":"Atocha","Leona Bar":"Malasaña / Chueca",
 "Sala Strong":"Centro / Sol","Las Ventas":"Salamanca","Cadillac Solitario":"Otros norte","Jazzville":"Retiro","El Despertar Café":"Atocha","Sala Vesta":"Malasaña / Chueca",
 "Tiffany's The Club":"Chamartín","Bonded Club":"Chamberí","Cristo Social Club":"Salamanca","Green Social Club":"Salamanca","Kube":"Tetuán / Azca","Marabú":"Chamberí",
 "Manamá":"Centro / Sol","Todos Santos":"Malasaña / Chueca","Blue Club":"Tetuán / Azca","Etnia Club":"Tetuán / Azca","Saint Club":"Salamanca","Chamán":"Tetuán / Azca",
 "Pabblo Club":"Tetuán / Azca","Global Club":"Salamanca","Movistar Arena":"Salamanca","Café Berlín":"Centro / Sol","Changó":"Argüelles / Moncloa","Ochoymedio":"Argüelles / Moncloa",
 "B12":"Chamartín","Honky Tonk":"Chamberí","Sala Villanos":"Usera / Carabanchel","Café Central Ateneo":"Centro / Sol","Moe Club":"Chamberí","La Coquette":"Centro / Sol",
 "Café La Palma":"Malasaña / Chueca","El Sótano":"Centro / Sol","Intruso Bar":"Malasaña / Chueca","Mitty":"Centro / Sol","Maravillas Club":"Malasaña / Chueca",
 "Sala Rockville":"Centro / Sol","Fun House":"Centro / Sol","Sala Clamores":"Chamberí","Big Mama Ballroom":"Argüelles / Moncloa","Sala Uni":"Chamberí","Toy Room Madrid":"Chamberí",
 "Vennus Madrid":"Malasaña / Chueca","Elefante Blanco":"Centro / Sol","Studio 76":"Chamberí","Revi Live":"Salamanca","Sala Olvido":"Usera / Carabanchel","Sala B":"Atocha",
 "Marula Café":"La Latina","Enbabia":"Centro / Sol","Posh (Liberata)":"Centro / Sol","Houdinni":"Centro / Sol","Bodeguita de Enmedio":"Centro / Sol","Sala Silikona":"Vallecas",
 "La Nueva Cubierta de Leganés":"Otros sur","Mökai Beach Club":"Chamberí",
}
ZONES = set(ZONE_BY_CP.values()) | set(VENUE_ZONE.values()) | {"Otros","Otros sur","Barajas","Retiro"}

def infer_zone(zone, venue, address):
    if venue in VENUE_ZONE: return VENUE_ZONE[venue]
    if zone and zone.strip() and zone.strip().lower() != "otros":
        z = zone.strip()
        return z
    m = re.search(r"\b(28\d{3})\b", address or "")
    if m and m.group(1) in ZONE_BY_CP: return ZONE_BY_CP[m.group(1)]
    return "Otros"

# palabras que no cuentan como "token poco común" para fusionar
GENERIC = {"lunes","martes","miercoles","jueves","viernes","sabado","domingo","monday","tuesday","wednesday","thursday","friday","saturday","sunday",
 "enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","setiembre","octubre","noviembre","diciembre",
 "january","february","march","april","june","july","august","september","october","november","december",
 "halloween","fiesta","fiestas","noche","noches","sesion","session","sesiones","sessions","club","madrid","party","parties","night","nights",
 "especial","special","edition","edicion","presenta","presents","entradas","tickets","oficial","official","weekend","concierto","conciertos",
 "concert","directo","teatro","tardeo","afterwork","after","halloweek","halloweekend","viernes","sabados","jueves","domingos"}
WEEKDAYS = r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
GENERIC_TITLE = [re.compile(r"^"+WEEKDAYS+r" en .+"), re.compile(r"^noche en .+"), re.compile(r".+ entradas$")]
GENERIC_SOURCES = {"Bynova","Nightlife Madrid","All Madrid Nightlife","Applinkers"}
PUBCRAWL = re.compile(r"pub ?crawl|ruta de bares", re.I)
EXCLUDED = re.compile(r"karaoke|bingo|\bclases? de\b|\btalleres?\b|\btablao\b|\bteatro\b|sin esperas|shisha|cena[ -]espect[aá]culo|candlelight|infantil|\bmuseo\b|\btributo a\b|\btribute to\b|\bdrag (show|queens?)\b|this is drag|\bmon[oó]logos?\b|stand[ -]?up|\bc[oó]mico\b", re.I)
MUSICAL_TITLE = re.compile(r"\bmusical\b", re.I)                     # en el título
MUSICAL_DESC = re.compile(r"\b(el|un|del|al|este) musical\b", re.I)   # en la descripción ("propuesta musical" no cuenta)
NIGHTLIFE_VENUES = {"Teatro Kapital","Teatro Barceló","Teatro Eslava","Joy Eslava","Teatro Magno","Museo Chicote"}  # su nombre no dispara la exclusión
# teatros/auditorios con butaca: fuera salvo sesiones club/after
SEATED_VENUE = re.compile(r"^(teatro|nuevo teatro|auditorio)\b|^ateneo de madrid$|^circulo de bellas artes$")
# campos que se conservan del documento existente si la extracción de hoy no los trae
STABLE_FIELDS = ["start","end","address","dressCode","ageMin","description","lineup","music"]

def strip(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
    s = re.sub(r"\b(discoteca|club de|sala de|the club|madrid)\b"," ",s)
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def plain(s):
    """minúsculas sin acentos, sin quitar palabras."""
    return re.sub(r"[^a-z0-9]+"," ",unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()).strip()

def canon_venue(v):
    if not v: return None
    k = strip(v)
    if k in VENUE_ALIAS: return VENUE_ALIAS[k]
    for a,c in VENUE_ALIAS.items():
        if len(a)>4 and (k.startswith(a+" ") or k.endswith(" "+a)): return c
    return v.strip()

def norm_music(lst):
    out=[]
    for m in lst or []:
        k = strip(str(m))
        t = MUSIC_ALIAS.get(k) or (k if k in MUSIC else None)
        if not t:
            for a,c in MUSIC_ALIAS.items():
                if a in k: t=c; break
        if t and t not in out: out.append(t)
    return out

def num(x):
    if x is None or x=="": return None
    try:
        v=float(str(x).replace("€","").replace(",",".").strip()); return int(v) if v==int(v) else round(v,2)
    except: return None

def norm_time(s):
    """'23:30', '23.30', '23h', '23:30:00', '7:00' -> 'HH:MM' o None."""
    if s is None: return None
    m = re.match(r"^\s*(\d{1,2})(?:[:.h](\d{2}))?", str(s))
    if not m: return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h>29 or mi>59: return None
    if h>=24: h-=24
    return f"{h:02d}:{mi:02d}"

def warn(*a):
    print(*a, file=sys.stderr)

def clean(e):
    date = str(e.get("date") or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date): return None
    venue = canon_venue(e.get("venue"))
    title = (e.get("title") or "").strip()
    if not title: return None
    pmin, pmax = num(e.get("priceMin")), num(e.get("priceMax"))
    if pmin is not None and pmax is not None and pmin>pmax:
        src = next((s.get("name") for s in (e.get("sources") or []) if isinstance(s,dict) and s.get("name")), None)
        warn(f"AVISO precio intercambiado: {date} {venue} «{title[:60]}» ({src or 'sin fuente'}): priceMin {pmin} > priceMax {pmax}")
        pmin,pmax=pmax,pmin
    free = bool(e.get("free")) or pmin==0
    music = norm_music(e.get("music"))
    typ = e.get("type") if e.get("type") in TYPES else "otro"
    st = e.get("status") if e.get("status") in STATUS else "desconocido"
    srcs=[]
    for s in e.get("sources") or []:
        if isinstance(s,dict) and s.get("name") and s.get("url"): srcs.append({"name":str(s["name"])[:40],"url":str(s["url"])[:500]})
    address = (e.get("address") or None)
    return {"title":title[:140],"date":date,"start":norm_time(e.get("start")),"end":norm_time(e.get("end")),"venue":venue,"address":address,
            "zone":infer_zone(e.get("zone"), venue, address),"type":typ,"music":music,"priceMin":pmin,"priceMax":pmax,"priceText":(str(e.get("priceText"))[:160] if e.get("priceText") else None),
            "free":free,"dressCode":(str(e.get("dressCode"))[:120] if e.get("dressCode") else None),"ageMin":num(e.get("ageMin")),"lineup":[str(x)[:80] for x in (e.get("lineup") or [])][:12],
            "description":(str(e.get("description"))[:400] if e.get("description") else None),"status":st,"sources":srcs,"ticketUrl":(e.get("ticketUrl") or (srcs[0]["url"] if srcs else None)),
            "_titles":[title[:140]]}

# ---------- reglas de inclusión ----------
def excluded_reason(e, window_start):
    text = f"{e['title']} {e.get('description') or ''}"
    if PUBCRAWL.search(text):
        last = (datetime.date.fromisoformat(window_start)+datetime.timedelta(days=2)).isoformat()
        if not (window_start <= e["date"] <= last): return "pub crawl fuera de las 3 primeras noches"
    if e["type"] not in ("club","after"):
        t = text
        for v in NIGHTLIFE_VENUES | ({e["venue"]} if e.get("venue") else set()):
            t = re.sub(re.escape(v), " ", t, flags=re.I)
        if e.get("venue") and e["venue"] not in NIGHTLIFE_VENUES and SEATED_VENUE.search(plain(e["venue"])): return "categoría excluida (teatro con butaca)"
        m = EXCLUDED.search(t)
        if m: return f"categoría excluida ({m.group(0).lower()})"
        if MUSICAL_TITLE.search(e["title"]) or MUSICAL_DESC.search(e.get("description") or ""): return "categoría excluida (musical)"
    if e["type"]=="concierto":
        tm = tmin(e.get("start"))
        if tm is not None and tm < 20*60: return "concierto antes de las 20:00"
    return None

# ---------- deduplicación ----------
def tmin(s):
    """'HH:MM' -> minutos desde el mediodía anterior a la noche (00:00-05:59 cuentan como madrugada)."""
    m = re.match(r"^(\d{1,2}):(\d{2})", str(s or ""))
    if not m: return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h < 6: h += 24
    return h*60+mi

def sim(a,b):
    A=set(strip(a).split()); B=set(strip(b).split())
    if not A or not B: return 0
    return len(A&B)/min(len(A),len(B))

def rare_tokens(t, exclude=frozenset(), joined=False):
    """palabras poco comunes (≥6 letras, no genéricas ni nombre de sala); joined=True da pares unidos ('perreo lab' -> 'perreolab')."""
    ws = plain(t).split()
    cand = [a+b for a,b in zip(ws, ws[1:])] if joined else ws
    return {w for w in cand if len(w)>=6 and not w.isdigit() and w not in GENERIC and w not in exclude}

def shared_rare(a, b, exclude=frozenset()):
    ra, rb = rare_tokens(a, exclude), rare_tokens(b, exclude)
    return (ra & rb) | (rare_tokens(a, exclude, True) & rb) | (ra & rare_tokens(b, exclude, True))

def words(t, exclude=frozenset()):
    return {w for w in plain(t).split() if len(w)>=3 and not w.isdigit() and w not in GENERIC and w not in exclude}

def addr_key(a):
    """'C/ Tetuán 27, 28013 Madrid' -> 'tetuan 27' (calle + número, sin código postal)."""
    toks = [w for w in plain(a).split() if not re.match(r"^28\d{3}$", w)]
    for i,w in enumerate(toks):
        if w.isdigit() and i>0 and not toks[i-1].isdigit(): return toks[i-1]+" "+w
    return None

def same_place(m, e):
    if m.get("venue") and e.get("venue") and strip(m["venue"])==strip(e["venue"]): return True
    ka, kb = addr_key(m.get("address")), addr_key(e.get("address"))
    return bool(ka and kb and ka==kb)

def titles_match(TA, TB, venue_names, vtoks):
    for a in TA:
        for b in TB:
            if sim(a,b)>=0.5: return True
            sa, sb = strip(a), strip(b)
            short_t = sa if len(sa)<=len(sb) else sb
            if sa and sb and sa!=sb and (sa in sb or sb in sa) and sa not in venue_names and sb not in venue_names and (len(short_t.split())>=2 or len(short_t)>=12): return True
            if shared_rare(a, b, vtoks): return True
    return False

def is_match(m, e):
    if m["date"]!=e["date"]: return False
    ta, tb = tmin(m.get("start")), tmin(e.get("start"))
    if ta is not None and tb is not None and abs(ta-tb)>60: return False   # nunca fusionar si las horas difieren >60 min
    TA, TB = m.get("_titles") or [m["title"]], e.get("_titles") or [e["title"]]
    vnames = {strip(x) for x in (m.get("venue"), e.get("venue")) if x}
    vtoks = frozenset(w for x in (m.get("venue"), e.get("venue")) if x for w in plain(x).split())
    if same_place(m, e):
        if titles_match(TA, TB, vnames, vtoks): return True
        # misma sala + fecha + hora: fusiona si comparten alguna palabra no genérica o uno de los títulos es genérico
        # (sin esta condición se mezclaban salas con varias pistas, p. ej. Fabrik, o dobles sesiones de Siroco)
        if ta is not None and ta==tb:
            if any(words(a, vtoks) & words(b, vtoks) for a in TA for b in TB): return True
            if any(is_generic(t) for t in TA+TB): return True
        return False
    pairs = [(sim(a,b),a,b) for a in TA for b in TB]
    best = max(p[0] for p in pairs)
    if best>=0.8 and (not m.get("venue") or not e.get("venue")): return True
    # salas distintas: título casi igual que comparte una palabra poco común, y además misma hora o el nombre de una sala aparece en el título de la otra
    for sc,a,b in pairs:
        if sc>=0.8 and shared_rare(a, b, vtoks):
            cross = any(strip(m.get("venue") or "#") in strip(x) for x in TB) or any(strip(e.get("venue") or "#") in strip(x) for x in TA)
            if (ta is not None and ta==tb) or cross: return True
    return False

def is_generic(title):
    t = plain(title)
    return any(p.match(t) for p in GENERIC_TITLE) or t in ("sabado","viernes","jueves","saturday","friday","thursday")

def merge(a,b):
    """a: existente (prioritario cuando tiene dato); b: nuevo."""
    out=dict(a)
    for k in ["start","end","address","priceText","dressCode","ageMin","description","ticketUrl"]:
        if out.get(k) in (None,"",[]) and b.get(k) not in (None,"",[]): out[k]=b[k]
    # precio: priceMin = el más barato de todas las fuentes; priceMax y estado = los de la fuente del ticketUrl (la más barata)
    pm=[p for p in [a.get("priceMin"),b.get("priceMin")] if p is not None]
    out["priceMin"]=min(pm) if pm else None
    cheaper_new = b.get("priceMin") is not None and (a.get("priceMin") is None or b["priceMin"] < a["priceMin"])
    ticket_from_b = cheaper_new or (not a.get("ticketUrl") and bool(b.get("ticketUrl")))
    ts, other = (b, a) if ticket_from_b else (a, b)
    out["priceMax"] = ts.get("priceMax") if ts.get("priceMin") is not None or ts.get("priceMax") is not None else other.get("priceMax")
    if out["priceMax"] is not None and out["priceMin"] is not None and out["priceMax"] < out["priceMin"]: out["priceMax"]=None
    out["status"] = ts.get("status","desconocido") if ts.get("status") not in (None,"desconocido") else other.get("status","desconocido")
    if cheaper_new:
        if b.get("priceText"): out["priceText"]=b["priceText"]
        if b.get("ticketUrl"): out["ticketUrl"]=b["ticketUrl"]
        out["sources"]=[s for s in b.get("sources",[])]+[s for s in a.get("sources",[]) if s["url"] not in {x["url"] for x in b.get("sources",[])}]
        a_prices=[s for s in (a.get("priceMin"),) if s is not None]
        if a_prices and b["priceMin"] < a["priceMin"] and b.get("sources"):
            out["priceNote"]=f"Más barato en {b['sources'][0]['name']} ({b['priceMin']} €); {a['sources'][0]['name'] if a.get('sources') else 'otra fuente'} lo lista a {a['priceMin']} €"
    elif a.get("priceMin") is not None and b.get("priceMin") is not None and b["priceMin"] > a["priceMin"] and b.get("sources") and a.get("sources"):
        out["priceNote"]=f"Más barato en {a['sources'][0]['name']} ({a['priceMin']} €); {b['sources'][0]['name']} lo lista a {b['priceMin']} €"
    out["free"]=bool(a.get("free") or b.get("free"))
    out["music"]=list(dict.fromkeys((a.get("music") or [])+(b.get("music") or [])))
    out["lineup"]=list(dict.fromkeys((a.get("lineup") or [])+(b.get("lineup") or [])))[:12]
    if out.get("zone") in (None,"Otros") and b.get("zone"): out["zone"]=b["zone"]
    if out.get("type")=="otro" and b.get("type")!="otro": out["type"]=b["type"]
    out["sources"]=list(out.get("sources") or [])
    urls={s["url"] for s in out["sources"]}
    for s in b.get("sources",[]):
        if s["url"] not in urls: out["sources"].append(s); urls.add(s["url"])
    out["_titles"]=list(dict.fromkeys((a.get("_titles") or [a["title"]])+(b.get("_titles") or [b["title"]])))
    # título: el más informativo (más largo sin ser genérico)
    if len(b["title"])>len(a["title"]) and not is_generic(b["title"]): out["title"]=b["title"]
    elif is_generic(a["title"]) and not is_generic(b["title"]): out["title"]=b["title"]
    return out

def dedupe(events):
    merged=[]
    for e in events:
        hit=next((m for m in merged if is_match(m,e)), None)
        if hit: hit.update(merge(hit,e))
        else: merged.append(e)
    # pasadas extra hasta que no haya cambios (los títulos y horas cambian durante la fusión)
    changed=True
    while changed:
        changed=False; out=[]
        for e in merged:
            hit=next((m for m in out if is_match(m,e)), None)
            if hit: hit.update(merge(hit,e)); changed=True
            else: out.append(e)
        merged=out
    return merged

def drop_generic(merged):
    """Quita entradas semanales genéricas ('Viernes en X', 'X - Entradas') si esa noche la sala tiene un evento con nombre."""
    keep=[]; dropped=0
    named=[e for e in merged if not is_generic(e["title"])]
    for e in merged:
        names={s["name"] for s in e.get("sources",[])}
        if is_generic(e["title"]) and names and names<=GENERIC_SOURCES and names&{"Bynova","Nightlife Madrid"}:
            if any(n is not e and n["date"]==e["date"] and same_place(n,e) for n in named):
                warn(f"descartado (genérico semanal): {e['date']} {e['venue']} «{e['title'][:60]}»"); dropped+=1; continue
        keep.append(e)
    return keep, dropped

def make_id(e):
    key = f"{strip(e.get('venue') or '')}|{e['date']}|{strip(e['title'])[:40]}"
    return e["date"]+"-"+hashlib.sha1(key.encode()).hexdigest()[:10]

def madrid_today():
    now=datetime.datetime.now(datetime.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        local=now.astimezone(ZoneInfo("Europe/Madrid"))
    except Exception:
        local=now.astimezone(datetime.timezone(datetime.timedelta(hours=1)))
    return (local-datetime.timedelta(hours=6)).strftime("%Y-%m-%d")

# ---------- estado actual de la BD ----------
ID_RE=re.compile(r"(\d{4}-\d{2}-\d{2}-[0-9a-f]{10})")
def parse_versions(txt):
    """Extrae {id: version} de texto libre: '"<id>"  795 bytes  version 2  "/ruta"' o '"<id>" 2,' o '<id> 2'."""
    out={}
    ms=list(ID_RE.finditer(txt))
    for i,m in enumerate(ms):
        seg=txt[m.end(): ms[i+1].start() if i+1<len(ms) else len(txt)]
        seg=seg.split("\n",1)[0] if "version" not in seg else seg
        v=re.search(r"version\s*[:=]?\s*(\d+)",seg)
        if not v: v=re.match(r"[^0-9\n]{0,6}(\d+)(?!\d*\s*bytes)",seg)
        if v: out[m.group(1)]=int(v.group(1))
    return out

def load_seen(path):
    """mapa id → última fecha vista (meta/seen) si existe en el directorio."""
    for p in (os.path.join(path,"meta","seen.json"), os.path.join(path,"seen.json")):
        if os.path.exists(p):
            try:
                d=json.load(open(p))
                d=d.get("data",d) if isinstance(d,dict) else {}
                d=d.get("ids",d) if isinstance(d,dict) else {}
                return {k:v for k,v in d.items() if isinstance(v,str)}
            except Exception as ex: warn("ERROR leyendo",p,ex)
    return {}

def load_existing(path):
    """Devuelve {id: {"version": int|None, "data": {...}}}."""
    existing={}
    if not path or path=="-" or not os.path.exists(path): return existing
    def add(d):
        if not isinstance(d,dict) or "id" not in d: return
        data=d.get("data") if isinstance(d.get("data"),dict) else {k:v for k,v in d.items() if k not in ("id","version","updatedAt","_meta")}
        existing[d["id"]]={"version":d.get("version"),"data":data}
    if os.path.isdir(path):
        # directorio de ArtifactData out_dir: busca <algo>/events/*.json o *.json directamente
        files=sorted(glob.glob(os.path.join(path,"events","*.json")) or glob.glob(os.path.join(path,"*.json")))
        versions={}
        for vt in glob.glob(os.path.join(path,"*.txt"))+glob.glob(os.path.join(path,"events","*.txt")):
            try: versions.update(parse_versions(open(vt,errors="ignore").read()))
            except Exception as ex: warn("ERROR leyendo",vt,ex)
        for extra in ("index.json","_index.json","versions.json"):
            p=os.path.join(path,extra)
            if os.path.exists(p):
                try:
                    for d in json.load(open(p)): versions[d["id"]]=d.get("version")
                except Exception: pass
        for f in files:
            name=os.path.basename(f)[:-5]
            if name.endswith(".meta") or name in ("index","_index","versions"): continue
            try: d=json.load(open(f))
            except Exception as ex: warn("ERROR leyendo",f,ex); continue
            if not isinstance(d,dict): continue
            if "data" in d and isinstance(d["data"],dict):   # {"id","version","data"}
                existing[d.get("id",name)]={"version":d.get("version"),"data":d["data"]}
            else:
                v=d.pop("version",None) if "version" in d and "date" not in d else d.get("_version")
                data={k:v2 for k,v2 in d.items() if not k.startswith("_") and k!="version"}
                existing[name]={"version":versions.get(name,v),"data":data}
            mp=f[:-5]+".meta.json"
            if os.path.exists(mp):
                try: existing[name]["version"]=json.load(open(mp)).get("version",existing[name]["version"])
                except Exception: pass
        return existing
    txt=open(path).read().strip()
    if not txt: return existing
    if txt.startswith("["):
        for d in json.loads(txt): add(d)
    else:
        for line in txt.splitlines():
            line=line.strip()
            if line.startswith("{"):
                try: add(json.loads(line))
                except Exception: continue
    return existing

def main(data_dir, existing_path, out_dir, today=None, force=False):
    today=today or madrid_today()
    yesterday=(datetime.date.fromisoformat(today)-datetime.timedelta(days=1)).isoformat()
    stale_limit=(datetime.date.fromisoformat(today)-datetime.timedelta(days=2)).isoformat()   # no visto en 3 extracciones seguidas
    hard_limit=(datetime.date.fromisoformat(today)-datetime.timedelta(days=6)).isoformat()    # no visto en 7 días
    events=[]; drops={}; nread=0; files_read=[]
    for f in sorted(glob.glob(os.path.join(data_dir,"*.json"))):
        try: arr=json.load(open(f))
        except Exception as ex: warn("ERROR leyendo",f,ex); continue
        n0=len(events); files_read.append(os.path.basename(f))
        for e in arr if isinstance(arr,list) else []:
            c=clean(e) if isinstance(e,dict) else None
            if not c: continue
            nread+=1
            r=excluded_reason(c, today)
            if r: drops[r.split(" (")[0]]=drops.get(r.split(" (")[0],0)+1; warn(f"descartado ({r}): {c['date']} {c['venue']} «{c['title'][:60]}»"); continue
            if c["date"]<today: drops["pasado"]=drops.get("pasado",0)+1; continue
            events.append(c)
        warn(f"{os.path.basename(f)}: {len(events)-n0} eventos válidos")
    merged=dedupe(events)
    merged,ngen=drop_generic(merged)
    if ngen: drops["genérico semanal"]=ngen
    existing=load_existing(existing_path)
    seen_old=load_seen(existing_path) if existing_path and os.path.isdir(existing_path) else {}
    nver=sum(1 for x in existing.values() if x.get("version") is not None)
    if existing and nver==0 and not force:
        warn("ERROR: hay",len(existing),"documentos existentes pero ninguna versión conocida. Crea versions.txt en",existing_path,"con las parejas id/versión que imprime ArtifactData (o usa --force).")
        sys.exit(2)
    if existing and nver<len(existing): warn(f"AVISO: {len(existing)-nver} documentos existentes sin versión conocida; sus escrituras fallarán.")
    seen_new={}
    # fuentes extraídas hoy (para decidir si un evento ausente se puede dar por cancelado)
    sources_today={s["name"] for e in merged for s in e["sources"]}
    now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.join(out_dir,"docs"),exist_ok=True)
    for old in glob.glob(os.path.join(out_dir,"docs","*.json")): os.remove(old)
    for old in glob.glob(os.path.join(out_dir,"batch*_*.json")): os.remove(old)
    writes=[]; seen=set(); counts={"nuevos":0,"actualizados":0,"sinCambios":0,"borradosPasados":0,"borradosCancelados":0,"borradosDuplicados":0,"conservadosNoVistos":0}
    def by_place_date(e):
        out=[]
        for xid,x in existing.items():
            xd=x["data"]
            if xd.get("date")!=e["date"]: continue
            if strip(xd.get("venue") or "")==strip(canon_venue(e.get("venue")) or "") or (addr_key(xd.get("address")) and addr_key(xd.get("address"))==addr_key(e.get("address"))):
                out.append((xid,x))
        return out
    for e in merged:
        titles=e.get("_titles") or [e["title"]]
        eid=make_id(e)
        if eid in seen: continue
        # si existe un doc previo con misma sala/dirección+fecha y título parecido pero distinto id, conservar su id
        cands=[]
        if eid in existing: cands.append(eid)
        for xid,x in by_place_date(e):
            if xid in seen or xid==eid: continue
            xd=x["data"]
            tt=[t for t in titles if len(strip(t).split())>=2] or titles
            if max(sim(xd.get("title",""),t) for t in tt)>=0.5: cands.append(xid)
        if cands:
            eid=cands[0]
            for dup in cands[1:]:   # duplicados antiguos del mismo evento → fuera
                if dup in seen: continue
                seen.add(dup); writes.append({"op":"delete","collection":"events","doc_id":dup,"if_version":existing[dup]["version"]})
                counts["borradosDuplicados"]+=1
        seen.add(eid)
        doc={k:v for k,v in e.items() if v not in (None,[],"") and not k.startswith("_")}
        if eid in existing:
            old=dict(existing[eid]["data"])
            for k in STABLE_FIELDS:
                if k not in doc and old.get(k) not in (None,[],""): doc[k]=old[k]
            if doc.get("zone")=="Otros" and old.get("zone") not in (None,"","Otros","otros"): doc["zone"]=old["zone"]
            seen_new[eid]=today
            cmp_old={k:v for k,v in old.items() if k not in ("updatedAt","lastSeen")}
            if cmp_old==doc:
                counts["sinCambios"]+=1
                continue
            doc["updatedAt"]=now; doc["lastSeen"]=today
            writes.append({"op":"set","collection":"events","doc_id":eid,"data":doc,"if_version":existing[eid]["version"]})
            counts["actualizados"]+=1
        else:
            doc["updatedAt"]=now; doc["lastSeen"]=today; seen_new[eid]=today
            writes.append({"op":"set","collection":"events","doc_id":eid,"data":doc})
            counts["nuevos"]+=1
    # documentos existentes que no han aparecido hoy
    for xid,x in existing.items():
        if xid in seen: continue
        d=x["data"].get("date","")
        last=(seen_old.get(xid) or x["data"].get("lastSeen") or (x["data"].get("updatedAt") or "")[:10] or "0000-00-00")
        if not d or d < yesterday:
            writes.append({"op":"delete","collection":"events","doc_id":xid,"if_version":x["version"]}); counts["borradosPasados"]+=1
        elif d >= today and last <= stale_limit and (last <= hard_limit or any(s.get("name") in sources_today for s in x["data"].get("sources",[]))):
            writes.append({"op":"delete","collection":"events","doc_id":xid,"if_version":x["version"]}); counts["borradosCancelados"]+=1
            warn(f"borrado (no visto desde {last}): {d} {x['data'].get('venue')} «{str(x['data'].get('title'))[:60]}»")
        else:
            counts["conservadosNoVistos"]+=1; seen_new[xid]=last
    # quitar if_version nulos (documentos cuya versión no conocemos)
    for w in writes:
        if w.get("if_version") is None: w.pop("if_version",None)
    for e in merged: e.pop("_titles",None)
    json.dump(merged,open(os.path.join(out_dir,"merged.json"),"w"),ensure_ascii=False,indent=1)
    # lotes: inline (batch_NN) y con file_path (batchf_NN)
    docs_dir=os.path.abspath(os.path.join(out_dir,"docs"))
    for w in writes:
        if w["op"]=="set":
            p=os.path.join(docs_dir,w["doc_id"]+".json")
            json.dump(w["data"],open(p,"w"),ensure_ascii=False)
    nb=0
    for i in range(0,len(writes),50):
        chunk=writes[i:i+50]
        json.dump(chunk,open(os.path.join(out_dir,f"batch_{i//50:02d}.json"),"w"),ensure_ascii=False)
        fchunk=[]
        for w in chunk:
            if w["op"]=="set":
                w2={k:v for k,v in w.items() if k!="data"}; w2["file_path"]=os.path.join(docs_dir,w["doc_id"]+".json"); fchunk.append(w2)
            else: fchunk.append(w)
        json.dump(fchunk,open(os.path.join(out_dir,f"batchf_{i//50:02d}.json"),"w"),ensure_ascii=False)
        nb+=1
    stats={}
    for e in merged:
        for s in e["sources"]: stats[s["name"]]=stats.get(s["name"],0)+1
    if drops: warn("descartes:", json.dumps(drops,ensure_ascii=False))
    json.dump({"updated":now,"ids":seen_new},open(os.path.join(out_dir,"seen.json"),"w"),ensure_ascii=False)
    summary={"hoy":today,"archivos":files_read,"leidos":nread,"unicos":len(merged),"escrituras":len(writes),"lotes":nb,"enBD":len(existing),"eventCountTrasSubida":len(existing)+counts["nuevos"]-counts["borradosPasados"]-counts["borradosCancelados"]-counts["borradosDuplicados"],**counts,"descartes":drops,"porFuente":dict(sorted(stats.items(),key=lambda kv:-kv[1]))}
    json.dump(summary,open(os.path.join(out_dir,"summary.json"),"w"),ensure_ascii=False,indent=1)
    status={"lastUpdated":now,"eventCount":summary["eventCountTrasSubida"],"sources":summary["porFuente"],"run":{"date":today,"new":counts["nuevos"],"updated":counts["actualizados"],"deleted":counts["borradosPasados"]+counts["borradosCancelados"]+counts["borradosDuplicados"],"unchanged":counts["sinCambios"],"files":files_read},"running":False,"note":"Actualización diaria"}
    json.dump(status,open(os.path.join(out_dir,"status.json"),"w"),ensure_ascii=False,indent=1)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    args=[a for a in sys.argv[1:] if not a.startswith("--")]
    today=None
    for i,a in enumerate(sys.argv):
        if a=="--today" and i+1<len(sys.argv): today=sys.argv[i+1]
        if a.startswith("--today="): today=a.split("=",1)[1]
    if len(args)<1: print(__doc__); sys.exit(1)
    main(args[0], args[1] if len(args)>1 else None, args[2] if len(args)>2 else "out", today, force="--force" in sys.argv)
