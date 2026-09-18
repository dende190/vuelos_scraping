## Purpose

Decide cuándo y con qué frecuencia se consulta cada búsqueda, y acumula el histórico de precios que hace posible distinguir una bajada real de una fluctuación.

## ADDED Requirements

### Requirement: Sondeo periódico con separación irregular

El sistema SHALL consultar cada búsqueda activa a un intervalo configurado, aplicando a cada ejecución un desplazamiento aleatorio. Las consultas NO SHALL producirse a horas exactas ni a intervalos constantes.

#### Scenario: Intervalo con desplazamiento

- **WHEN** el intervalo configurado es de 4 horas con un desplazamiento máximo de 20 minutos
- **THEN** cada sondeo se ejecuta entre 3 h 40 min y 4 h 20 min después del anterior

#### Scenario: Varias búsquedas activas

- **WHEN** hay varias búsquedas activas cuyos sondeos coinciden en el tiempo
- **THEN** el sistema las ejecuta de forma secuencial y separadas entre sí, nunca en paralelo

### Requirement: Coste acotado de la ventana flexible

Para una búsqueda en modo de ventana flexible, el sistema SHALL evaluar la ventana completa al menos una vez al día contra cada fuente, sin que el número de consultas crezca con el número de bloques cuando la fuente permite resolver la ventana en una sola petición.

#### Scenario: Fuente que resuelve la ventana de una vez

- **WHEN** una fuente admite consultar un rango de fechas de salida junto con una duración de viaje
- **THEN** el sistema obtiene todos los bloques en una sola consulta
- **AND** puede repetirla en cada sondeo ordinario

#### Scenario: Fuente que exige consultar bloque a bloque

- **WHEN** una fuente solo admite consultar un par de fechas concreto
- **THEN** el sistema evalúa la ventana completa una vez al día
- **AND** en los sondeos ordinarios consulta únicamente los bloques más baratos del último barrido

#### Scenario: El coste se mantiene acotado

- **WHEN** se amplía la ventana de una búsqueda de modo que crece el número de bloques posibles
- **THEN** el número de consultas diarias contra una fuente que resuelve la ventana de una vez no aumenta

### Requirement: Serie histórica por búsqueda y fuente

El sistema SHALL mantener una serie de precios independiente para cada combinación de búsqueda y fuente, y SHALL evaluar bajadas comparando únicamente dentro de la misma serie.

#### Scenario: Registro de un precio

- **WHEN** una consulta devuelve un precio válido para una búsqueda y una fuente
- **THEN** el sistema lo añade a la serie de esa combinación, con su instante de obtención

#### Scenario: Primer precio de una fuente

- **WHEN** una fuente aporta su primer precio para una búsqueda que ya tiene histórico de otra fuente
- **THEN** ese precio inicia una serie nueva y no se compara contra el mínimo de la otra fuente

### Requirement: Respeto de los límites de las fuentes

El sistema SHALL reducir su ritmo de consultas cuando una fuente señale exceso de peticiones, y SHALL reintentar con esperas crecientes antes de considerar la consulta fallida.

#### Scenario: La fuente señala exceso de peticiones

- **WHEN** una fuente responde indicando que se ha superado su límite de peticiones
- **THEN** el sistema espera un tiempo creciente entre reintentos
- **AND** no lanza nuevas consultas a esa fuente mientras dure la espera

#### Scenario: Se agotan los reintentos

- **WHEN** se agotan los reintentos configurados sin obtener respuesta útil
- **THEN** el sistema registra el sondeo como fallido para esa fuente y continúa con el resto

### Requirement: Solo las búsquedas activas consumen consultas

El sistema NO SHALL consultar fuentes para búsquedas que no estén en estado activo.

#### Scenario: Búsqueda pausada, terminada o vencida

- **WHEN** llega el momento de un sondeo y la búsqueda no está activa
- **THEN** el sistema omite la consulta y no la contabiliza como fallo
