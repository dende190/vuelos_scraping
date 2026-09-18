## Purpose

Decide cuándo interrumpir al usuario y con qué información, de modo que cada aviso sea accionable y que el silencio del sistema nunca se confunda con ausencia de ofertas.

## ADDED Requirements

### Requirement: Umbral relativo de bajada

El sistema SHALL emitir una alerta de bajada únicamente cuando el precio nuevo sea inferior al último precio notificado de esa misma serie en al menos el porcentaje configurado.

#### Scenario: Bajada por encima del umbral

- **WHEN** el umbral configurado es del 5% y el precio baja un 6% respecto al último notificado de esa serie
- **THEN** el sistema emite una alerta

#### Scenario: Bajada por debajo del umbral

- **WHEN** el precio baja un 2% respecto al último notificado de esa serie
- **THEN** el sistema registra el precio pero no emite alerta

#### Scenario: Bajada solo respecto a otra fuente

- **WHEN** un precio de una fuente es inferior al mínimo registrado de otra fuente, pero no al de la suya
- **THEN** el sistema no emite alerta de bajada

### Requirement: Notificación del precio de referencia inicial

Al activarse una búsqueda, el sistema SHALL notificar el primer precio obtenido de cada fuente como referencia de partida.

#### Scenario: Primer sondeo tras el alta

- **WHEN** una búsqueda recién activada obtiene sus primeros precios
- **THEN** el sistema envía un mensaje con el precio de partida de cada fuente
- **AND** en modo flexible indica también cuál es el bloque de fechas más barato encontrado

### Requirement: Resumen diario

El sistema SHALL enviar una vez al día, a la hora configurada, un resumen de todas las búsquedas activas, aunque no haya habido ningún cambio de precio.

#### Scenario: Resumen con cambios

- **WHEN** llega la hora configurada y ha habido movimientos de precio
- **THEN** el resumen muestra por búsqueda el precio actual, el mínimo histórico y la variación

#### Scenario: Resumen sin cambios

- **WHEN** llega la hora configurada y no ha habido ningún cambio
- **THEN** el sistema envía igualmente el resumen, para acreditar que sigue operativo

#### Scenario: Sin búsquedas activas

- **WHEN** llega la hora configurada y el usuario no tiene búsquedas activas
- **THEN** el sistema no envía resumen

### Requirement: Contenido mínimo de una alerta

Toda alerta de precio SHALL incluir la ruta y las fechas concretas, el precio y su moneda, la fuente, la antigüedad del dato, las etiquetas de riesgo del resultado, el enlace de verificación y un control para detener la búsqueda.

#### Scenario: Alerta de bajada

- **WHEN** el sistema emite una alerta de bajada
- **THEN** el mensaje incluye todos los elementos mínimos
- **AND** indica la diferencia respecto al precio anterior notificado

#### Scenario: Alerta sobre un resultado con etiquetas de riesgo

- **WHEN** el resultado que dispara la alerta está etiquetado como billetes separados o sin equipaje facturado
- **THEN** la alerta muestra esas etiquetas junto al precio

### Requirement: El precio comunicado no se presenta como garantizado

Todo mensaje que comunique un precio SHALL indicar el instante en que se obtuvo y SHALL invitar a verificarlo en el enlace antes de comprar.

#### Scenario: Cualquier mensaje con precio

- **WHEN** el sistema envía un mensaje que contiene un precio
- **THEN** el mensaje indica hace cuánto se obtuvo el dato
- **AND** advierte de que debe verificarse antes de reservar

### Requirement: Las subidas no interrumpen

El sistema NO SHALL emitir alertas inmediatas por subidas de precio. Las subidas SHALL reflejarse únicamente en el resumen diario.

#### Scenario: El precio sube

- **WHEN** un sondeo devuelve un precio superior al último notificado
- **THEN** el sistema lo registra en la serie sin enviar alerta
- **AND** la variación aparece en el siguiente resumen diario

### Requirement: Aviso de fuente caída

El sistema SHALL avisar al usuario cuando una fuente deje de funcionar y cuando se restablezca, para que la ausencia de alertas no se interprete como ausencia de ofertas.

#### Scenario: Una fuente cae

- **WHEN** el control de disponibilidad determina que una fuente ha dejado de responder
- **THEN** el sistema envía un aviso indicando qué fuente y desde cuándo

#### Scenario: Fuente restablecida

- **WHEN** una fuente caída vuelve a responder
- **THEN** el sistema envía un aviso de restablecimiento

### Requirement: Cierre de una búsqueda

El sistema SHALL notificar al usuario cuando una búsqueda deje de vigilarse, indicando el motivo y el precio mínimo que llegó a registrarse.

#### Scenario: Búsqueda vencida por fecha

- **WHEN** una búsqueda pasa a vencida
- **THEN** el sistema informa del cierre, del motivo y del mínimo histórico alcanzado

#### Scenario: Búsqueda fallida

- **WHEN** una búsqueda pasa a fallida por no obtener resultados de forma persistente
- **THEN** el sistema informa de que ha dejado de vigilarla y de que el motivo es un fallo, no la ausencia de vuelos
