# Revisión: Madrid de Noche (30 oct 2026)

## Lo que funciona
- **Base de datos:** las noches del 2 y 9 nov tienen 14 eventos cada una, igual que el archivo fusionado. Los archivos del artifact coinciden con los locales.
- **Tarea programada:** diaria a las 22:00 (Madrid), Opus 5.5, sin aprobaciones, con aviso push. Aún no se ha ejecutado: la primera vez es hoy.
- **App:** probada en móvil y escritorio, sin errores.
  - Funcionan filtros, favoritos y ficha del evento.
  - Lo que empieza antes de las 06:00 cuenta en la noche anterior.
  - La carga en 4 tramos de fechas no pierde ni duplica eventos.

## Errores
**App**
1. "Finde" siempre muestra 0 eventos.
2. Dentro de cada noche, lo de las 00:00 sale antes que lo de las 22:00.
3. La búsqueda distingue tildes: "reggaeton" da 5 resultados, "reggaetón" 65.
4. En móvil, el texto del precio desborda la tarjeta y la página se desplaza en horizontal.
5. Al hacer scroll, las cabeceras de día quedan ocultas.
6. Si cierras el panel de filtros tocando fuera, el filtro queda activo pero la lista no cambia.
7. "Entradas" no siempre lleva al precio más barato: falla en 95 eventos.
8. Accesibilidad: las tarjetas no se abren con teclado, el foco no entra en los paneles y algunos grises tienen poco contraste.
9. Menores:
   - "tardeo" aparece sin traducir.
   - El filtro de edad muestra lo que exige esa edad, no lo que te admite.
   - Los favoritos podrían borrarse al recargar.

**Datos**
- La auditoría halló errores en 7 de 20 eventos revisados.
- 287 eventos (28 %) enlazan a un listado general, no al evento.
- Un 33 % no tiene precio; un 75 % no dice si quedan entradas.

**Actualización diaria**
- **Lectura de la base de datos:** entera de una vez (~200 000 tokens). Si se corta, no se borran los eventos pasados y se llegaría al límite de 25 000 en unos 25 días.
- **Cancelados y duplicados:** nunca se borran.
- **"Agotado":** basta con que lo diga una fuente.
- **Espera a los agentes:** 25 min; la primera extracción tardó unos 40.
- **Escritura por lotes:** sin probar desde la tarea.
- **Duración y coste:** 60–120 min por ejecución; 25–40 M tokens de entrada (casi todos en caché) y 0,4–0,7 M de salida.

## Lo que falta
- **Fuentes con 0 eventos:** 3 de los 7 agentes nunca se han ejecutado. Nada de RA, Techno Airlines, ma.to, Shotgun, DICE, Madrid Lux, Clubbable, Discomadrid, Discoruta, Discotecas Gratis, Taquilla.com, Eventbrite, Atrápalo, Discotech ni Fourvenues directo. El estado dice "49 fuentes", pero solo 35 aportan eventos.
- **Salas sin eventos el 30–31 oct (Halloween):** Teatro Barceló, Gabana, Specka, Sala Caracol, Marula, Medias Puri, Uñas Chung Lee, Toni 2, Stardust/Sala Cool, Liberty, Villa Panthera e Istar. Opium y Oh My Club están cerradas. Fabrik y Kapital, solo 2 cada una.
- **Actualizar a demanda:** no hay botón.
- **Compartir:** pendiente.

## Próximos pasos
1. **Antes de las 22:00 de hoy** (~1 h): espera de 60 min, leer la base de datos por partes guardando solo lo necesario, y probar la escritura por lotes.
2. **Errores 1–7 de la app** (~1,5 h).
3. **Probar a mano los 3 agentes nunca ejecutados** (~1 h).
4. **Añadir las 12 salas que faltan** (~1–2 h).
5. **Mejorar la fusión** (~1 h): borrar futuros que dejen de aparecer, tomar precio y estado de la web de venta, enlaces directos.
6. **Accesibilidad** (~45 min).
7. **Compartir y botón "actualizar"** (~1 h).
