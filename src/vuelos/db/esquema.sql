-- Esquema de la base de datos. Ver design.md, apartado "Modelo de datos".
--
-- Dos criterios que explican por que las cosas estan donde estan:
--
-- 1. `notificaciones` esta separada de `precios` a proposito. El umbral de
--    alerta se evalua contra el ultimo precio NOTIFICADO, no contra el ultimo
--    registrado. Sin esa distincion, una bajada lenta y sostenida generaria un
--    aviso en cada sondeo.
--
-- 2. Los conjuntos cerrados y conocidos van en columnas, no en JSON. Los
--    filtros de una busqueda y las advertencias de un precio estan fijados en
--    las specs, asi que el motor puede validarlos y se pueden consultar con
--    WHERE. Solo queda como JSON lo que es una lista abierta y que nunca se
--    consulta por sus partes.
--
-- Las fechas van en TEXT ISO-8601 porque SQLite no tiene tipo fecha: los tipos
-- de almacenamiento reales son NULL, INTEGER, REAL, TEXT y BLOB. ISO-8601
-- ordena bien alfabeticamente y lo entienden las funciones date() del motor.
-- Los instantes se guardan SIEMPRE en UTC con desplazamiento explicito; el
-- repositorio rechaza los que llegan sin zona horaria.

CREATE TABLE IF NOT EXISTS busquedas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id           INTEGER NOT NULL,
    origen            TEXT    NOT NULL,
    destino           TEXT    NOT NULL,

    -- 'A' = fechas exactas, 'B' = ventana flexible con duracion en noches
    modo              TEXT    NOT NULL CHECK (modo IN ('A', 'B')),

    -- Modo A
    salida            TEXT,
    regreso           TEXT,

    -- Modo B
    ventana_ini       TEXT,
    ventana_fin       TEXT,
    duracion_noches   INTEGER,

    -- Filtros. Conjunto cerrado, fijado en la spec interfaz-telegram.
    -- NULL significa "sin restriccion".
    max_escalas         INTEGER CHECK (max_escalas IS NULL OR max_escalas >= 0),
    max_escala_minutos  INTEGER CHECK (max_escala_minutos IS NULL OR max_escala_minutos > 0),
    requiere_maleta     INTEGER NOT NULL DEFAULT 0 CHECK (requiere_maleta IN (0, 1)),
    franja_horaria      TEXT CHECK (franja_horaria IS NULL
                                    OR franja_horaria IN ('manana', 'tarde', 'noche')),

    estado            TEXT    NOT NULL DEFAULT 'activa'
                      CHECK (estado IN ('activa', 'pausada', 'terminada_por_usuario',
                                        'vencida', 'fallida')),
    pausada_hasta     TEXT,
    sondeos_fallidos  INTEGER NOT NULL DEFAULT 0,

    creada_en         TEXT    NOT NULL,
    actualizada_en    TEXT    NOT NULL,

    -- Coherencia entre modo y fechas: que la base no admita una busqueda a medias
    CHECK (
        (modo = 'A' AND salida IS NOT NULL AND regreso IS NOT NULL)
        OR
        (modo = 'B' AND ventana_ini IS NOT NULL AND ventana_fin IS NOT NULL
                    AND duracion_noches IS NOT NULL)
    )
);

-- El filtro de aerolineas si es una relacion uno-a-muchos de verdad.
CREATE TABLE IF NOT EXISTS busqueda_aerolineas (
    busqueda_id  INTEGER NOT NULL REFERENCES busquedas(id) ON DELETE CASCADE,
    aerolinea    TEXT    NOT NULL,
    PRIMARY KEY (busqueda_id, aerolinea)
);

CREATE TABLE IF NOT EXISTS precios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    busqueda_id       INTEGER NOT NULL REFERENCES busquedas(id) ON DELETE CASCADE,
    fuente            TEXT    NOT NULL,

    -- Bloque de fechas concreto al que corresponde este precio. En modo B
    -- identifica cual de los bloques posibles es.
    salida            TEXT    NOT NULL,
    regreso           TEXT    NOT NULL,

    -- Importe tal como lo devolvio la fuente
    precio            REAL    NOT NULL,
    moneda            TEXT    NOT NULL,

    -- Importe convertido a la moneda de referencia, y el cambio aplicado.
    -- Si la fuente ya devolvio la moneda de referencia, cambio_aplicado es 1.0.
    precio_ref        REAL    NOT NULL,
    moneda_ref        TEXT    NOT NULL,
    cambio_aplicado   REAL    NOT NULL DEFAULT 1.0,

    -- Mercado bajo el que se obtuvo. Un precio de otro mercado no debe entrar.
    mercado           TEXT    NOT NULL,

    escalas           INTEGER,

    -- Advertencias sobre comparabilidad y riesgo. Conjunto cerrado, fijado en
    -- la spec proveedores-precios. En columnas porque se filtra por ellas.
    billetes_separados      INTEGER NOT NULL DEFAULT 0 CHECK (billetes_separados IN (0, 1)),
    sin_equipaje_facturado  INTEGER NOT NULL DEFAULT 0 CHECK (sin_equipaje_facturado IN (0, 1)),
    no_verificable          INTEGER NOT NULL DEFAULT 0 CHECK (no_verificable IN (0, 1)),
    ciudad_oculta           INTEGER NOT NULL DEFAULT 0 CHECK (ciudad_oculta IN (0, 1)),
    billete_desechado       INTEGER NOT NULL DEFAULT 0 CHECK (billete_desechado IN (0, 1)),

    -- Lista abierta de nombres de aerolinea del itinerario, solo para mostrar.
    -- Nunca se consulta por sus partes: el filtro de aerolineas se aplica en la
    -- peticion a la fuente, no en SQL. Por eso sigue siendo JSON.
    aerolineas        TEXT,

    enlace            TEXT,
    obtenido_en       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS notificaciones (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    busqueda_id        INTEGER NOT NULL REFERENCES busquedas(id) ON DELETE CASCADE,
    fuente             TEXT    NOT NULL,
    precio_notificado  REAL    NOT NULL,
    moneda_ref         TEXT    NOT NULL,
    motivo             TEXT    NOT NULL
                       CHECK (motivo IN ('referencia_inicial', 'bajada', 'cierre')),
    enviada_en         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS estado_fuentes (
    fuente        TEXT    PRIMARY KEY,
    operativa     INTEGER NOT NULL DEFAULT 1,
    ultimo_ok     TEXT,
    ultimo_fallo  TEXT,
    avisado_en    TEXT
);

-- Indices. Las lecturas calientes son siempre "la serie de esta busqueda en
-- esta fuente, ordenada por instante" o "el minimo de esa serie".
CREATE INDEX IF NOT EXISTS idx_precios_serie
    ON precios (busqueda_id, fuente, obtenido_en DESC);
CREATE INDEX IF NOT EXISTS idx_precios_bloque
    ON precios (busqueda_id, fuente, salida, regreso, obtenido_en DESC);
CREATE INDEX IF NOT EXISTS idx_precios_minimo
    ON precios (busqueda_id, fuente, precio_ref ASC);
CREATE INDEX IF NOT EXISTS idx_notificaciones_serie
    ON notificaciones (busqueda_id, fuente, enviada_en DESC);
CREATE INDEX IF NOT EXISTS idx_busquedas_activas
    ON busquedas (estado, chat_id);
