#!/usr/bin/env python3
"""Ejecuta todos los parsers de scrape/sources/ y deja un JSON por fuente en data/.
Uso: python3 scrape.py [--out run/data] [--today YYYY-MM-DD] [--days 14] [--only fulltechno,applinkers] [--timeout 600]
Salida: data/<fuente>.json (array de eventos), data/_scrape_report.json con contadores y la lista `failed`
(fuentes con error o con menos eventos que su MIN_EVENTS) para que la sesión lance agentes de respaldo solo para ellas.
"""
import sys, os, json, time, importlib, pkgutil, datetime, traceback, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape import common

def madrid_today():
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        local = now.astimezone(ZoneInfo("Europe/Madrid"))
    except Exception:
        local = now.astimezone(datetime.timezone(datetime.timedelta(hours=1)))
    return (local - datetime.timedelta(hours=6)).strftime("%Y-%m-%d")

def main():
    args = sys.argv[1:]
    opt = lambda k, d: args[args.index(k) + 1] if k in args else d
    out_dir = opt("--out", "run/data"); today = opt("--today", madrid_today()); days = int(opt("--days", "14"))
    only = opt("--only", None); timeout = int(opt("--timeout", "600"))
    end = (datetime.date.fromisoformat(today) + datetime.timedelta(days=days)).isoformat()
    os.makedirs(out_dir, exist_ok=True)
    import scrape.sources as pkg
    names = [m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.name.startswith("_")]
    if only: names = [n for n in names if n in only.split(",")]
    report = {"today": today, "end": end, "sources": {}, "failed": []}
    def run(name):
        t0 = time.time()
        mod = importlib.import_module(f"scrape.sources.{name}")
        evs = mod.scrape(today, end)
        ok, bad = common.validate(evs, today, end)
        return mod, ok, bad, time.time() - t0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(run, n): n for n in names}
        for f in cf.as_completed(futs, timeout=timeout + 60):
            n = futs[f]
            try:
                mod, ok, bad, dt = f.result(timeout=timeout)
                json.dump(ok, open(os.path.join(out_dir, f"{n}.json"), "w"), ensure_ascii=False, indent=0)
                entry = {"source": getattr(mod, "NAME", n), "events": len(ok), "min": getattr(mod, "MIN_EVENTS", 1), "dropped": bad, "seconds": round(dt)}
                if len(ok) < getattr(mod, "MIN_EVENTS", 1):
                    entry["error"] = f"solo {len(ok)} eventos (mínimo {getattr(mod, 'MIN_EVENTS', 1)})"; report["failed"].append(n)
                report["sources"][n] = entry
                common.log(f"{n}: {len(ok)} eventos en {dt:.0f}s" + (f" — {entry['error']}" if "error" in entry else ""))
            except Exception as e:
                report["sources"][n] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}; report["failed"].append(n)
                common.log(f"{n}: ERROR {e}"); traceback.print_exc()
    json.dump(report, open(os.path.join(out_dir, "_scrape_report.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: (v.get("events"), v.get("error")) for k, v in report["sources"].items()}, ensure_ascii=False))
    print("failed:", report["failed"])

if __name__ == "__main__":
    main()
