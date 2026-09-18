## Purpose

Define qué es una búsqueda vigilada de vuelos, qué estados atraviesa y cuándo deja de consumir recursos. Es el modelo central del que dependen el monitoreo y las alertas.

## ADDED Requirements

### Requirement: Definición de una búsqueda

Una búsqueda SHALL quedar definida por un aeropuerto de origen, un aeropuerto de destino, un modo de fechas, las fechas correspondientes a ese modo y un conjunto opcional de filtros.

#### Scenario: Búsqueda en modo de fechas exactas

- **WHEN** se crea una búsqueda con fecha de salida y fecha de regreso concretas
- **THEN** el sistema vigila exclusivamente ese par de fechas

#### Scenario: Búsqueda en modo de ventana flexible

- **WHEN** se crea una búsqueda con una ventana de fechas y una duración de viaje en días
- **THEN** el sistema vigila todos los bloques de esa duración que caben completos dentro de la ventana

### Requirement: Evaluación de bloques en modo flexible

En modo de ventana flexible, el sistema SHALL evaluar cada bloque posible de la duración indicada y SHALL identificar el bloque de menor precio como recomendación al usuario.

#### Scenario: Ventana de 27 días con bloques de 12 días

- **WHEN** la ventana abarca 27 días y la duración es de 12 días
- **THEN** el sistema evalúa los 16 bloques posibles
- **AND** informa cuál es el bloque más barato con sus fechas concretas de salida y regreso

#### Scenario: La recomendación cambia

- **WHEN** en un sondeo posterior el bloque más barato pasa a ser otro distinto
- **THEN** el sistema registra el cambio y lo refleja en la siguiente comunicación al usuario

### Requirement: Estados de una búsqueda

Una búsqueda SHALL encontrarse siempre en exactamente uno de estos estados: activa, pausada, terminada por el usuario, vencida o fallida. Solo las búsquedas activas generan consultas a las fuentes.

#### Scenario: Activa a pausada y de vuelta

- **WHEN** el usuario pausa una búsqueda activa
- **THEN** la búsqueda pasa a pausada y deja de generar consultas
- **AND** al vencer el plazo de pausa vuelve al estado activa

#### Scenario: Terminada por el usuario

- **WHEN** el usuario detiene una búsqueda
- **THEN** la búsqueda pasa a terminada por el usuario y no vuelve a generar consultas ni alertas

#### Scenario: Una búsqueda pausada no consulta

- **WHEN** llega el momento de un sondeo programado y la búsqueda está pausada
- **THEN** el sistema omite la consulta sin registrarla como fallo

### Requirement: Vencimiento automático

El sistema SHALL pasar automáticamente a estado vencida toda búsqueda cuya fecha relevante haya quedado en el pasado, y SHALL notificarlo al usuario.

#### Scenario: Vence una búsqueda de fechas exactas

- **WHEN** se alcanza la fecha de salida de una búsqueda en modo de fechas exactas
- **THEN** la búsqueda pasa a vencida y deja de consultarse
- **AND** el sistema informa al usuario del cierre y del precio mínimo que llegó a registrar

#### Scenario: Vence una búsqueda de ventana flexible

- **WHEN** ya no queda dentro de la ventana ningún bloque completo de la duración pedida que empiece en el futuro
- **THEN** la búsqueda pasa a vencida

### Requirement: Fallo persistente de las fuentes

El sistema SHALL pasar una búsqueda a estado fallida cuando sus consultas no obtengan ningún resultado utilizable durante un número consecutivo de sondeos configurado, y SHALL avisar al usuario en lugar de permanecer en silencio.

#### Scenario: Sondeos consecutivos sin resultados

- **WHEN** una búsqueda acumula el número configurado de sondeos consecutivos sin resultados en ninguna fuente
- **THEN** la búsqueda pasa a fallida
- **AND** el sistema avisa al usuario de que ha dejado de obtener precios para esa búsqueda

#### Scenario: Recuperación antes del umbral

- **WHEN** una búsqueda con sondeos fallidos vuelve a obtener resultados antes de alcanzar el umbral
- **THEN** el contador de fallos se reinicia y la búsqueda permanece activa

### Requirement: Conservación del histórico al terminar

Terminar, vencer o marcar como fallida una búsqueda NO SHALL eliminar los precios registrados para ella. El histórico SHALL conservarse para análisis posterior.

#### Scenario: Terminar conserva los precios

- **WHEN** el usuario detiene una búsqueda que acumulaba histórico de precios
- **THEN** el sistema deja de consultar, pero los precios registrados siguen disponibles

#### Scenario: Borrado explícito

- **WHEN** el usuario solicita explícitamente borrar una búsqueda y sus datos
- **THEN** el sistema elimina también su histórico de precios, tras pedir confirmación

### Requirement: Filtros aplicados a la búsqueda

Los filtros declarados en una búsqueda SHALL aplicarse a todos sus resultados antes de que estos entren en el histórico de precios.

#### Scenario: Filtro de equipaje

- **WHEN** una búsqueda declara que requiere equipaje facturado
- **THEN** los resultados que no lo incluyan quedan excluidos del histórico y no pueden disparar alertas

#### Scenario: Filtro de escalas

- **WHEN** una búsqueda declara un máximo de escalas
- **THEN** los resultados con más escalas quedan excluidos del histórico
