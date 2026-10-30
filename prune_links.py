#!/usr/bin/env python3
"""Quita los enlaces de compra muertos antes de la fusión.
Uso: python3 prune_links.py run/data [--workers 10]
Para cada evento de run/data/*.json comprueba su ticketUrl (y las urls de sources) con una petición real:
  muerto = 404/410, dominio inexistente, o redirección a la portada de la misma web (evento retirado).
  403/429/406 (bloqueo a bots) NO cuenta como muerto.
Un ticketUrl muerto se sustituye por la primera url viva de sources; si no queda ninguna url viva, el evento se descarta.
Reescribe los JSON in situ y deja run/data/_links_report.json. Resultados cacheados 20 h en run/cache."""
import sys, os, json, time, hashlib, concurrent.futures as cf
from urllib.parse import urlparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape import common
import requests

SKIP_HOSTS = ("ra.co","shotgun.live","site.fourvenues.com","fourvenues.com","instagram.com","facebook.com")  # bloquean a bots: no se puede juzgar

def check(url):
    host=urlparse(url).netloc.replace("www.","")
    if any(h in host for h in SKIP_HOSTS): return "unknown"
    key="LINK "+url
    c=common._cached(key)
    if c in ("ok","dead","unknown"): return c
    st="unknown"
    try:
        r=common.session().get(url, timeout=20, allow_redirects=True, stream=True); code=r.status_code; final=r.url; r.close()
        if code in (404,410): st="dead"
        elif code<400:
            p0=urlparse(url).path.rstrip("/"); f=urlparse(final)
            if len(p0)>1 and f.path.rstrip("/") in ("",) and f.netloc.replace("www.","")==host: st="dead"   # redirigido a la portada
            else: st="ok"
        else: st="unknown"   # 403/406/429/5xx: no se puede saber
    except requests.exceptions.ConnectionError as ex:
        m=str(ex); st="dead" if ("NameResolution" in m or "getaddrinfo" in m or "Name or service" in m) else "unknown"
    except Exception: st="unknown"
    common.CACHE_TTL=72000; common._store(key, st)
    return st

def main():
    args=sys.argv[1:]; d=args[0]; workers=int(args[args.index("--workers")+1]) if "--workers" in args else 10
    files=[f for f in sorted(os.listdir(d)) if f.endswith(".json") and not f.startswith("_")]
    data={f:json.load(open(os.path.join(d,f))) for f in files}
    urls=set()
    for arr in data.values():
        for e in arr:
            if isinstance(e,dict):
                if e.get("ticketUrl"): urls.add(e["ticketUrl"])
                for s in e.get("sources") or []:
                    if s.get("url"): urls.add(s["url"])
    urls=sorted(urls); t0=time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as ex: res=dict(zip(urls, ex.map(check, urls)))
    rep={"checked":len(urls),"dead":sum(1 for v in res.values() if v=="dead"),"ok":sum(1 for v in res.values() if v=="ok"),"unknown":sum(1 for v in res.values() if v=="unknown"),"seconds":int(time.time()-t0),"replacedTicket":0,"droppedEvents":0,"deadUrls":[u for u,v in res.items() if v=="dead"][:200],"byFile":{}}
    for f,arr in data.items():
        out=[]; rep["byFile"][f]={"before":len(arr),"replaced":0,"dropped":0}
        for e in arr:
            if not isinstance(e,dict): continue
            live=[s for s in (e.get("sources") or []) if res.get(s.get("url"))!="dead"]
            if e.get("ticketUrl") and res.get(e["ticketUrl"])=="dead":
                if live: e["ticketUrl"]=live[0]["url"]; rep["replacedTicket"]+=1; rep["byFile"][f]["replaced"]+=1
                else: rep["droppedEvents"]+=1; rep["byFile"][f]["dropped"]+=1; continue
            e["sources"]=live or e.get("sources")
            out.append(e)
        json.dump(out, open(os.path.join(d,f),"w"), ensure_ascii=False, indent=0)
    json.dump(rep, open(os.path.join(d,"_links_report.json"),"w"), ensure_ascii=False, indent=1)
    print(json.dumps({k:rep[k] for k in ("checked","ok","dead","unknown","replacedTicket","droppedEvents","seconds")}))
    for u in rep["deadUrls"][:15]: print("  muerto:", u, file=sys.stderr)

if __name__=="__main__": main()
