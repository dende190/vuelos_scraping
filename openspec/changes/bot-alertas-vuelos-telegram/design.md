# Diseño técnico

## Context

Repositorio nuevo: no hay código previo, solo el andamiaje de OpenSpec. No hay restricciones heredadas de stack.

Restricciones que sí condicionan el diseño, todas acordadas con el usuario:

| Restricción | Consecuencia |
|---|---|
| Presupuesto de datos: 0 € | No hay API comercial de vuelos. Solo fuentes gratuitas o no oficiales |
| Aerolíneas de bajo coste imprescindibles | Descarta Amadeus, que es la única con nivel gratuito serio |
| El usuario compra siempre en Colombia | Todas las consultas van con punto de venta Colombia, fijo |
| Rutas fuera de Europa | Las fuentes específicas de Ryanair, Wizz y similares no aportan nada |
| Despliegue en VPS propio (OVH) | Proceso permanente disponible; IP de centro de datos |
| Uso personal más unas pocas personas de confianza | Sin registro público, sin control de abuso, volumen bajo |

Ver `proposal.md` para la motivación y el alcance.

## Goals / Non-Goals

**Goals**

- Que el sistema pueda funcionar meses sin intervención y, cuando se rompa, lo diga.
- Que ninguna comparación de precios mezcle magnitudes distintas.
- Que el volumen de consultas sea lo bastante bajo como para no necesitar proxies ni evasión.
- Que cambiar de fuente de precios sea sustituir un adaptador, no reescribir el sistema.

**Non-Goals de diseño**

- Alta disponibilidad, redundancia o recuperación automática ante caída del VPS.
- Concurrencia: el sistema ejecuta una consulta cada vez, a propósito.
- Escalado horizontal o multi-instancia. Un proceso, una base de datos, un fichero.
- **Calendario de precios (aplazado a una segunda fase, decidido el 18-sep-2026).** La fase 1 descubrió que Kiwi expone `returnItineraryPricesCalendar`, `itineraryPriceGraph` e `itineraryPriceTable`, que harían viable el calendario verde/amarillo/rojo por muy poco coste de consultas. Se deja fuera a propósito: el coste real no está en obtener los datos sino en decidir cómo se presenta un calendario dentro de Telegram, y eso abre más preguntas de las que resuelve en un MVP. Queda anotado aquí para no volver a investigarlo.

## Decisions

### 1. Telegram como única interfaz

**Elegido:** bot de Telegram, sin web.

**Alternativas:** aplicación web con notificaciones push del navegador.

**Motivo:** la web obligaba a resolver autenticación, alojamiento del front, service worker y claves VAPID, y aun así en iOS las notificaciones push solo llegan si la página se instala como aplicación en la pantalla de inicio. Telegram aporta identidad, entrega fiable en móvil y escritorio, y controles interactivos, sin coste ni interfaz que mantener. El precio es perder el calendario visual de precios, que el usuario ha dejado explícitamente fuera del alcance.

### 2. Python, un solo proceso, SQLite

**Elegido:** Python con `python-telegram-bot` (asíncrono), APScheduler para la programación y SQLite para la persistencia. Todo en un proceso gestionado por systemd.

**Alternativas:** Node con BullMQ y Redis; Celery con Redis; Postgres en lugar de SQLite.

**Motivo:** el volumen objetivo son decenas de consultas al día y menos de diez búsquedas activas. Redis y Postgres añadirían dos servicios que operar a cambio de capacidad que no se va a usar. SQLite en modo WAL cubre de sobra esta carga y reduce la copia de seguridad a copiar un fichero. Si algún día hace falta Postgres, la migración es mecánica; al revés no.

### 3. Dos fuentes tras una interfaz común

**Elegido:** un contrato único de proveedor con dos implementaciones: Google Flights mediante `fast-flights`, y Kiwi mediante su GraphQL público.

**Alternativas evaluadas y descartadas:**

