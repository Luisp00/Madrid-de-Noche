"""Filtros compartidos por los parsers de conciertos (Conciertos.club, La Ganzúa, Madrid en Vivo, esMadrid).
El prefijo "_" hace que scrape.py no lo trate como fuente."""
import re
from scrape.common import plain

# teatros/auditorios/hoteles/etc. con butaca o cena-espectáculo (SPEC.md: "Qué NO es ocio nocturno")
BAD_VENUE = re.compile(r"\bteatro\b|\bteatros\b|auditorio|ateneo de madrid|circulo de bellas artes|paraninfo|hotel|cafe de la opera|museo|iglesia|basilica|"
                       r"conde duque|centro cultural|casa de america|real academia|palacio de la prensa|fundacion|\bcine\b|catedral|monasterio|"
                       r"ayuntamiento|biblioteca|universidad|colegio|circo price|caixaforum|matadero|sala de columnas|tablao|corral de la moreria|"
                       r"capitol gran via|casa patas|cardamomo|las tablas|torres bermejas|florida park|palacio de congresos|palacio de cibeles|ifema", re.I)
GOOD_THEATRES = re.compile(r"teatro (kapital|barcelo|eslava|magno)|joy eslava", re.I)
BAD_TITLE = re.compile(r"tribut|homenaje|candlelight|karaoke|monolog|stand[- ]?up|comedia|humor|\bmagia\b|musical\b|infantil|\bclase\b|taller|workshop|"
                       r"cena[- ]espectaculo|\bdrags?\b|tablao|\bbingo\b|\bcuentos?\b|\bcircense\b|\bopera\b|zarzuela|flamenco en vivo|espectaculo flamenco|"
                       r"\bballet\b|\bgala\b lirica|navidad en familia|\bshow\b de magia", re.I)

def excluded_venue(venue):
    p = plain(venue or "")
    return bool(BAD_VENUE.search(p)) and not GOOD_THEATRES.search(p)

def excluded_title(*texts):
    return bool(BAD_TITLE.search(plain(" ".join(t for t in texts if t))))

def euro_nums(txt):
    """Números que acompañan a un € en un texto ('15 / 20 €', 'desde 12,50€'); common.plain() elimina el símbolo € y parse_price no los ve."""
    t = (txt or "").replace("\xa0", " ")
    nums = []
    for m in re.finditer(r"(\d+(?:[.,]\d{1,2})?(?:\s*(?:/|-|–|y|a)\s*\d+(?:[.,]\d{1,2})?)*)\s*(?:€|eur\b|euros?\b)", t, re.I):
        for x in re.findall(r"\d+(?:[.,]\d{1,2})?", m.group(1)):
            v = float(x.replace(",", "."))
            nums.append(int(v) if v == int(v) else v)
    return nums
