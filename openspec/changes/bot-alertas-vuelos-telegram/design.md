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

**Incógnita abierta que resuelve la fase 0:** si basta con el parámetro o si el mercado lo determina la dirección IP de salida. Si fuera lo segundo, el VPS en Francia daría precios del mercado equivocado y habría que enrutar el tráfico por Colombia.

### 6. Sondeo cada 4 horas con desplazamiento aleatorio

**Elegido:** intervalo base de 4 horas, con un desplazamiento aleatorio de hasta 20 minutos, y ejecución estrictamente secuencial.

**Alternativa:** sondear cada pocos minutos, como pedía la idea inicial.

**Motivo:** las tarifas aéreas se recargan unas pocas veces al día, no de forma continua. Sondear cada cinco minutos descartaría más del 95 % de las respuestas por idénticas, y a cambio dibujaría exactamente el patrón regular y de alto volumen que provoca bloqueos. Cuatro horas capturan prácticamente los mismos mínimos con dos órdenes de magnitud menos de tráfico. **Este razonamiento se apoya en una frecuencia de recarga que no se ha verificado documentalmente**; la fase 0 incluye contrastarlo midiendo cuántos sondeos consecutivos devuelven precio idéntico.

### 7. Dos niveles de refresco en modo flexible

**Elegido:** barrido completo de la ventana una vez al día; seguimiento cada 4 horas solo sobre los bloques más baratos del último barrido.

**Motivo:** una ventana de 27 días con bloques de 12 días son 16 combinaciones. A 4 horas por sondeo serían 96 consultas diarias por búsqueda, y con cinco búsquedas casi 500. Con dos niveles quedan 16 consultas al día del barrido más 18 del seguimiento: unas 34 por búsqueda. La información que se pierde es despreciable, porque el bloque más barato no cambia cada cuatro horas.

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
