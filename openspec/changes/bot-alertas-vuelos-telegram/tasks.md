# Plan de implementación

> **La fase 1 es una puerta.** Si alguna de sus tareas falla, hay que parar y revisar
> `proposal.md` y `design.md` antes de seguir: varias decisiones del diseño dependen
> de que estas comprobaciones salgan bien.

## 1. Verificación de viabilidad de las fuentes (puerta)

- [x] 1.1 Instalar `fast-flights` y ejecutar una consulta real BOG->RDU con fechas futuras; verificar que devuelve itinerarios con precio y no una respuesta vacía ni error 401
- [x] 1.2 Leer el código fuente de `fast-flights` y determinar si permite fijar país (`gl`), idioma (`hl`) y moneda (`curr`); dejar por escrito en `design.md` qué mercado usa por omisión y cómo se fija el de Colombia
- [x] 1.3 Si 1.2 muestra que no es configurable, comprobar si el codificador de la petición es reutilizable para construir la URL a mano con los parámetros de mercado; verificar comparando el precio obtenido con el que muestra Google Flights en el navegador desde Colombia
- [x] 1.4 Determinar si el mercado lo fija el parámetro o la IP de salida: lanzar la misma consulta con país Colombia y país Estados Unidos, moneda fija en ambas, desde la misma IP; verificar si los precios difieren y anotar el resultado en `design.md`
- [x] 1.5 Lanzar una consulta real al GraphQL público de Kiwi sin credenciales; verificar que responde y guardar una respuesta completa de ejemplo como fichero de referencia
- [x] 1.6 Sobre la respuesta de 1.5, documentar qué campos vienen siempre y cuáles no: precio, moneda, escalas, aerolíneas, equipaje facturado, billetes separados y enlace de reserva; verificar contra al menos tres rutas distintas
- [x] 1.7 Comprobar si Kiwi admite fijar mercado y moneda; anotar el resultado en `design.md`
- [x] 1.8 Ejecutar la misma consulta contra ambas fuentes 6 veces separadas 30 minutos; verificar cuántas devuelven precio idéntico, para contrastar el supuesto de que las tarifas se recargan pocas veces al día

## 2. Andamiaje del proyecto

- [x] 2.1 Crear la estructura del proyecto Python con gestión de dependencias y fichero de configuración por variables de entorno; verificar que el proyecto arranca y lee la configuración sin secretos en el código
- [x] 2.1b Fijar `typing_extensions` como dependencia explícita, que `fast-flights` 3.1.0 importa sin declarar; verificar que una instalación limpia arranca sin `ModuleNotFoundError`
- [x] 2.2 Configurar el registro de eventos con niveles y salida a fichero rotado; verificar que un arranque deja traza legible
- [x] 2.3 Configurar el arranque de pruebas automáticas; verificar que la orden de pruebas se ejecuta en un proyecto vacío

## 3. Persistencia

- [x] 3.1 Crear el esquema SQLite con las tablas `busquedas`, `precios`, `notificaciones` y `estado_fuentes` según el modelo de `design.md`; verificar que las migraciones se aplican sobre una base vacía
- [x] 3.2 Activar el modo WAL y crear los índices por búsqueda, fuente e instante de obtención; verificar con una consulta de plan de ejecución que las lecturas de serie usan índice
- [x] 3.3 Implementar el acceso a datos de búsquedas y precios; verificar con pruebas unitarias de alta, consulta y cambio de estado
- [x] 3.4 Implementar la copia de seguridad diaria del fichero SQLite; verificar que la copia se genera y que puede abrirse

## 4. Capa de proveedores de precios

