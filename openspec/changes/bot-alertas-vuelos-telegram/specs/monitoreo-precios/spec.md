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

### Requirement: Niveles de refresco en modo flexible

Para una búsqueda en modo de ventana flexible, el sistema SHALL separar el barrido completo de la ventana del seguimiento frecuente, para acotar el número de consultas.

#### Scenario: Barrido completo diario

- **WHEN** transcurre el periodo configurado para el barrido completo
- **THEN** el sistema evalúa todos los bloques posibles de la ventana
- **AND** selecciona los bloques más baratos para el seguimiento frecuente

#### Scenario: Seguimiento frecuente acotado

- **WHEN** se ejecuta un sondeo ordinario sobre una búsqueda en modo flexible
- **THEN** el sistema consulta únicamente los bloques seleccionados en el último barrido completo

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
