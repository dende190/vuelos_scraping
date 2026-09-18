## Purpose

Aísla al resto del sistema de las fuentes concretas de las que salen los precios, garantiza que los precios obtenidos sean los que el usuario puede realmente pagar y detecta cuándo una fuente ha dejado de funcionar.

## ADDED Requirements

### Requirement: Varias fuentes independientes

El sistema SHALL consultar al menos dos fuentes de precios independientes entre sí, y SHALL seguir operando cuando una de ellas falle.

#### Scenario: Ambas fuentes responden

- **WHEN** se ejecuta un sondeo y todas las fuentes devuelven resultados
- **THEN** el sistema registra los resultados de cada fuente por separado

#### Scenario: Una fuente falla

- **WHEN** una fuente devuelve error o ningún resultado y la otra responde correctamente
- **THEN** el sistema registra los resultados de la fuente que respondió
- **AND** contabiliza el fallo de la otra sin interrumpir el sondeo

### Requirement: Búsqueda en ventana flexible

La capa de proveedores SHALL ofrecer una operación de búsqueda que reciba una ventana de fechas de salida y una duración de viaje en noches, y SHALL devolver los itinerarios de los bloques posibles con independencia de cuántas peticiones necesite cada fuente para resolverla.

#### Scenario: Ventana resuelta contra cualquier fuente

- **WHEN** se solicita una búsqueda con una ventana de fechas y una duración en noches
- **THEN** el resultado incluye itinerarios de los bloques evaluados, cada uno con sus fechas concretas de salida y regreso
- **AND** quien la invoca no necesita saber cuántas peticiones hizo la fuente

#### Scenario: Bloque más barato identificable

- **WHEN** una búsqueda en ventana flexible devuelve resultados de varios bloques
- **THEN** cada resultado indica a qué bloque de fechas corresponde, de modo que pueda determinarse el más barato

### Requirement: Punto de venta fijo

Todas las consultas de precio SHALL realizarse con el punto de venta y la moneda de referencia configurados para el usuario, de forma explícita y constante. Un precio obtenido bajo un punto de venta distinto del configurado NO SHALL registrarse.

#### Scenario: Consulta con el punto de venta configurado

- **WHEN** el sistema consulta una fuente
- **THEN** la consulta declara explícitamente el punto de venta configurado
- **AND** el resultado se registra indicando bajo qué punto de venta se obtuvo

#### Scenario: La fuente no permite fijar el punto de venta

- **WHEN** una fuente no admite declarar el punto de venta configurado
- **THEN** el sistema no usa esa fuente para registrar precios
- **AND** deja constancia del motivo

### Requirement: Etiquetado de resultados no directamente comparables

Cada resultado SHALL llevar las etiquetas que adviertan de condiciones que afectan a su comparabilidad o a su riesgo, en particular billetes separados, conexiones autogestionadas y ausencia de equipaje facturado.

#### Scenario: Resultado con conexión autogestionada

- **WHEN** una fuente devuelve un itinerario compuesto por billetes separados
- **THEN** el resultado queda etiquetado como tal
- **AND** la etiqueta acompaña al precio en cualquier mensaje que lo muestre

#### Scenario: Resultado sin equipaje facturado

- **WHEN** un resultado no incluye equipaje facturado
- **THEN** el resultado queda etiquetado como tal

### Requirement: Datos mínimos de un resultado

Todo resultado registrado SHALL incluir precio, moneda, fuente, instante de obtención y un enlace que permita al usuario verificar y reservar. Un resultado sin enlace de verificación SHALL registrarse marcado como no verificable.

#### Scenario: Resultado completo

- **WHEN** una fuente devuelve un itinerario con todos los datos mínimos
- **THEN** el sistema lo registra y puede usarlo para alertar

#### Scenario: Resultado sin enlace de verificación

- **WHEN** una fuente devuelve un itinerario sin enlace de reserva
- **THEN** el sistema lo registra marcado como no verificable
- **AND** cualquier alerta que lo incluya advierte de que no hay enlace directo

### Requirement: Moneda única de comparación

El sistema SHALL comparar precios entre sí únicamente dentro de la misma moneda de referencia, y NO SHALL mezclar en una misma serie precios obtenidos en monedas distintas.

#### Scenario: Comparación dentro de la moneda de referencia

- **WHEN** se evalúa si un precio nuevo es menor que el mínimo registrado
- **THEN** la comparación se realiza sobre valores en la moneda de referencia configurada

#### Scenario: Precio devuelto en otra moneda

- **WHEN** una fuente devuelve un precio en una moneda distinta de la de referencia
- **THEN** el sistema convierte el valor y registra tanto el importe original como el convertido y el cambio aplicado

### Requirement: Canario de disponibilidad de las fuentes

El sistema SHALL ejecutar periódicamente una consulta de control, de ruta y fechas conocidas y estables, contra cada fuente, para distinguir la ausencia de ofertas de la caída de la fuente.

#### Scenario: La consulta de control no devuelve resultados

- **WHEN** la consulta de control contra una fuente devuelve cero resultados
- **THEN** el sistema marca esa fuente como caída
- **AND** notifica al usuario que la fuente ha dejado de responder

#### Scenario: La fuente se restablece

- **WHEN** una fuente marcada como caída vuelve a devolver resultados en la consulta de control
- **THEN** el sistema la marca como operativa y notifica el restablecimiento

#### Scenario: Todas las fuentes caídas

- **WHEN** todas las fuentes están marcadas como caídas
- **THEN** el sistema lo comunica de forma destacada, porque en ese estado la ausencia de alertas no significa ausencia de ofertas
