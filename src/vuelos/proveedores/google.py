"""Adaptador de Google Flights.

No usa `fast_flights.get_flights`: esa función construye la petición con
`tfs`, `hl` y `curr` y **no envía el país** (`gl`). Como el usuario compra
siempre en Colombia, un precio de otro mercado sería plausible pero
impagable, así que aquí se reutilizan el codificador y el analizador de la
librería y se compone la petición a mano con `gl` explícito.

Verificado el 18-sep-2026: Google sí lee `gl`. Con la moneda libre, sin `gl`
responde en pesos colombianos y con `gl=US` en dólares.

Límites conocidos de esta fuente, medidos contra el navegador:
  - Devuelve la selección destacada de Google, no todos los itinerarios
    (5 de 11 en la comparación que está en design.md).
  - No informa del equipaje en la respuesta; solo se puede pedir en la
    consulta.
  - No devuelve enlace de reserva; se construye apuntando a la búsqueda.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from vuelos.modelos import Filtros

from .base import (
    Consulta,
    ConsultaVentana,
    ErrorProveedor,
    LimiteDePeticiones,
    Proveedor,
    Resultado,
)

log = logging.getLogger(__name__)

URL = "https://www.google.com/travel/flights"
NOMBRE = "google"

#: Franja horaria -> (hora mínima, hora máxima) de salida.
FRANJAS = {"manana": (5, 11), "tarde": (12, 18), "noche": (19, 4)}

Transporte = Callable[[dict[str, str]], str]


def _transporte_real(params: dict[str, str]) -> str:
    from primp import Client

    cliente = Client(
        impersonate="chrome_145", impersonate_os="macos", referer=True, cookie_store=True
    )
    respuesta = cliente.get(URL, params=params)
    if respuesta.status_code == 429:
        raise LimiteDePeticiones("Google devolvió 429")
    if respuesta.status_code >= 400:
        raise ErrorProveedor(f"Google devolvió {respuesta.status_code}")
    return respuesta.text


class AdaptadorGoogle(Proveedor):
    """Google Flights, con el mercado fijado explícitamente."""

    nombre = NOMBRE

    def __init__(self, transporte: Transporte | None = None) -> None:
        self._transporte = transporte or _transporte_real

    # ------------------------------------------------------------- consultas

    def _construir(self, consulta: Consulta):
        """Devuelve (query de fast-flights, parámetros con `gl` inyectado)."""
        from fast_flights import FlightQuery, Passengers, create_query

        f = consulta.filtros
        horas: dict = {}
        if f.franja_horaria:
            desde, hasta = FRANJAS[str(f.franja_horaria)]
            horas = {"earliest_departure_hour": desde, "latest_departure_hour": hasta}

        tramo = dict(
            max_stops=f.max_escalas,
            airlines=list(f.aerolineas) or None,
            max_layover_minutes=f.max_escala_minutos,
            **horas,
        )
        query = create_query(
            flights=[
                FlightQuery(date=consulta.salida.isoformat(), from_airport=consulta.origen,
                            to_airport=consulta.destino, **tramo),
                FlightQuery(date=consulta.regreso.isoformat(), from_airport=consulta.destino,
                            to_airport=consulta.origen, **tramo),
            ],
            trip="round-trip",
            seat="economy",
            passengers=Passengers(adults=1),
            currency=consulta.moneda,
            language="es",
            # El equipaje no se puede leer de la respuesta; solo pedirlo aquí.
            checked_bags=1 if f.requiere_maleta else 0,
        )
        # Aquí está el motivo de no usar get_flights: añadir el mercado.
        params = dict(query.params()) | {"gl": consulta.mercado}
        return query, params

    def enlace(self, consulta: Consulta) -> str:
        """Enlace de verificación (tarea 4.9).

        La fuente no da enlace de reserva, así que se apunta a la búsqueda
        equivalente en Google Flights, que es donde el usuario comprobaría el
        precio de todos modos.
        """
        query, _ = self._construir(consulta)
        return f"{query.url()}&gl={consulta.mercado}"

    def buscar(self, consulta: Consulta) -> list[Resultado]:
        from fast_flights.parser import parse

        query, params = self._construir(consulta)
        html = self._transporte(params)
        try:
            crudos = parse(html)
        except Exception as exc:
            raise ErrorProveedor(f"no se pudo analizar la respuesta de Google: {exc}") from exc

        enlace = f"{query.url()}&gl={consulta.mercado}"
        resultados = [
            r for r in (self._a_resultado(c, consulta, enlace) for c in crudos) if r is not None
        ]
        log.info(
            "google %s->%s %s/%s: %d itinerarios (mercado %s, %s)",
            consulta.origen, consulta.destino, consulta.salida, consulta.regreso,
            len(resultados), consulta.mercado, consulta.moneda,
        )
        return resultados

    def buscar_ventana(self, consulta: ConsultaVentana) -> list[Resultado]:
        """Bloque a bloque: la fuente no admite rangos de fechas.

        Se consultan los dos regresos posibles por cada salida y se quedan
        solo los que dan las noches en destino pedidas. Esa comprobación no se
        puede hacer antes de preguntar, porque depende de la hora de llegada.
        """
        resultados: list[Resultado] = []
        descartados = 0
        for salida, regreso in consulta.bloques():
            bloque = Consulta(
                origen=consulta.origen, destino=consulta.destino, salida=salida,
                regreso=regreso, mercado=consulta.mercado, moneda=consulta.moneda,
                filtros=consulta.filtros,
            )
            try:
                for r in self.buscar(bloque):
                    if r.dura(consulta.duracion_noches):
                        resultados.append(r)
                    else:
                        descartados += 1
            except ErrorProveedor as exc:
                log.warning("bloque %s/%s fallido: %s", salida, regreso, exc)
        if descartados:
            log.info(
                "google ventana: %d itinerarios descartados por no dar %d noches en destino",
                descartados, consulta.duracion_noches,
            )
        return resultados

    def peticiones_por_ventana(self, consulta: ConsultaVentana) -> int:
        return len(consulta.bloques())

    # ---------------------------------------------------------------- mapeo

    def _a_resultado(self, crudo, consulta: Consulta, enlace: str) -> Resultado | None:
        precio = getattr(crudo, "price", None)
        if not isinstance(precio, int | float):
            return None  # Google marca algunas filas sin precio numérico.

        segmentos = getattr(crudo, "flights", []) or []

        # Sin etiquetas de equipaje ni de billete separado: esta fuente no
        # informa de ninguna de las dos en la respuesta. No se marca
        # `sin_equipaje_facturado` porque no consta que falte, solo que se
        # desconoce; afirmarlo sería inventarse un dato.
        # Los segmentos que trae el resultado son solo los de la ida, asi que
        # el ultimo marca la llegada a destino.
        llegada = None
        if segmentos:
            crudo_llegada = getattr(segmentos[-1], "arrival", None)
            fecha = getattr(crudo_llegada, "date", None)
            if isinstance(fecha, tuple) and len(fecha) == 3:
                llegada = date(*fecha)

        return Resultado(
            salida=consulta.salida,
            regreso=consulta.regreso,
            llegada_ida=llegada,
            precio=float(precio),
            moneda=consulta.moneda,
            # La respuesta no confirma el mercado aplicado; se registra el que
            # se pidió. La validación real está en quien registra el precio.
            mercado=consulta.mercado,
            escalas=max(len(segmentos) - 1, 0),
            aerolineas=tuple(getattr(crudo, "airlines", ()) or ()),
            enlace=enlace,
        )


def consulta_de_control(mercado: str, moneda: str, hoy: date | None = None) -> Consulta:
    """Consulta fija y conocida para comprobar que la fuente sigue viva."""
    from datetime import timedelta

    hoy = hoy or date.today()
    return Consulta(
        origen="BOG", destino="MDE",
        salida=hoy + timedelta(days=30), regreso=hoy + timedelta(days=37),
        mercado=mercado, moneda=moneda, filtros=Filtros(),
    )
