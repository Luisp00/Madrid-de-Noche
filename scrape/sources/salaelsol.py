"""Sala El Sol (salaelsol.com): feed Events Manager /events.ics + ficha de cada evento (hora, precios, enlace de compra).
Conciertos a partir de las 20:00 y sesiones de club de madrugada (Mazo Club, Ochoymedio Club, Elements Cave…)."""
from scrape.sources._eventsmanager import scrape_ics

NAME = "Sala El Sol"
MIN_EVENTS = 6
VENUE = "Sala El Sol"
ADDRESS = "C/ Jardines 3, 28013 Madrid"
ZONE = "Centro / Sol"
ICS = "https://salaelsol.com/events.ics"

def scrape(today, end):
    return scrape_ics(name=NAME, ics_url=ICS, venue=VENUE, address=ADDRESS, zone=ZONE, today=today, end=end,
                      club_music=["indie", "rock"], concert_music=["indie", "rock"])
