#!/usr/bin/env python3
"""Comprueba los enlaces de compra (ticketUrl y urls de sources) de un events.json y clasifica cada uno:
ok (2xx/3xx a página real), dead (404/410, dominio inexistente, redirección a portada/aviso de evento no disponible), blocked (403/429/challenge), error (timeout).
Uso: python3 tools/linkcheck.py run/out/events.json [--max 2000] [--workers 8] > run/linkcheck.json
Imprime un resumen por fuente a stderr y el detalle JSON a stdout."""
import sys, os, json, re, time, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrape import common
import requests

DEAD_TEXT = re.compile(r"(evento no encontrado|event not found|página no encontrada|page not found|no disponible|not available|ha finalizado|has ended|sold out and removed|404|este evento ya no|this event is no longer|no existe)", re.I)

def check(url):
    t0=time.time(); r=None
    try:
        s=common.session()
        r=s.get(url, timeout=20, allow_redirects=True, stream=True)
        code=r.status_code; final=r.url
        body=""
        try:
            body=r.raw.read(60000, decode_content=True).decode("utf-8","ignore")
        except Exception: pass
        r.close()
        if code in (404,410): st="dead"
        elif code in (403,429,503) or "challenge" in body.lower()[:5000]: st="blocked"
        elif code>=500: st="error"
        elif code>=400: st="dead"
        else:
            # redirigido a la portada de la ticketera = evento retirado
            from urllib.parse import urlparse
            p0=urlparse(url).path.rstrip("/"); p1=urlparse(final).path.rstrip("/")
            if p0 and len(p0)>1 and p1 in ("","/") and urlparse(final).netloc.replace("www.","")==urlparse(url).netloc.replace("www.",""): st="dead"
            elif DEAD_TEXT.search(re.sub(r"<[^>]+>"," ",body[:30000])) and ("404" in body[:3000] or re.search(r"no encontrad|not found|no disponible|not available|no longer", body[:30000], re.I)): st="dead"
            else: st="ok"
        return {"url":url,"status":st,"code":code,"final":final if final!=url else None,"ms":int((time.time()-t0)*1000)}
    except requests.exceptions.ConnectionError as ex:
        msg=str(ex)[:160]
        return {"url":url,"status":"dead" if ("NameResolution" in msg or "getaddrinfo" in msg or "Name or service" in msg) else "error","code":None,"error":msg,"ms":int((time.time()-t0)*1000)}
    except Exception as ex:
        return {"url":url,"status":"error","code":None,"error":str(ex)[:160],"ms":int((time.time()-t0)*1000)}

def main():
    args=sys.argv[1:]; path=args[0]; opt=lambda k,d: args[args.index(k)+1] if k in args else d
    maxn=int(opt("--max","2000")); workers=int(opt("--workers","8"))
    ev=json.load(open(path))
    urls={}  # url -> set of (source, kind)
    for e in ev:
        if e.get("ticketUrl"): urls.setdefault(e["ticketUrl"],set()).add(("ticket:"+(e["sources"][0]["name"] if e.get("sources") else "?")))
        for s in e.get("sources") or []: urls.setdefault(s["url"],set()).add("source:"+s["name"])
    items=list(urls.items())[:maxn]
    common.CACHE_TTL=0
    results=[]
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda it: dict(check(it[0]), tags=sorted(it[1])), items):
            results.append(res)
    # resumen por fuente
    summ={}
    for r in results:
        for t in r["tags"]:
            kind,name=t.split(":",1); d=summ.setdefault(name,{"ticket":{},"source":{}})
            d[kind][r["status"]]=d[kind].get(r["status"],0)+1
    for name,d in sorted(summ.items(), key=lambda kv: -(sum(kv[1]["ticket"].values())+sum(kv[1]["source"].values()))):
        print(f"{name:24s} ticket={d['ticket']}  source={d['source']}", file=sys.stderr)
    json.dump({"checked":len(results),"bySource":summ,"results":results}, sys.stdout, ensure_ascii=False, indent=0)

if __name__=="__main__": main()
