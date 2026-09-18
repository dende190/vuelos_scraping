# Bot de Telegram para vigilancia de precios de vuelos

## Why

Vigilar a mano el precio de un vuelo durante semanas no es viable: los precios cambian varias veces al día y el momento bueno dura horas. Google Flights ofrece un seguimiento de precios propio, pero no permite definir el umbral, ni combinar varias fuentes, ni acumular histórico propio, ni responder a "¿qué bloque de 12 días dentro de esta ventana sale más barato?".

Este cambio crea un bot de Telegram que vigila varias búsquedas en paralelo, guarda el histórico de precios y avisa solo cuando la bajada es relevante. Telegram es la única interfaz: no hay web, no hay login, no hay app.

## What Changes

**Interfaz conversacional (Telegram)**
- Alta de búsquedas con un formato de texto corto, en dos modos:
  - **Modo A — fechas exactas**: `BOG > RDU 20ene 15feb`
  - **Modo B — ventana flexible + duración**: `BOG > RDU 20ene-15feb 12d` (busca el mejor bloque de 12 días dentro de la ventana)
- Filtros opcionales en la misma línea: `directo`, `max1escala`, `escala<4h`, `maleta`, `manana`/`tarde`/`noche`, y códigos de aerolínea.
- Toda alta se confirma con botones inline antes de activarse: el bot muestra cómo interpretó ciudades, códigos IATA, años y duración. Esto elimina la ambigüedad del texto libre sin necesidad de NLP.
- Gestión del ciclo de vida: `/lista` con botones por búsqueda, **Detener**, **Pausar 7d**, y un botón **Detener esta búsqueda** en cada alerta.

**Fuentes de precios**
- Dos proveedores tras una interfaz común: **Google Flights** (vía `fast-flights`) y **Kiwi** (vía su GraphQL público sin API key).
- **Punto de venta fijo en Colombia** (`gl=co`) en todas las consultas. Un precio de otro mercado sería un fallo silencioso: plausible pero impagable para el usuario.
- **Canario de salud**: una consulta fija y conocida cada 6 h. Si devuelve cero resultados, el bot avisa de "fuente caída" en vez de dejar creer que no hay ofertas.

**Monitoreo**
- Sondeo cada ~4 h con jitter aleatorio de ±20 min. Las tarifas se recargan pocas veces al día; sondear cada minutos solo multiplica el riesgo de bloqueo sin ganar información.
- En modo B, barrido completo de la ventana 1x/día y seguimiento cada 4 h solo sobre los 3 mejores bloques.
- **Una serie histórica de precios independiente por fuente.** Comparar un precio de Kiwi contra el mínimo de Google produce bajadas falsas.

**Alertas**
- Notificación solo si el precio baja ≥5% respecto al último mínimo notificado de esa misma fuente.
- Resumen diario a las 08:00 (hora Colombia) con precio actual y mínimo histórico, aunque no haya cambios: sin él no se sabe si el bot sigue vivo.
- Cada alerta lleva fuente, antigüedad del dato, deep link de reserva y etiquetas de riesgo (`[self-transfer]`, `[sin maleta]`, `[2 billetes]`).

**Fuera de alcance en este MVP** (acordado explícitamente):
- Calendario de precios verde/amarillo/rojo por mes.
- Alertas en el navegador (Web Push) e interfaz web.
- Comparación multi-punto-de-venta: el usuario compra siempre en Colombia.
- Descubrimiento de ofertas en rutas no solicitadas.
- Recomendación de "mejor día para comprar", que requiere un histórico que aún no existe.

## Capabilities

### New Capabilities
- `interfaz-telegram`: alta de búsquedas por texto, confirmación con botones, comandos de gestión y ciclo de vida operado por el usuario.
- `busquedas-vuelos`: modelo de búsqueda (ruta, modo A/B, filtros), estados y transiciones, y reglas de vencimiento.
- `proveedores-precios`: interfaz común de proveedor, adaptadores de Google Flights y Kiwi, punto de venta fijo, etiquetado de resultados no comparables y canario de salud.
- `monitoreo-precios`: programación de sondeos, jitter, niveles de refresco y series históricas de precios por fuente.
- `alertas-precios`: umbrales de notificación, anti-spam, resumen diario y contenido de los mensajes.

### Modified Capabilities

Ninguna. El repositorio no tiene specs previas.

## Impact

**Stack nuevo** (no hay código previo; el repositorio solo contiene el andamiaje de OpenSpec):

| Pieza | Elección |
|---|---|
| Lenguaje | Python |
| Bot | `python-telegram-bot` (async) |
| Programación | APScheduler |
| Persistencia | SQLite |
| Fuente 1 | `fast-flights` (Google Flights, sin navegador) |
| Fuente 2 | Kiwi GraphQL público (`api.skypicker.com/umbrella/v2/graphql`) |
| Despliegue | Un proceso en VPS propio (OVH) |

**Riesgos asumidos y su mitigación**

1. **Dependencia de fuentes no oficiales.** `fast-flights` tiene incidencias abiertas de marzo y mayo de 2026 (fallos 401, resultados sin parsear). Mitigación: dos fuentes independientes más canario de salud. La primera tarea del plan es verificar que la librería funciona hoy para la ruta real; si no, la propuesta cambia.
2. **Términos de servicio.** El acceso automatizado a Google Flights va contra sus condiciones. Se asume conscientemente a volumen bajo (decenas de consultas/día), uso personal y sin redistribución de datos.
3. **IP de datacenter.** OVH puede recibir peor trato que una IP residencial. Se mide antes de mitigar; si hay bloqueo, el plan B es un túnel a una máquina doméstica, y el plan C quedarse solo con Kiwi.
4. **Precios informativos, no contractuales.** Los mensajes muestran antigüedad del dato y enlace de verificación; el bot nunca afirma un precio como garantizado.