- [x] 4.1 Definir el contrato común de proveedor con el resultado normalizado: precio, moneda, fuente, instante, enlace, etiquetas, escalas, aerolíneas y equipaje; verificar con una implementación simulada usada en pruebas
- [x] 4.2 Implementar el adaptador de Google Flights componiendo la petición a mano (reutilizando el codificador de `fast-flights` y su `parser.parse`, ya que la librería no envía `gl`), con punto de venta y moneda fijos; verificar que toda consulta emitida lleva `gl` y `curr` configurados
- [x] 4.3 Implementar el adaptador de Kiwi sobre `returnItineraries`, con `market`, `currency` y `locale` fijos y excluyendo `enableThrowAwayTicketing` y `enableTrueHiddenCity`; verificar que `bagsInfo`, `travelHack` y `bookingUrl` se mapean al resultado normalizado
- [x] 4.4 Implementar el etiquetado de resultados: billetes separados, conexión autogestionada, sin equipaje facturado y sin enlace de verificación; verificar con pruebas sobre respuestas de ejemplo guardadas
- [x] 4.5 Implementar el rechazo de resultados obtenidos bajo un mercado distinto del configurado; verificar con una prueba que un resultado así no llega a registrarse
- [x] 4.6 Implementar reintentos con esperas crecientes ante límite de peticiones y errores transitorios; verificar con pruebas que simulan respuestas de exceso de peticiones
- [x] 4.7 Implementar la conversión a la moneda de referencia conservando importe original y cambio aplicado; verificar con pruebas que ambos valores quedan registrados
- [ ] 4.8 Implementar la búsqueda en ventana flexible en ambos adaptadores: nativa en Kiwi (`outboundDepartureDate` como rango más `nightsCount`) y por barrido de bloques en Google; verificar que ambos devuelven resultados etiquetados con su bloque de fechas
- [x] 4.9 Construir el enlace de verificación de los resultados de Google a partir de la URL de la consulta, dado que la fuente no devuelve enlace de reserva; verificar que el enlace abre la búsqueda equivalente en Google Flights

## 5. Modelo de búsquedas y ciclo de vida

- [ ] 5.1 Implementar el modelo de búsqueda con los dos modos de fechas y los filtros; verificar con pruebas de creación en ambos modos
- [ ] 5.2 Implementar el cálculo de bloques de una ventana flexible, usado por los adaptadores que deban consultar bloque a bloque; verificar con una prueba que una ventana de 27 días con bloques de 12 produce exactamente 16 combinaciones
- [ ] 5.3 Implementar la máquina de estados con las transiciones entre activa, pausada, terminada, vencida y fallida; verificar con pruebas que las transiciones no permitidas se rechazan
- [ ] 5.4 Implementar el vencimiento automático por fecha en ambos modos; verificar con pruebas de reloj simulado
- [ ] 5.5 Implementar el contador de sondeos fallidos consecutivos y el paso a estado fallida, con reinicio al recuperarse; verificar con pruebas
- [ ] 5.6 Implementar la aplicación de filtros duros antes de registrar un precio; verificar con una prueba de que un resultado sin equipaje no entra en el histórico de una búsqueda que lo exige
- [ ] 5.7 Implementar el borrado explícito de búsqueda con su histórico, separado de la terminación; verificar que terminar conserva los precios y que borrar los elimina

## 6. Interfaz de Telegram

- [ ] 6.1 Conectar el bot y responder a un mensaje de prueba; verificar la recepción desde una cuenta real
- [ ] 6.2 Restringir el uso a los identificadores de chat autorizados; verificar que un chat no autorizado recibe una negativa y no crea nada
- [ ] 6.3 Implementar el analizador del formato de alta en modo de fechas exactas; verificar con pruebas sobre una batería de mensajes válidos e inválidos
- [ ] 6.4 Implementar el analizador del modo de ventana flexible con duración; verificar que rechaza una duración mayor que la ventana indicando la máxima admitida
- [ ] 6.5 Implementar la resolución de fechas sin año a la próxima ocurrencia futura; verificar con pruebas de reloj simulado alrededor del cambio de año
- [ ] 6.6 Incorporar el catálogo de aeropuertos y la resolución de nombre de ciudad a código; verificar que una ciudad con varios aeropuertos pide elegir y que un lugar desconocido produce un mensaje de error concreto
- [ ] 6.7 Implementar el analizador de filtros opcionales en la misma línea; verificar que un término no reconocido se señala individualmente sin crear la búsqueda
- [ ] 6.8 Implementar el mensaje de confirmación con botones de confirmar, cancelar y pasar a fechas flexibles; verificar que una búsqueda sin confirmar no genera consultas ni consume cupo
- [ ] 6.9 Implementar el comando de listado con precio actual, mínimo histórico y botones por búsqueda; verificar el caso sin búsquedas
- [ ] 6.10 Implementar las acciones de detener y pausar desde los botones; verificar que la pausa reactiva automáticamente al vencer el plazo
- [ ] 6.11 Implementar el límite de búsquedas activas por usuario; verificar que al superarlo se rechaza el alta y se ofrece listar las activas
- [ ] 6.12 Implementar la respuesta de ayuda ante entrada no reconocida con un ejemplo de cada modo; verificar con un mensaje arbitrario

