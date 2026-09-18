## Purpose

Telegram es la única interfaz del sistema. Esta capacidad traduce los mensajes de texto del usuario en búsquedas vigiladas, confirma su interpretación antes de activarlas y le da control sobre el ciclo de vida de cada una.

## ADDED Requirements

### Requirement: Alta de búsqueda por texto en dos modos

El sistema SHALL aceptar el alta de una búsqueda mediante un mensaje de texto en uno de dos modos: fechas exactas (modo A) o ventana flexible con duración fija (modo B).

#### Scenario: Alta en modo A con fechas exactas

- **WHEN** el usuario envía `BOG > RDU 20ene 15feb`
- **THEN** el sistema interpreta origen BOG, destino RDU, salida el 20 de enero y regreso el 15 de febrero
- **AND** presenta la interpretación para confirmación

#### Scenario: Alta en modo B con ventana y duración

- **WHEN** el usuario envía `BOG > RDU 20ene-15feb 12d`
- **THEN** el sistema interpreta una ventana del 20 de enero al 15 de febrero y un viaje de 12 días
- **AND** indica cuántas combinaciones de fechas evaluará dentro de esa ventana
- **AND** presenta la interpretación para confirmación

#### Scenario: Duración mayor que la ventana

- **WHEN** el usuario envía una duración que no cabe en la ventana indicada
- **THEN** el sistema rechaza el alta e indica la duración máxima admitida para esa ventana

### Requirement: Confirmación explícita antes de activar

El sistema SHALL mostrar su interpretación completa de la solicitud y SHALL exigir confirmación del usuario mediante botones antes de activar la búsqueda. Una búsqueda sin confirmar no consume cupo ni genera consultas.

#### Scenario: El usuario confirma

- **WHEN** el sistema muestra la interpretación y el usuario pulsa Confirmar
- **THEN** la búsqueda pasa a estado activa y comienza a ser vigilada

#### Scenario: El usuario cancela

- **WHEN** el sistema muestra la interpretación y el usuario pulsa Cancelar
- **THEN** la búsqueda se descarta y no se realiza ninguna consulta

#### Scenario: El usuario corrige a fechas flexibles

- **WHEN** el sistema interpreta fechas exactas y el usuario pulsa la opción de fechas flexibles
- **THEN** el sistema pide la duración del viaje y vuelve a presentar la interpretación en modo B

### Requirement: Resolución de fechas sin año

El sistema SHALL asumir que una fecha escrita sin año corresponde a la próxima ocurrencia futura de esa fecha, y SHALL mostrar el año resuelto en la confirmación.

#### Scenario: Fecha que ya pasó en el año en curso

- **WHEN** hoy es 18 de septiembre de 2026 y el usuario escribe `20ene`
- **THEN** el sistema resuelve la fecha como 20 de enero de 2027
- **AND** muestra el año completo en la confirmación

### Requirement: Resolución de ciudad a código de aeropuerto

El sistema SHALL aceptar nombres de ciudad además de códigos IATA, y SHALL resolverlos a códigos de aeropuerto concretos antes de confirmar.

#### Scenario: Ciudad con un aeropuerto principal

- **WHEN** el usuario escribe `Raleigh` como destino
- **THEN** el sistema lo resuelve a RDU y lo muestra en la confirmación

#### Scenario: Ciudad con varios aeropuertos

- **WHEN** el usuario escribe una ciudad servida por varios aeropuertos
- **THEN** el sistema pide al usuario elegir entre ellos antes de continuar

#### Scenario: Origen o destino no reconocido

- **WHEN** el usuario escribe un lugar que el sistema no puede resolver
- **THEN** el sistema responde indicando qué término no reconoció y no crea la búsqueda

### Requirement: Filtros opcionales en la misma línea

El sistema SHALL aceptar filtros opcionales al final del mensaje de alta, en cualquier orden: número máximo de escalas, duración máxima de escala, equipaje facturado, franja horaria de salida y aerolíneas.

#### Scenario: Alta con filtros

- **WHEN** el usuario envía `BOG > RDU 20ene-15feb 12d maleta max1escala manana`
- **THEN** el sistema aplica los tres filtros y los enumera en la confirmación

#### Scenario: Filtro no reconocido

- **WHEN** el mensaje contiene un término que no corresponde a ningún filtro conocido
- **THEN** el sistema señala ese término concreto y pide corrección, sin crear la búsqueda

### Requirement: Listado y control de búsquedas

El sistema SHALL ofrecer un comando que liste las búsquedas del usuario con su estado, precio actual y precio mínimo registrado, acompañando cada una de controles para detenerla o pausarla.

#### Scenario: Listado con búsquedas activas

- **WHEN** el usuario envía el comando de listado
- **THEN** el sistema muestra cada búsqueda con ruta, fechas, estado, precio actual y mínimo histórico
- **AND** adjunta a cada una botones de Detener y Pausar

#### Scenario: Listado sin búsquedas

- **WHEN** el usuario envía el comando de listado y no tiene ninguna búsqueda
- **THEN** el sistema responde indicándolo y recuerda el formato de alta

### Requirement: Detener una búsqueda desde su alerta

Cada alerta de precio SHALL incluir un control para detener la búsqueda que la originó, sin necesidad de listar ni de identificarla por código.

#### Scenario: Detener desde la alerta recibida

- **WHEN** el usuario pulsa Detener esta búsqueda en una alerta
- **THEN** la búsqueda pasa a estado terminada y deja de generar consultas y alertas
- **AND** el sistema confirma la acción en el mismo hilo

### Requirement: Pausa temporal

El sistema SHALL permitir pausar una búsqueda durante un periodo determinado, tras el cual vuelve a estado activo automáticamente.

#### Scenario: Pausar y reanudar

- **WHEN** el usuario pausa una búsqueda por 7 días
- **THEN** el sistema deja de consultarla y de alertar durante ese periodo
- **AND** la reactiva automáticamente al vencer el plazo, informando al usuario

### Requirement: Límite de búsquedas activas

El sistema SHALL limitar el número de búsquedas simultáneamente activas por usuario para acotar el volumen de consultas a las fuentes.

#### Scenario: Se alcanza el límite

- **WHEN** el usuario intenta activar una búsqueda por encima del límite configurado
- **THEN** el sistema rechaza el alta, indica el límite y ofrece listar las activas para detener alguna

### Requirement: Respuesta ante entrada no reconocida

El sistema SHALL responder a cualquier mensaje que no pueda interpretar con una explicación del formato admitido y un ejemplo concreto de cada modo.

#### Scenario: Mensaje sin formato reconocible

- **WHEN** el usuario envía texto que no encaja en ningún modo ni comando
- **THEN** el sistema responde con los dos formatos de alta y un ejemplo de cada uno
