#!/usr/bin/env python3
"""Fusiona data/*.json en eventos únicos y genera los documentos "chunk" para la base de datos del artifact
y el events.json de la versión web estática.

Uso: python3 -I merge.py data/ EXISTENTE out/ [--today YYYY-MM-DD]
  data/      archivos *.json de los agentes extractores (arrays de eventos según SPEC.md).
  EXISTENTE  estado actual: un directorio tal como lo deja `ArtifactData query … out_dir`
               - …/chunks/chunk-NN.json  (formato actual: {"i","n","events":[…]}), o
               - …/events/<id>.json      (formato antiguo, un documento por evento; solo lectura),
             o un events.json (array de eventos con id), o "-" / inexistente si está vacío.
             Las versiones de los chunks existentes pueden darse en <EXISTENTE>/versions.txt (líneas
             "chunk-00 3" o el texto del resultado de la herramienta pegado tal cual); si faltan, el
             archivo de escrituras no lleva if_version y hay que ponerlo a mano antes de subir.
  out/       se escriben:
               chunks/chunk-NN.json   documentos a escribir en la colección `chunks` (≤ 150 KB cada uno)
               writes.json            lista de escrituras para `ArtifactData` (set de cada chunk con
                                      file_path + delete de los chunks sobrantes), con if_version si se conoce
               events.json            todos los eventos (para la web estática: docs/data/events.json)
               status.json            documento meta/status (también docs/data/status.json)
               merged.json            eventos únicos de la extracción de hoy (depuración)
               summary.json           estadísticas (también por stdout)
Avisos (precios intercambiados, descartes) van a stderr; las estadísticas a stdout.

Reglas de fusión con lo existente:
  - Un evento ya existente conserva su id aunque cambie el título (misma sala + fecha + título parecido).
  - Los campos "estables" (dirección, dress code, edad, descripción, line-up, música, hora de cierre) se
    conservan del evento existente si la extracción de hoy no los trae. Precio, estado y enlace vienen
    siempre de la extracción de hoy (el más barato gana).
  - Cada evento lleva `lastSeen` (fecha de la última extracción en que apareció). Los no vistos hoy:
      · fecha anterior a ayer                                → se quitan
      · futuros no vistos en 3 extracciones seguidas, si alguna de sus fuentes sí se extrajo hoy
        (o no vistos en 7 días, sea cual sea la fuente)      → se quitan (cancelados / duplicados viejos)
      · el resto                                            → se conservan tal cual
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
 "concert","directo","teatro","tardeo","afterwork","after","halloweek","halloweekend","viernes","sabados","jueves","domingos",
 # plurales en inglés: "FRIDAYS" en Saint Club, Rubicón y Vennus a las 00:00 se fusionaban como si fuera el mismo evento
 "mondays","tuesdays","wednesdays","thursdays","fridays","saturdays","sundays"}
WEEKDAYS = r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
WEEKDAYS_EN = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)"
GENERIC_TITLE = [re.compile(r"^"+WEEKDAYS+r"s? (en |de |at |night |noche )?[a-z0-9 ']{1,40}$"), re.compile(r"^noche en .+"), re.compile(r".+ entradas$"),
                 re.compile(r"^[a-z0-9 ']{1,40} "+WEEKDAYS+r"s?$"), re.compile(r"^"+WEEKDAYS_EN+r"('?s)? (at|in|night|nights) [a-z0-9 ']{1,40}$"),
                 re.compile(r"^[a-z0-9 ']{1,40} "+WEEKDAYS_EN+r"('?s)?$"), re.compile(r"^(sesion|session|fiesta|noche|night|party|club) (de )?"+WEEKDAYS+r"s?$"),
                 re.compile(r"^("+WEEKDAYS+r"|"+WEEKDAYS_EN+r")( ?s)?$"),
                 # entradas fijas de agenda de bares de música ("Concierto de Jazz" cada noche en El Despertar Café)
                 re.compile(r"^(concierto|conciertos|jam session|jam|musica en directo|musica en vivo|directo)( de| en)?( jazz| blues| swing| soul| funk| directo| vivo)?$")]
GENERIC_SOURCES = {"Bynova","Nightlife Madrid","All Madrid Nightlife","Applinkers","Discomadrid","Discoruta","Clubbable","Discotecas Gratis","Fourvenues"}
# nombre de fuente según el host del enlace: varias webs (Applinkers, All Madrid Nightlife, Bynova…) enlazan a la misma
# página de la ticketera; para el usuario la fuente real es la ticketera y un mismo enlace no debe salir tres veces
HOST_SOURCE = [("site.fourvenues.com","Fourvenues"),("fourvenues.com","Fourvenues"),("xceed.me","Xceed"),("dice.fm","DICE"),("feverup.com","Fever"),("fever.pxf.io","Fever"),
               ("app.whan.es","WHAN"),("whan.es","WHAN"),("ra.co","Resident Advisor"),("shotgun.live","Shotgun"),("taquilla.com","Taquilla.com"),
               ("eventbrite.","Eventbrite"),("entradium.com","Entradium"),("wegow.com","Wegow"),("discotech.me","Discotech"),("tickets.nightlifemadrid.com","Nightlife Madrid")]
def source_name_for(url, default):
    try: host=re.match(r"https?://([^/?#]+)", str(url).lower()).group(1).replace("www.","")
    except Exception: return default
    for h,n in HOST_SOURCE:
        if h in host: return n
    return default
# fuentes que no se usan (petición del usuario, 30 oct 2026): se quitan de los eventos y, si un evento solo venía de ellas, se descarta
EXCLUDED_SOURCES = {"Madrid Lux","MadridLux","madridlux.com"}
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
        if isinstance(s,dict) and s.get("name") and s.get("url"):
            if s["name"] in EXCLUDED_SOURCES or "madridlux.com" in str(s["url"]): continue
            srcs.append({"name":source_name_for(s["url"], str(s["name"]))[:40],"url":str(s["url"])[:500]})
    srcs=dedupe_sources(srcs)
    if not srcs and (e.get("sources") or []): return None   # solo venía de fuentes excluidas
    address = (e.get("address") or None)
    return {"title":title[:140],"date":date,"start":norm_time(e.get("start")),"end":norm_time(e.get("end")),"venue":venue,"address":address,
            "zone":infer_zone(e.get("zone"), venue, address),"type":typ,"music":music,"priceMin":pmin,"priceMax":pmax,"priceText":(str(e.get("priceText"))[:160] if e.get("priceText") else None),
            "free":free,"dressCode":(str(e.get("dressCode"))[:120] if e.get("dressCode") else None),"ageMin":num(e.get("ageMin")),"lineup":[str(x)[:80] for x in (e.get("lineup") or [])][:12],
            "description":(str(e.get("description"))[:400] if e.get("description") else None),"status":st,"sources":srcs,"ticketUrl":((e.get("ticketUrl") if e.get("ticketUrl") and "madridlux.com" not in str(e.get("ticketUrl")) else None) or (srcs[0]["url"] if srcs else None)),
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

SELLER_HOSTS = ("xceed.me","dice.fm","feverup.com","app.whan.es","site.fourvenues.com","fourvenues.com","ra.co","shotgun.live","taquilla.com","eventbrite","entradium.com","wegow.com","tickets.nightlifemadrid.com","geeticket","oneboxtds","tomaticket","woutick","enterticket","discotech.me",
              "entradas.conciertos.club","tixxlab.com","ticketmaster.es","entradas.com","eventim-light.com","ticketclub.es")
def ticket_key(u):
    """Clave de comparación de un enlace de compra: host + ruta sin parámetros ni barra final, en minúsculas. None si no es una ticketera conocida."""
    if not u: return None
    u=str(u).strip().lower()
    m=re.match(r"https?://([^/?#]+)([^?#]*)", u)
    if not m: return None
    host=m.group(1).replace("www.",""); path=m.group(2).rstrip("/")
    if not any(h in host for h in SELLER_HOSTS): return None
    path=re.sub(r"/(es|en)(/|$)", "/", path)          # xceed.me/es/... y /en/... son la misma página
    if not path or path in ("/","/events","/event"): return None
    if "fourvenues.com" in host:
        # el código del evento es global: /es/allmadridnightlife/events/QBP3 y /es/nova-nightlife-madrid/events/QBP3 son la misma sesión
        fv=re.search(r"/events/([a-z0-9]+)$", path)
        if fv: return "fourvenues.com/events/"+fv.group(1)
    if host.endswith("ra.co"): host="ra.co"           # es.ra.co/events/N = ra.co/events/N
    # parámetros que identifican la sesión: taquilla.com/entradas/fabrik?event=32696751 y ?event=32745876 son dos noches distintas
    q=re.search(r"[?&](event|session|sesion|session_id|sessionid|event_id|eventid)=([^&#]+)", u)
    if q: path+=f"?{q.group(1)}={q.group(2)}"
    return host+path

def fourvenues_codes(e):
    return {k for k in ticket_keys(e) if k.startswith("fourvenues.com/events/")}

def ticket_keys(e):
    ks={ticket_key(e.get("ticketUrl"))}
    for s in e.get("sources") or []: ks.add(ticket_key(s.get("url")))
    ks.discard(None); return ks

def dedupe_sources(srcs):
    """Quita enlaces repetidos (misma página de ticketera aunque cambie es/en o parámetros) y nombres repetidos con la misma url."""
    out=[]; keys=set()
    for s in srcs:
        k=ticket_key(s["url"]) or s["url"].rstrip("/").lower()
        if k in keys: continue
        keys.add(k); out.append(s)
    return out

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
    if m["date"]!=e["date"]:
        # mismo enlace de compra con fechas vecinas: una fuente puso la fecha natural de una sesión de madrugada
        if abs((datetime.date.fromisoformat(m["date"])-datetime.date.fromisoformat(e["date"])).days)==1 and ticket_keys(m)&ticket_keys(e): return True
        return False
    if ticket_keys(m)&ticket_keys(e): return True
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
            # misma sala, misma noche y misma hora de inicio con títulos cortos (nombres de artista): es el mismo cartel
            if all(len(plain(t).split())<=3 for t in TA+TB): return True
        # entrada semanal genérica ("Viernes", "Graf Fridays", "Concierto de Jazz") a ≤30 min de otra sesión de la misma sala
        # (≤60 si las dos son genéricas): es la misma noche publicada por dos webs con horas redondeadas distintas
        if ta is not None and tb is not None and not any(PUBCRAWL.search(t) for t in TA+TB):
            ga, gb = any(is_generic(t) for t in TA), any(is_generic(t) for t in TB)
            if (ga and gb) or ((ga or gb) and abs(ta-tb)<=30): return True
        return False
    # salas distintas con códigos de Fourvenues distintos: son sesiones distintas (cada código es una sesión)
    fa, fb = fourvenues_codes(m), fourvenues_codes(e)
    if fa and fb and not (fa & fb): return False
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
    return any(p.match(t) for p in GENERIC_TITLE) or t in ("lunes","martes","miercoles","jueves","viernes","sabado","domingo","monday","tuesday","wednesday","thursday","friday","saturday","sunday")

DIRECT_SELLER = ("feverup.com","xceed.me","dice.fm","app.whan.es","site.fourvenues.com","taquilla.com","shotgun.live","eventbrite.","entradium.com","wegow.com","tickets.nightlifemadrid.com")
def seller_rank(e):
    """0 = el precio viene de la página propia de la ticketera (alguna fuente del evento ES la ticketera); 1 = de un agregador o afiliado."""
    for s0 in e.get("sources") or []:
        u=str(s0.get("url") or "").lower()
        if any(h in u for h in DIRECT_SELLER) and "pxf.io" not in u: return 0
    return 1

def merge(a,b):
    """a: existente (prioritario cuando tiene dato); b: nuevo."""
    # si solo uno de los dos trae el precio desde la página propia de la ticketera, ese manda (los agregadores
    # repiten precios viejos o de afiliado): se intercambian los papeles para que su precio/enlace sea el elegido
    if a.get("priceMin") is not None and b.get("priceMin") is not None and seller_rank(a)!=seller_rank(b):
        direct, other = (a,b) if seller_rank(a)==0 else (b,a)
        other=dict(other); other["priceMin"]=None; other["priceMax"]=None; other["priceText"]=None   # el agregador no compite en precio
        a,b = (direct,other) if direct is a else (other,direct)
        if direct is not a and not a.get("ticketUrl"): pass
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
    out["sources"]=dedupe_sources(out["sources"])
    out["_titles"]=list(dict.fromkeys((a.get("_titles") or [a["title"]])+(b.get("_titles") or [b["title"]])))
    # título: el más informativo (más largo sin ser genérico); dos nombres cortos distintos (cartel) se unen con " + "
    ta_, tb_ = a["title"], b["title"]
    if len(plain(ta_).split())<=3 and len(plain(tb_).split())<=3 and strip(ta_)!=strip(tb_) and strip(tb_) not in strip(ta_) and strip(ta_) not in strip(tb_) and not is_generic(ta_) and not is_generic(tb_) and len(ta_)+len(tb_)<120:
        out["title"]=ta_+" + "+tb_
        out["lineup"]=list(dict.fromkeys(out.get("lineup",[])+[ta_,tb_]))[:12]
    elif len(b["title"])>len(a["title"]) and not is_generic(b["title"]): out["title"]=b["title"]
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
        if is_generic(e["title"]) and names and names<=GENERIC_SOURCES:
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

# ---------- estado actual ----------
ID_RE=re.compile(r"(chunk-\d{2,3}|\d{4}-\d{2}-\d{2}-[0-9a-f]{10})")
def parse_versions(txt):
    """Extrae {id: version} de texto libre: '"chunk-00"  120000 bytes  version 2  "/ruta"' o 'chunk-00 2'."""
    out={}
    ms=list(ID_RE.finditer(txt))
    for i,m in enumerate(ms):
        seg=txt[m.end(): ms[i+1].start() if i+1<len(ms) else len(txt)]
        seg=seg.split("\n",1)[0] if "version" not in seg else seg
        v=re.search(r"version\s*[:=]?\s*(\d+)",seg)
        if not v: v=re.match(r"[^0-9\n]{0,6}(\d+)(?!\d*\s*bytes)",seg)
        if v: out[m.group(1)]=int(v.group(1))
    return out

def load_existing(path):
    """Devuelve (eventos existentes {id: evento}, chunks existentes {doc_id: version|None})."""
    events={}; chunks={}
    if not path or path=="-" or not os.path.exists(path): return events, chunks
    def add_event(e, eid=None):
        if not isinstance(e,dict): return
        eid = eid or e.get("id")
        if not eid or not e.get("date"): return
        events[eid]={k:v for k,v in e.items() if k!="id"}
    if os.path.isdir(path):
        versions={}
        for vt in glob.glob(os.path.join(path,"*.txt"))+glob.glob(os.path.join(path,"chunks","*.txt")):
            try: versions.update(parse_versions(open(vt,errors="ignore").read()))
            except Exception as ex: warn("ERROR leyendo",vt,ex)
        cfiles=sorted(glob.glob(os.path.join(path,"chunks","*.json")))
        for f in cfiles:
            name=os.path.basename(f)[:-5]
            try: d=json.load(open(f))
            except Exception as ex: warn("ERROR leyendo",f,ex); continue
            d=d.get("data",d) if isinstance(d,dict) and "data" in d and "events" not in d else d
            chunks[name]=versions.get(name, d.get("version") if isinstance(d,dict) else None)
            for e in (d.get("events") or []) if isinstance(d,dict) else []: add_event(e)
        if not cfiles:
            for f in sorted(glob.glob(os.path.join(path,"events","*.json"))):
                name=os.path.basename(f)[:-5]
                if name.endswith(".meta"): continue
                try: d=json.load(open(f))
                except Exception as ex: warn("ERROR leyendo",f,ex); continue
                if isinstance(d,dict) and isinstance(d.get("data"),dict): add_event(d["data"], d.get("id",name))
                else: add_event(d, name)
        return events, chunks
    try:
        d=json.load(open(path))
        for e in (d if isinstance(d,list) else d.get("events",[])): add_event(e)
    except Exception as ex: warn("ERROR leyendo",path,ex)
    return events, chunks

CHUNK_BYTES=150_000

def main(data_dir, existing_path, out_dir, today=None):
    today=today or madrid_today()
    yesterday=(datetime.date.fromisoformat(today)-datetime.timedelta(days=1)).isoformat()
    stale_limit=(datetime.date.fromisoformat(today)-datetime.timedelta(days=2)).isoformat()   # no visto en 3 extracciones seguidas
    hard_limit=(datetime.date.fromisoformat(today)-datetime.timedelta(days=6)).isoformat()    # no visto en 7 días
    events=[]; drops={}; nread=0; files_read=[]
    for f in sorted(glob.glob(os.path.join(data_dir,"*.json"))) if data_dir and os.path.isdir(data_dir) else []:
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
    existing, old_chunks = load_existing(existing_path)
    sources_today={s["name"] for e in merged for s in e["sources"]}
    now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    final={}; seen=set()
    counts={"nuevos":0,"actualizados":0,"sinCambios":0,"quitadosPasados":0,"quitadosCancelados":0,"quitadosDuplicados":0,"conservadosNoVistos":0}
    by_date={}
    for xid,xd in existing.items(): by_date.setdefault(xd.get("date"),[]).append((xid,xd))
    today_by_date={}   # fecha -> [(id, evento de hoy con _titles)] para fundir existentes no vistos que son duplicados
    for e in merged:
        titles=e.get("_titles") or [e["title"]]
        eid=make_id(e)
        if eid in seen: continue
        cands=[eid] if eid in existing else []
        v_e=strip(canon_venue(e.get("venue")) or ""); a_e=addr_key(e.get("address"))
        tt=[t for t in titles if len(strip(t).split())>=2] or titles
        for xid,xd in by_date.get(e["date"],[]):
            if xid in seen or xid in cands: continue
            if ticket_keys(e) & ticket_keys(xd): cands.append(xid); continue   # mismo enlace de compra (p. ej. feverup.com/m/124925)
            if strip(xd.get("venue") or "")==v_e or (a_e and addr_key(xd.get("address"))==a_e):
                if max(sim(xd.get("title",""),t) for t in tt)>=0.5: cands.append(xid)
        if cands:
            eid=cands[0]
            for dup in cands[1:]:
                if dup not in seen: seen.add(dup); counts["quitadosDuplicados"]+=1
        seen.add(eid)
        doc={k:v for k,v in e.items() if v not in (None,[],"") and not k.startswith("_")}
        if eid in existing:
            old=existing[eid]
            for k in STABLE_FIELDS:
                if k not in doc and old.get(k) not in (None,[],""): doc[k]=old[k]
            if doc.get("zone")=="Otros" and old.get("zone") not in (None,"","Otros","otros"): doc["zone"]=old["zone"]
            cmp_old={k:v for k,v in old.items() if k not in ("updatedAt","lastSeen")}
            if cmp_old==doc:
                counts["sinCambios"]+=1; doc["updatedAt"]=old.get("updatedAt",now)
            else:
                counts["actualizados"]+=1; doc["updatedAt"]=now
        else:
            counts["nuevos"]+=1; doc["updatedAt"]=now
        doc["lastSeen"]=today
        final[eid]=doc
        today_by_date.setdefault(e["date"],[]).append((eid,e))
    for xid,xd in existing.items():
        if xid in seen: continue
        xs=[s0 for s0 in xd.get("sources",[]) if s0.get("name") not in EXCLUDED_SOURCES and "madridlux.com" not in str(s0.get("url",""))]
        if not xs: counts["quitadosFuenteExcluida"]=counts.get("quitadosFuenteExcluida",0)+1; continue
        if len(xs)!=len(xd.get("sources",[])):
            xd=dict(xd); xd["sources"]=xs
            if "madridlux.com" in str(xd.get("ticketUrl","")): xd["ticketUrl"]=xs[0]["url"]
        d=xd.get("date",""); last=(xd.get("lastSeen") or (xd.get("updatedAt") or "")[:10] or "0000-00-00")
        # no visto hoy pero es el mismo evento que uno de hoy (otro título/hora de otra fuente, p. ej. de un agente o de una
        # extracción anterior): se funde en el de hoy en vez de salir duplicado; aporta precio y campos que falten
        if d and d >= today and xd.get("title"):
            xm=dict(xd, venue=canon_venue(xd.get("venue")))
            hit=next((eid for eid,e in today_by_date.get(d,[]) if is_match(e,xm)), None)
            if hit:
                doc=final[hit]; before=json.dumps(doc,sort_keys=True,ensure_ascii=False)
                if doc.get("priceMin") is None and doc.get("priceMax") is None and (xd.get("priceMin") is not None or xd.get("priceMax") is not None):
                    for k in ("priceMin","priceMax","priceText"):
                        if xd.get(k) is not None: doc[k]=xd[k]
                    if xd.get("free"): doc["free"]=True
                    if doc.get("status") in (None,"desconocido") and xd.get("status") not in (None,"desconocido"): doc["status"]=xd["status"]
                for k in STABLE_FIELDS:
                    if doc.get(k) in (None,[],"") and xd.get(k) not in (None,[],""): doc[k]=xd[k]
                doc["sources"]=dedupe_sources(list(doc.get("sources") or [])+[s0 for s0 in xs if s0.get("url") not in {x.get("url") for x in doc.get("sources") or []}])
                if json.dumps(doc,sort_keys=True,ensure_ascii=False)!=before: doc["updatedAt"]=now
                warn(f"fundido con uno de hoy (no visto): {d} {xd.get('venue')} «{str(xd.get('title'))[:50]}» -> «{doc.get('title','')[:50]}»")
                counts["quitadosDuplicados"]+=1; continue
        if not d or d < yesterday: counts["quitadosPasados"]+=1
        elif d >= today and last <= stale_limit and (last <= hard_limit or any(s.get("name") in sources_today for s in xd.get("sources",[]))):
            counts["quitadosCancelados"]+=1; warn(f"quitado (no visto desde {last}): {d} {xd.get('venue')} «{str(xd.get('title'))[:60]}»")
        else:
            counts["conservadosNoVistos"]+=1; final[xid]=xd
    # salida
    for e in merged: e.pop("_titles",None)
    os.makedirs(os.path.join(out_dir,"chunks"),exist_ok=True)
    for old in glob.glob(os.path.join(out_dir,"chunks","*.json")): os.remove(old)
    allev=[dict(id=i,**d) for i,d in sorted(final.items(), key=lambda kv:(kv[1].get("date",""), tmin(kv[1].get("start")) or 9999, kv[1].get("title","")))]
    json.dump(merged,open(os.path.join(out_dir,"merged.json"),"w"),ensure_ascii=False,indent=1)
    json.dump(allev,open(os.path.join(out_dir,"events.json"),"w"),ensure_ascii=False,separators=(",",":"))
    chunks=[]; cur=[]; size=2
    for e in allev:
        b=len(json.dumps(e,ensure_ascii=False,separators=(",",":")).encode())+1
        if cur and size+b>CHUNK_BYTES: chunks.append(cur); cur=[]; size=2
        cur.append(e); size+=b
    if cur or not chunks: chunks.append(cur)
    writes=[]
    for i,ch in enumerate(chunks):
        name=f"chunk-{i:02d}"; p=os.path.abspath(os.path.join(out_dir,"chunks",name+".json"))
        json.dump({"i":i,"n":len(chunks),"count":len(ch),"updatedAt":now,"events":ch},open(p,"w"),ensure_ascii=False,separators=(",",":"))
        w={"op":"set","collection":"chunks","doc_id":name,"file_path":p}
        if name in old_chunks and old_chunks[name] is not None: w["if_version"]=old_chunks[name]
        writes.append(w)
    for name,v in old_chunks.items():
        if name not in {f"chunk-{i:02d}" for i in range(len(chunks))}:
            w={"op":"delete","collection":"chunks","doc_id":name}
            if v is not None: w["if_version"]=v
            writes.append(w)
    json.dump(writes,open(os.path.join(out_dir,"writes.json"),"w"),ensure_ascii=False,indent=1)
    stats={}
    for e in merged:
        for s in e["sources"]: stats[s["name"]]=stats.get(s["name"],0)+1
    if drops: warn("descartes:", json.dumps(drops,ensure_ascii=False))
    missing=[w["doc_id"] for w in writes if w["doc_id"] in old_chunks and "if_version" not in w]
    if missing: warn("AVISO: chunks existentes sin versión conocida (pon if_version a mano antes de subir):",missing)
    summary={"hoy":today,"archivos":files_read,"leidos":nread,"unicos":len(merged),"eventosTotales":len(allev),"chunks":len(chunks),"escrituras":len(writes),"existentes":len(existing),**counts,"descartes":drops,"porFuente":dict(sorted(stats.items(),key=lambda kv:-kv[1]))}
    json.dump(summary,open(os.path.join(out_dir,"summary.json"),"w"),ensure_ascii=False,indent=1)
    status={"lastUpdated":now,"eventCount":len(allev),"chunks":len(chunks),"sources":summary["porFuente"],
            "run":{"date":today,"new":counts["nuevos"],"updated":counts["actualizados"],"removed":counts["quitadosPasados"]+counts["quitadosCancelados"]+counts["quitadosDuplicados"],"unchanged":counts["sinCambios"],"files":files_read},
            "running":False,"note":"Actualización diaria"}
    json.dump(status,open(os.path.join(out_dir,"status.json"),"w"),ensure_ascii=False,indent=1)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    args=[a for a in sys.argv[1:] if not a.startswith("--")]
    today=None
    for i,a in enumerate(sys.argv):
        if a=="--today" and i+1<len(sys.argv): today=sys.argv[i+1]
        if a.startswith("--today="): today=a.split("=",1)[1]
    if len(args)<1: print(__doc__); sys.exit(1)
    main(args[0], args[1] if len(args)>1 else None, args[2] if len(args)>2 else "out", today)