## 7. Monitoreo y programación

- [ ] 7.1 Implementar el planificador de sondeos con intervalo base y desplazamiento aleatorio; verificar registrando 20 ejecuciones y comprobando que ninguna cae en hora exacta ni a intervalo constante
- [ ] 7.2 Garantizar la ejecución secuencial de las consultas; verificar con una prueba de que dos sondeos coincidentes no se solapan
- [ ] 7.3 Implementar el registro de precios en la serie de cada par de búsqueda y fuente; verificar que el primer precio de una fuente nueva no se compara con el mínimo de otra
- [ ] 7.4 Implementar la programación de la ventana flexible según lo que admita cada fuente: consulta única por sondeo cuando la fuente resuelve la ventana entera, y barrido diario más seguimiento de los bloques más baratos cuando no; verificar contando las consultas emitidas por cada adaptador en un sondeo
- [ ] 7.5 Implementar la omisión de búsquedas no activas; verificar que una búsqueda pausada no genera consultas ni se contabiliza como fallo
- [ ] 7.6 Registrar el recuento diario de consultas por fuente; verificar que el dato queda accesible para vigilar el volumen real

## 8. Alertas

- [ ] 8.1 Implementar la evaluación del umbral relativo contra el último precio notificado de la misma serie; verificar con pruebas de bajada por encima y por debajo del umbral
- [ ] 8.2 Implementar la notificación del precio de referencia inicial al activar una búsqueda; verificar que en modo flexible incluye el bloque más barato encontrado
- [ ] 8.3 Implementar el formato de alerta con todos los elementos mínimos y el botón de detener la búsqueda; verificar visualmente en Telegram
- [ ] 8.4 Implementar que las subidas de precio no generan alerta inmediata; verificar con una prueba de que solo aparecen en el resumen
- [ ] 8.5 Implementar el resumen diario a la hora configurada, incluido el caso sin cambios; verificar que no se envía cuando no hay búsquedas activas
- [ ] 8.6 Implementar los avisos de cierre de búsqueda por vencimiento y por fallo, con el mínimo histórico alcanzado; verificar que el mensaje de fallo distingue el fallo de la ausencia de vuelos
- [ ] 8.7 Verificar que ningún mensaje con precio omite la antigüedad del dato ni el aviso de verificación, recorriendo todas las plantillas

## 9. Salud de las fuentes

- [ ] 9.1 Implementar la consulta de control periódica por fuente con ruta y fechas estables; verificar que se ejecuta de forma independiente de las búsquedas del usuario
- [ ] 9.2 Implementar el cambio de estado de una fuente a caída y a restablecida, con aviso al usuario en ambos sentidos; verificar forzando un fallo simulado
- [ ] 9.3 Implementar el aviso destacado cuando todas las fuentes están caídas; verificar con ambas fuentes simuladas como caídas

## 10. Despliegue

- [ ] 10.1 Preparar la unidad de systemd con reinicio automático y arranque al inicio; verificar que el servicio sobrevive a un reinicio del VPS
- [ ] 10.2 Ubicar la base de datos y los registros en rutas persistentes y configurar la rotación; verificar que los datos sobreviven a un reinicio del servicio
- [ ] 10.3 Documentar en el repositorio la puesta en marcha, las variables de entorno necesarias y cómo restaurar una copia de seguridad; verificar siguiendo el documento en una instalación limpia

## 11. Validación de extremo a extremo

- [ ] 11.1 Poner en marcha una única búsqueda real en modo de fechas exactas y dejarla operando cinco días; verificar que llegan los resúmenes diarios y que la consulta de control no se dispara
- [ ] 11.2 Comparar durante esos cinco días los precios registrados con los que muestra Google Flights en el navegador desde Colombia; verificar que coinciden dentro de un margen razonable y que el mercado es el correcto
- [ ] 11.3 Activar una búsqueda en modo flexible y verificar que la recomendación de bloque más barato es coherente con lo que muestra Google Flights
- [ ] 11.4 Contrastar en el registro de recuentos que el volumen diario de consultas se mantiene en el orden previsto por el diseño
- [ ] 11.5 Probar el ciclo completo de gestión: alta, confirmación, pausa, reactivación, detención desde una alerta y vencimiento por fecha