| Fuente | Motivo del descarte |
|---|---|
| Amadeus Self-Service | Nivel gratuito, pero cobertura pobre de bajo coste |
| SerpApi | Cubre todo, incluida la semántica de precios de Google, pero cuesta unos 50-75 USD/mes |
| Kiwi Tequila (oficial) | Requiere aprobación como socio; no depende de nosotros |
| Automatización de navegador | Lenta, pesada y mucho más detectable que reconstruir la petición |

**Motivo de la combinación:** no es cobertura, es resiliencia. `fast-flights` reconstruye la petición de Google Flights sin navegador y expone todos los filtros que el usuario pidió (escalas, duración de escala, aerolíneas, franjas horarias, equipaje), pero acumula incidencias abiertas de marzo y mayo de 2026 por fallos de autenticación y de análisis de la respuesta. Una sola fuente convierte cualquier cambio en Google en un silencio indistinguible de "no hay ofertas". Kiwi, al ser GraphQL y no análisis de HTML, se rompe por motivos distintos, y además aporta itinerarios con conexión autogestionada que Google no muestra.

### 4. Una serie de precios por búsqueda y por fuente

**Elegido:** las series nunca se fusionan. El umbral de alerta se evalúa siempre contra el último precio notificado de la misma serie.

**Alternativa:** normalizar todos los precios a un "precio total comparable" y mantener una sola serie por búsqueda.

**Motivo:** los precios de Kiwi pueden corresponder a billetes separados o no incluir equipaje facturado. Fusionarlos con los de Google produciría una bajada aparente el primer día que no corresponde a ninguna mejora real. La normalización exigiría conocer con certeza la composición de cada precio, que es justo lo que las fuentes no garantizan. Separar series cuesta una columna y elimina la clase entera de falsos positivos.

### 5. Punto de venta explícito y constante

**Elegido:** todas las consultas declaran punto de venta Colombia y moneda de referencia fija. Una fuente que no permita fijarlo no se usa para registrar precios.

**Motivo:** está verificado que Google Flights acepta parámetros de país, idioma y moneda, y que las tarifas dependen del mercado. También está verificado que `fast-flights` no documenta esos parámetros. Si la librería consulta por omisión un mercado distinto, el sistema vigilaría precios plausibles pero que el usuario no puede pagar, sin ningún síntoma visible. Es el fallo más caro del diseño y por eso se trata como requisito duro y se verifica antes de escribir nada más.

**Resuelto en la fase 1:** el parámetro `gl` sí lo lee Google, pero `fast-flights` no lo envía. La solución es reutilizar su codificador y construir la petición con `gl` añadido. Ver "Resultados de la fase 1".

### 6. Sondeo cada 4 horas con desplazamiento aleatorio

**Elegido:** intervalo base de 4 horas, con un desplazamiento aleatorio de hasta 20 minutos, y ejecución estrictamente secuencial.

**Alternativa:** sondear cada pocos minutos, como pedía la idea inicial.

**Motivo:** las tarifas aéreas se recargan unas pocas veces al día, no de forma continua. Sondear cada cinco minutos descartaría más del 95 % de las respuestas por idénticas, y a cambio dibujaría exactamente el patrón regular y de alto volumen que provoca bloqueos. Cuatro horas capturan prácticamente los mismos mínimos con dos órdenes de magnitud menos de tráfico. **Este razonamiento se apoya en una frecuencia de recarga que no se ha verificado documentalmente**; la fase 0 incluye contrastarlo midiendo cuántos sondeos consecutivos devuelven precio idéntico.

### 7. La ventana flexible la resuelve cada proveedor a su manera

**Elegido:** el contrato de proveedor expone una operación de búsqueda en ventana flexible que recibe la ventana y la duración en noches. Cada adaptador la resuelve con lo que su fuente ofrece:

| Proveedor | Cómo la resuelve | Consultas por barrido |
|---|---|---|
| Kiwi | De forma nativa: `outboundDepartureDate` como rango más `nightsCount` como rango de noches | **1** |
| Google Flights | Barrido: una consulta por cada bloque posible, más seguimiento posterior de los más baratos | **N** (16 en el ejemplo) |

