#!/usr/bin/env python3
"""Fusiona data/*.json en eventos únicos y genera ops para la base de datos del artifact.
Uso: python3 -I merge.py data/ existing.json out/
  existing.json: salida de db_query (una línea JSON por doc, con id/data/version) o [] si está vacía.
  out/: escribe merged.json y ops_NN.json (≤50 ops cada uno) listos para db_write.
Avisos (intercambios de precio, descartes) van a stderr; las estadísticas a stdout.
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
}

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
EXCLUDED = re.compile(r"karaoke|bingo|\bclases? de\b|\btalleres?\b|\btablao\b|\bteatro\b|sin esperas|shisha|cena[ -]espect[aá]culo|candlelight|infantil|\bmuseo\b", re.I)
MUSICAL_TITLE = re.compile(r"\bmusical\b", re.I)                     # en el título
MUSICAL_DESC = re.compile(r"\b(el|un|del|al|este) musical\b", re.I)   # en la descripción ("propuesta musical" no cuenta)
NIGHTLIFE_VENUES = {"Teatro Kapital","Teatro Barceló","Teatro Eslava","Joy Eslava","Teatro Magno","Museo Chicote"}  # su nombre no dispara la exclusión
# teatros/auditorios con butaca: fuera salvo sesiones club/after
SEATED_VENUE = re.compile(r"^(teatro|nuevo teatro|auditorio)\b|^ateneo de madrid$|^circulo de bellas artes$")

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
    return {"title":title[:140],"date":date,"start":e.get("start") or None,"end":e.get("end") or None,"venue":venue,"address":(e.get("address") or None),
            "zone":(e.get("zone") or "Otros"),"type":typ,"music":music,"priceMin":pmin,"priceMax":pmax,"priceText":(e.get("priceText") or None),
            "free":free,"dressCode":(e.get("dressCode") or None),"ageMin":num(e.get("ageMin")),"lineup":[str(x)[:80] for x in (e.get("lineup") or [])][:12],
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
            if sa and sb and sa!=sb and (sa in sb or sb in sa) and sa not in venue_names and sb not in venue_names: return True
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

def main(data_dir, existing_path, out_dir):
    today=madrid_today()
    events=[]; drops={}; nread=0
    for f in sorted(glob.glob(os.path.join(data_dir,"*.json"))):
        try: arr=json.load(open(f))
        except Exception as ex: print("ERROR leyendo",f,ex); continue
        for e in arr if isinstance(arr,list) else []:
            c=clean(e) if isinstance(e,dict) else None
            if not c: continue
            nread+=1
            r=excluded_reason(c, today)
            if r: drops[r.split(" (")[0]]=drops.get(r.split(" (")[0],0)+1; warn(f"descartado ({r}): {c['date']} {c['venue']} «{c['title'][:60]}»"); continue
            events.append(c)
    merged=dedupe(events)
    merged,ngen=drop_generic(merged)
    if ngen: drops["genérico semanal"]=ngen
    # ids y comparación con existentes
    existing={}
    if existing_path and os.path.exists(existing_path):
        txt=open(existing_path).read().strip()
        if txt.startswith("["):
            for d in json.loads(txt): existing[d["id"]]={"version":d.get("version"),"data":d.get("data",{})}
        else:
            for line in txt.splitlines():
                line=line.strip()
                if line.startswith("{"):
                    try: d=json.loads(line)
                    except: continue
                    if "id" in d: existing[d["id"]]={"version":d.get("version"),"data":d.get("data",{})}
    now=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ops=[]; seen=set()
    for e in merged:
        titles=e.get("_titles") or [e["title"]]
        if e["date"]<today: continue
        eid=make_id(e)
        if eid in seen: continue
        seen.add(eid)
        # si existe un doc previo con misma venue+date y título parecido (a cualquiera de los títulos vistos) pero distinto id, conservar su id
        if eid not in existing:
            for xid,x in existing.items():
                if xid in seen: continue
                xd=x["data"]
                if xd.get("date")==e["date"] and strip(xd.get("venue") or "")==strip(e.get("venue") or "") and max(sim(xd.get("title",""),t) for t in titles)>=0.5:
                    eid=xid; seen.add(eid); break
        doc={k:v for k,v in e.items() if v not in (None,[],"") and not k.startswith("_")}; doc["updatedAt"]=now
        if eid in existing:
            old=dict(existing[eid]["data"]); old.pop("updatedAt",None); cmp=dict(doc); cmp.pop("updatedAt",None)
            if old==cmp: continue
            ops.append({"op":"set","path":f"events/{eid}","data":doc,"ifVersion":existing[eid]["version"]})
        else:
            ops.append({"op":"set","path":f"events/{eid}","data":doc})
    # borrar eventos pasados (más de 1 día) para no acumular
    for xid,x in existing.items():
        d=x["data"].get("date","")
        if d and d < (datetime.date.fromisoformat(today)-datetime.timedelta(days=1)).isoformat():
            ops.append({"op":"delete","path":f"events/{xid}","ifVersion":x["version"]})
    for e in merged: e.pop("_titles",None)
    os.makedirs(out_dir,exist_ok=True)
    json.dump(merged,open(os.path.join(out_dir,"merged.json"),"w"),ensure_ascii=False,indent=1)
    for i in range(0,len(ops),50):
        json.dump(ops[i:i+50],open(os.path.join(out_dir,f"ops_{i//50:02d}.json"),"w"),ensure_ascii=False)
    stats={}
    for e in merged:
        for s in e["sources"]: stats[s["name"]]=stats.get(s["name"],0)+1
    if drops: warn("descartes:", json.dumps(drops,ensure_ascii=False))
    print(json.dumps({"leidos":nread,"unicos":len(merged),"ops":len(ops),"lotes":(len(ops)+49)//50,"porFuente":stats},ensure_ascii=False))

if __name__=="__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else None, sys.argv[3] if len(sys.argv)>3 else "out")
