"""Helper: resuelve un nombre de sala libre ("Sala BUT", "SALA CHANGÓ") contra el directorio scrape/venues.json
(nombre canónico, dirección y zona). El prefijo "_" hace que scrape.py no lo trate como fuente."""
import os, re, json
from scrape.common import plain

_DIR = None
_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venues.json")
EXTRA = {"unas chung lee": ("Uñas Chung Lee", None, "Centro / Sol")}      # SPEC.md (salas conocidas), no está en el directorio

def _key(s):
    k = plain(s)
    k = re.sub(r"[^a-z0-9 ]", " ", k)
    return re.sub(r"\s+", " ", k).strip()

def _load():
    global _DIR
    if _DIR is None:
        _DIR = {}
        try: items = json.load(open(_FILE, encoding="utf-8"))
        except Exception: items = []
        for v in items:
            rec = (v["name"], v.get("address"), v.get("zone") or "Otros")
            for n in [v["name"]] + list(v.get("aliases") or []):
                _DIR.setdefault(_key(n), rec)
    return _DIR

def resolve(name):
    """(venue, address, zone) o None si la sala no está en el directorio."""
    k = _key(name)
    if not k: return None
    d = _load()
    if k in d: return d[k]
    if k in EXTRA: return EXTRA[k]
    k2 = re.sub(r"^sala ", "", k)
    for cand in (k2, "sala " + k2):
        if cand in d: return d[cand]
        if cand in EXTRA: return EXTRA[cand]
    return None