Para el adaptador de Google se mantienen los dos niveles: barrido completo una vez al día y seguimiento cada 4 horas solo sobre los bloques más baratos del último barrido. Para Kiwi los dos niveles no aplican, porque el barrido cuesta una sola consulta y puede hacerse en cada sondeo.

**Motivo:** verificado en la fase 1 que el esquema de Kiwi acepta la ventana y las noches como rangos. Una ventana de 27 días con bloques de 12 días son 16 combinaciones: con Google, sondear las 16 cada 4 horas serían 96 consultas diarias por búsqueda, y los dos niveles lo dejan en unas 34. Con Kiwi son 6 al día sin perder nada.

**Alternativa descartada:** imponer el barrido por bloques a las dos fuentes por uniformidad. Habría desperdiciado la capacidad nativa de Kiwi y multiplicado por 16 sus consultas a cambio de nada. La asimetría se queda dentro del adaptador y no se filtra al resto del sistema.

### 8. Confirmación con botones en lugar de interpretación automática

**Elegido:** el sistema interpreta el texto de forma determinista, muestra su interpretación y espera confirmación.

**Alternativa:** procesamiento de lenguaje natural para resolver la ambigüedad sin preguntar.

**Motivo:** el formato de alta tiene tres ambigüedades irreducibles: el año cuando no se escribe, la ciudad frente al aeropuerto, y si un par de fechas es ida y vuelta o una ventana a explorar. Ninguna se resuelve mejor adivinando que preguntando. La confirmación cuesta una pantalla y elimina la clase entera de errores de interpretación, además de enseñar el formato correcto por repetición.

### 9. Modelo de datos

```
  +-------------------+        +--------------------------+
  |  busquedas        |        |  precios                 |
  +-------------------+        +--------------------------+
  | id                |<-------| busqueda_id              |
  | chat_id           |   1:N  | fuente                   |
  | origen, destino   |        | salida, regreso          |
  | modo (A|B)        |        | precio, moneda           |
  | salida, regreso   |        | precio_ref (moneda base) |
  | ventana_ini/fin   |        | etiquetas                |
  | duracion_dias     |        | enlace                   |
  | filtros           |        | obtenido_en              |
  | estado            |        +--------------------------+
  | pausada_hasta     |
  | creada_en         |        +--------------------------+
  +-------------------+        |  notificaciones          |
           |                   +--------------------------+
           +------------------>| busqueda_id, fuente      |
                          1:N  | precio_notificado        |
                               | enviada_en               |
                               +--------------------------+

                               +--------------------------+
                               |  estado_fuentes          |
                               +--------------------------+
                               | fuente, operativa        |
                               | ultimo_ok, ultimo_fallo  |
                               +--------------------------+
```

`notificaciones` existe por separado a propósito: el umbral se evalúa contra **el último precio notificado**, no contra el último precio registrado. Sin esa distinción, una bajada lenta y sostenida generaría un aviso en cada sondeo.

`precio_ref` guarda el importe convertido a la moneda de comparación junto al original, para que una variación del tipo de cambio nunca se confunda con una bajada de tarifa.

## Resultados de la fase 1 (verificación de fuentes)

Medido el 18 de septiembre de 2026 desde una IP de Bogotá (ETB, AS19429), sobre la ruta BOG-RDU con salida el 20-nov-2026 y regreso el 04-dic-2026.

### Google Flights a través de `fast-flights`

**Funciona.** Versión 3.1.0. A fechas de uno a dos meses vista devuelve entre cinco y seis itinerarios con precio, aerolínea, segmentos, horarios y duración. Aparecen Avianca, COPA, LATAM, American, Delta, United y Frontier, es decir, las compañías relevantes para rutas Colombia-Estados Unidos. Las incidencias abiertas del repositorio no impidieron ninguna consulta.

**Lo que se confirmó del mercado:**

