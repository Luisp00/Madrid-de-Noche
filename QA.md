# QA merged.json (1031 events)
IDs leave out "2026-".

## 1. Structure
- Missing date/venue/title: 0/0/0. Bad times: 0. Null start: 120. pmin>pmax: 0. Outside window: 0.
- Unmerged duplicates (drop the first ID): 10-30-ea6d320afd/5a88a172fb, 11-13-b9bd2204ac/a57c332261, 11-01-4ca70d7cd9/1e29a9b08c, 10-29-7b4df27a71/01d7065e21, 10-30-e32bfa3b44/3d134a5961, 10-29-180b78e008/a532c2368a, 10-31-8a91813332/bc84a5c154, 10-31-ef4a190524/f3b4d3777f, 10-30-3f0444ad7c/67fadd4b4b.
- Wrongly merged: 11-02-903dae95de (two Fitz events).
- "Otros" with a zone-table postcode: 0, but 145 have no address. Postcode disagrees with the venue table: 21 (Fitz, Siroco).
- concierto before 20:00: 2 (11-08-72df927b81, 11-07-e5f387e4b9).
- Not nightlife: 19. 15 seated-theatre concerts (Albéniz, Rialto, Ateneo, Círculo de Bellas Artes…), karaoke 10-31-1651ded112, salsa class, Vistalegre tribute 11-06-45fd5ecf70, drag show 10-31-e9d588ef7c. Also 21 Fever "Fiesta VIP sin esperas" products, and 3 pub crawls past the 3-night limit.

## 2. Spot-check (13 OK / 7 wrong)
| Source | Result |
|---|---|
| Fever | OK: Shark, Pogo, VINTAGE, RAW |
| Fever | Wrong: Kapital 10-31 priceMax 80 (page: "desde 35"). HallowFest priceMin 33 (page: 55/70). Ella Sky Bar says agotado, page on sale. Kinyxx title |
| Applinkers | OK: Joy 11-04, Joy 10-31, Bresh |
| Applinkers | Wrong: One World start is 22:30, not 00:00 |
| Conciertos.club | OK ×4 |
| Others | OK: Siroco, El Sol. Wrong: Mondo start 23:00, Shoko start 23:45 |

Fourvenues URLs returned client_error, so I checked them through applinkers.com.

## 3. Fixes
1. Delete the duplicates, the non-nightlife events and the extra pub crawls.
2. Correct:
   - 10-31-9d7f0a25f7 status → disponible
   - 10-31-8e43bfb26c prices → 55–70
   - 10-31-73fe79ca5d priceMax → null
   - 11-02-903dae95de start → 22:30
   - 11-08-72df927b81 start → 20:00
   - 11-01-e5dbe43ef3 start → 23:00
   - 10-31-f29b60a4dc start → 23:45
3. merge.py:
   - Run a second dedupe pass (titles change mid-merge).
   - Merge on same venue+date+start, or on a shared uncommon token.
   - Block merges when starts differ by more than 60 min.
   - Drop generic weekday entries.
   - Add venue aliases (Strong, Las Ventas, Core/Boite).
   - Take price and status from the ticket source instead of max().
4. SPEC.md: exclude seated theatres, karaoke, classes and skip-the-line products. Resolve the Fitz/Siroco zones. Add the frequent venues that have no address.
