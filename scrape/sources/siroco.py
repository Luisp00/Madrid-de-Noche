"""Siroco (siroco.es): feed Events Manager /events.ics (título, descripción, categoría, URL) + ficha de cada evento (hora real, precios, enlace de compra)."""
from scrape.sources._eventsmanager import scrape_ics

NAME = "Siroco"
MIN_EVENTS = 10
VENUE = "Siroco"
ADDRESS = "C/ San Dimas 3, 28015 Madrid"
ZONE = "Malasaña / Chueca"       # excepción de SPEC.md: el CP es 28015 pero va en Malasaña
ICS = "https://siroco.es/events.ics"

def scrape(today, end):
    return scrape_ics(name=NAME, ics_url=ICS, venue=VENUE, address=ADDRESS, zone=ZONE, today=today, end=end,
                      club_music=["electronica"], concert_music=[], club_planta=True)