| Comprobación | Resultado |
|---|---|
| ¿`fast-flights` envía el país (`gl`)? | **No.** Construye la petición solo con `tfs`, `hl` y `curr` |
| ¿Google lee `gl` si se le añade? | **Sí.** Con moneda libre, sin `gl` responde en COP y con `gl=US` responde en USD |
| ¿Es reutilizable el codificador? | **Sí.** `Query.params()` da el `tfs` ya codificado y `fast_flights.parser.parse` es público, así que basta con añadir `gl` y hacer la petición |
| ¿Cambia la tarifa entre mercados? | **No en esta ruta.** Emparejando itinerarios por aerolínea y hora de salida, el cociente COP/USD es constante en 3.159: es el mismo precio convertido |

**Consecuencia para el diseño:** el adaptador no puede usar `get_flights` tal cual; debe componer la petición con `gl` explícito. El `impersonate="chrome_145"` que aplica la librería conviene conservarlo.

**Lo que esto no demuestra:** que el mercado nunca afecte al precio. Es una ruta, un día y un par de fechas. La conclusión sólida es que el mecanismo para fijar el mercado existe y funciona, no que dé igual usarlo.

**Incógnita que solo se resuelve en el VPS:** si `gl=CO` desde una IP francesa devuelve de verdad el mercado colombiano, o si Google prioriza la IP. No es comprobable desde Colombia. La tarea 11.2 lo contrasta contra el navegador una vez desplegado.

### Kiwi a través de su GraphQL público

**Funciona sin credenciales.** El extremo `https://api.skypicker.com/umbrella/v2/graphql` responde con HTTP 200 sin cabecera de autenticación, sin clave y sin proxy. La introspección del esquema está habilitada, así que el contrato es consultable en cualquier momento.

**Presencia de campos.** Sobre 24 itinerarios de tres rutas distintas (BOG-RDU, BOG-MAD, MDE-MIA), estos campos vinieron en el 100 % de los resultados:

| Campo | Para qué sirve |
|---|---|
| `price { amount currency { code } }` | Precio y moneda |
| `bagsInfo.includedCheckedBags` y `hasNoCheckedBaggage` | Equipaje facturado incluido |
| `travelHack.isVirtualInterlining` | **Marca el billete separado / conexión autogestionada** |
| `travelHack.isTrueHiddenCity` y `isThrowawayTicket` | Otras prácticas de riesgo, a excluir |
| `bookingOptions.edges[].node.bookingUrl` | Enlace de reserva directo |

Es decir, todo lo que `proveedores-precios` exige etiquetar se puede leer de la respuesta, al contrario que en Google Flights.

**Mercado y moneda:** `options` acepta `market`, `currency` y `locale`. Con `market: "co"` y `currency: "usd"` la respuesta llegó en dólares. Cumple el requisito de punto de venta fijo de forma explícita y sin rodeos.

**Filtros:** `ItinerariesFilterInput` cubre todos los que pidió el usuario: `maxStopsCount`, `stopoverTime`, `showNoCheckedBags`, `carriers` y `excludeCarriers`, y rangos horarios en `outbound` e `inbound`. Además `enableSelfTransfer`, `enableThrowAwayTicketing` y `enableTrueHiddenCity` permiten excluir en origen los itinerarios que no queremos comparar.

**Dos capacidades del esquema que el diseño no contemplaba:**

1. `ItineraryReturnInput` acepta `outboundDepartureDate` como **rango** y `nightsCount` como **rango de noches**. Es decir, el modo de ventana flexible es nativo: una sola consulta cubre lo que el diseño resolvía con dieciséis.
2. Existen `returnItineraryPricesCalendar`, `itineraryPriceGraph` e `itineraryPriceTable`, que devuelven precios por fecha: justo el calendario que se había dejado fuera del alcance por considerarlo caro.

Ambas cosas afectan a la decisión 7 y al alcance del MVP. Pendiente de decisión del usuario antes de reescribirlas.

**Comparación con Google en la misma ruta y fechas** (BOG-RDU, 20-nov a 04-dic, en dólares): Google devolvió un mínimo de 631 y Kiwi de 818. Los itinerarios baratos de Kiwi en esta ruta salían con `isVirtualInterlining` verdadero, es decir, billetes separados. Confirma lo previsto: en rutas de Latinoamérica, Kiwi aporta resiliencia y detección de billetes separados, no mejor precio.

### Dependencia no declarada

`fast-flights` 3.1.0 importa `typing_extensions` sin declararlo. Con Python 3.14 el paquete no arranca hasta instalarlo aparte. Hay que fijarlo de forma explícita.

### Límites de los datos que devuelve

| Dato | Disponible |
|---|---|
| Precio, moneda, aerolínea, segmentos, horarios, duración, escalas | Sí |
| Emisiones de carbono | Sí |
| Enlace de reserva | **No.** Hay que construirlo con `Query.url()`, que apunta a la búsqueda en Google Flights |
| Equipaje incluido en el resultado | **No.** Solo se puede filtrar en la petición, no leer en la respuesta |
| Listado completo de vuelos | **No.** Devuelve la selección de Google, no todas las opciones |

Que no venga el equipaje en la respuesta afecta al etiquetado exigido en `proveedores-precios`: para esta fuente, la ausencia de equipaje facturado no se puede afirmar leyendo el resultado, solo forzarse filtrando en la petición.

## Risks / Trade-offs

- **`fast-flights` deja de funcionar por un cambio en Google** → Dos fuentes independientes y consulta de control periódica; el sistema avisa de la caída en lugar de callar. Plan B: operar solo con Kiwi.
- **El punto de venta real no es el configurado** → Requisito duro en las specs y verificación en la fase 0, antes de escribir el resto. Si el mercado lo fija la IP, se enruta el tráfico o se abandona esa fuente.
- **La IP de OVH recibe peor trato que una residencial** → Medir antes de mitigar. Si aparecen bloqueos: reducir huella (agente de usuario realista, nada en paralelo, respetar los límites), después túnel a una máquina doméstica, y en último término prescindir de Google.
- **El acceso automatizado a Google Flights va contra sus condiciones de servicio** → Asumido de forma consciente: uso personal, volumen de decenas de consultas al día, sin redistribución de datos. Es una decisión del usuario, documentada aquí para que no se pierda.
- **Kiwi devuelve precios que no son directamente comparables** → Series separadas, etiquetado obligatorio y filtros duros aplicados antes de registrar el precio.
- **Alertas sobre precios ya caducados** → Ningún mensaje presenta el precio como garantizado: todos llevan antigüedad del dato y enlace de verificación.
- **El VPS se cae y nadie se entera** → El resumen diario cumple también de señal de vida: si un día no llega, algo pasa.
- **SQLite se corrompe o se pierde** → Copia diaria del fichero. El histórico de precios es el activo del sistema y no se puede reconstruir.

## Migration Plan

No hay migración: el sistema no existe todavía.

**Despliegue:** unidad de systemd con reinicio automático, fichero SQLite en disco persistente, secretos (credencial del bot, identificadores de chat autorizados) en variables de entorno fuera del control de versiones.

**Puesta en marcha por fases:** primero la fase 0 de verificación de fuentes; después una única búsqueda real en modo de fechas exactas durante varios días, comprobando que el resumen diario llega y que la consulta de control no se dispara; solo entonces el modo flexible y el resto de búsquedas.

**Vuelta atrás:** detener el servicio. No hay estado externo que revertir. El fichero SQLite se conserva.

## Open Questions

Ninguna de estas afecta a las specs ni al reparto de tareas; se afinan con datos de uso:

- Número de sondeos consecutivos sin resultado antes de marcar una búsqueda como fallida. Punto de partida: 3.
- Cuántos bloques del barrido completo pasan al seguimiento frecuente. Punto de partida: 3.
- Qué fuente de tipos de cambio usar, en caso de que alguna fuente no permita fijar la moneda de referencia.
- Si el resumen diario debe agrupar todas las búsquedas en un mensaje o enviar uno por búsqueda cuando haya muchas.
