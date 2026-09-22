"""Adaptador de Kiwi sobre su GraphQL público.

El extremo responde sin credenciales ni proxy, y acepta `market`, `currency`
y `locale`, así que el punto de venta se fija de forma explícita y sin rodeos.

A diferencia de Google, esta fuente sí informa en la respuesta del equipaje
incluido y de si el itinerario son billetes separados, que es lo que permite
etiquetar los resultados en vez de suponerlos.

Resuelve la ventana flexible de forma nativa: `outboundDepartureDate` admite
un rango y `nightsCount` un rango de noches, así que toda la ventana cuesta
una sola petición.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from vuelos.modelos import Etiqueta, Filtros

from .base import (
    Consulta,
    ConsultaVentana,
    ErrorProveedor,
    LimiteDePeticiones,
    MercadoIncorrecto,
    Proveedor,
    Resultado,
)

log = logging.getLogger(__name__)

URL = "https://api.skypicker.com/umbrella/v2/graphql"
#: `bookingUrl` llega como ruta relativa (/es/booking/?...&token=...), no como
#: enlace absoluto: hay que componerlo o no sirve para abrirlo desde Telegram.
BASE_RESERVA = "https://www.kiwi.com"
NOMBRE = "kiwi"
CONSULTA = Path(__file__).parent / "consulta_kiwi.graphql"

#: Franja horaria -> (hora mínima, hora máxima) de salida.
FRANJAS = {"manana": (5, 11), "tarde": (12, 18), "noche": (19, 23)}

Transporte = Callable[[dict], dict]


def _transporte_real(cuerpo: dict) -> dict:
    peticion = urllib.request.Request(
        URL, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=120) as respuesta:
            return json.loads(respuesta.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise LimiteDePeticiones("Kiwi devolvió 429") from exc
        raise ErrorProveedor(f"Kiwi devolvió {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ErrorProveedor(f"no se pudo contactar con Kiwi: {exc.reason}") from exc


def _absoluto(ruta: str | None) -> str | None:
    """Convierte la ruta relativa de reserva en un enlace abrible."""
    if not ruta:
        return None
    if ruta.startswith(("http://", "https://")):
        return ruta
    return f"{BASE_RESERVA}/{ruta.lstrip('/')}"


class AdaptadorKiwi(Proveedor):
    """Kiwi, con mercado y moneda fijados."""

    nombre = NOMBRE

    def __init__(self, transporte: Transporte | None = None) -> None:
        self._transporte = transporte or _transporte_real
        self._consulta_gql = CONSULTA.read_text(encoding="utf-8")

    # ------------------------------------------------------------- petición

    @staticmethod
    def _filtro(filtros: Filtros) -> dict:
        f: dict = {
            "limit": 20,
            # Se excluyen en origen las prácticas que pueden invalidar el
            # billete; el self-transfer se deja pasar pero se etiqueta.
            "enableThrowAwayTicketing": False,
            "enableTrueHiddenCity": False,
            "enableSelfTransfer": True,
        }
        if filtros.max_escalas is not None:
            f["maxStopsCount"] = filtros.max_escalas
        if filtros.max_escala_minutos is not None:
            f["stopoverTime"] = {"start": 0, "end": filtros.max_escala_minutos * 60}
        if filtros.requiere_maleta:
            f["showNoCheckedBags"] = False
        if filtros.aerolineas:
            f["carriers"] = list(filtros.aerolineas)
        if filtros.franja_horaria:
            desde, hasta = FRANJAS[str(filtros.franja_horaria)]
            f["outbound"] = {"departureTime": [{"start": f"{desde:02d}:00",
                                                "end": f"{hasta:02d}:59"}]}
        return f

    def _opciones(self, mercado: str, moneda: str) -> dict:
        return {
            "currency": moneda.lower(),
            "locale": "es",
            "market": mercado.lower(),
            "partner": "skypicker",
            "sortBy": "PRICE",
        }

    @staticmethod
    def _pasajeros(filtros: Filtros) -> dict:
        return {
            "adults": 1,
            "adultsHandBags": 1,
            "adultsHoldBags": 1 if filtros.requiere_maleta else 0,
        }

    def _pedir(self, variables: dict) -> list[dict]:
        datos = self._transporte({"query": self._consulta_gql, "variables": variables})
        if datos.get("errors"):
            mensajes = "; ".join(e.get("message", "?") for e in datos["errors"][:3])
            raise ErrorProveedor(f"Kiwi rechazó la consulta: {mensajes}")
        nodo = (datos.get("data") or {}).get("returnItineraries") or {}
        if nodo.get("__typename") not in (None, "Itineraries"):
            raise ErrorProveedor(f"Kiwi respondió {nodo.get('__typename')}")
        return nodo.get("itineraries") or []

    # ------------------------------------------------------------ búsquedas

    def buscar(self, consulta: Consulta) -> list[Resultado]:
        variables = {
            "search": {
                "itinerary": {
                    "source": {"ids": [f"Station:airport:{consulta.origen}"]},
                    "destination": {"ids": [f"Station:airport:{consulta.destino}"]},
                    "outboundDepartureDate": {
                        "start": f"{consulta.salida}T00:00:00",
                        "end": f"{consulta.salida}T23:59:59",
                    },
                    "inboundDepartureDate": {
                        "start": f"{consulta.regreso}T00:00:00",
                        "end": f"{consulta.regreso}T23:59:59",
                    },
                },
                "passengers": self._pasajeros(consulta.filtros),
                "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
            },
            "filter": self._filtro(consulta.filtros),
            "options": self._opciones(consulta.mercado, consulta.moneda),
        }
        crudos = self._pedir(variables)
        resultados = [
            r for r in (self._a_resultado(c, consulta.mercado, consulta.moneda,
                                          consulta.salida, consulta.regreso) for c in crudos)
            if r is not None
        ]
        log.info(
            "kiwi %s->%s %s/%s: %d itinerarios (mercado %s, %s)",
            consulta.origen, consulta.destino, consulta.salida, consulta.regreso,
            len(resultados), consulta.mercado, consulta.moneda,
        )
        return resultados

    def buscar_ventana(self, consulta: ConsultaVentana) -> list[Resultado]:
        """Toda la ventana en una petición, con `nightsCount`."""
        variables = {
            "search": {
                "itinerary": {
                    "source": {"ids": [f"Station:airport:{consulta.origen}"]},
                    "destination": {"ids": [f"Station:airport:{consulta.destino}"]},
                    "outboundDepartureDate": {
                        "start": f"{consulta.ventana_ini}T00:00:00",
                        "end": f"{consulta.ventana_fin}T23:59:59",
                    },
                    "nightsCount": {
                        "start": consulta.duracion_noches,
                        "end": consulta.duracion_noches,
                    },
                },
                "passengers": self._pasajeros(consulta.filtros),
                "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
            },
            "filter": self._filtro(consulta.filtros),
            "options": self._opciones(consulta.mercado, consulta.moneda),
        }
        crudos = self._pedir(variables)
        resultados = [
            r for r in (self._a_resultado(c, consulta.mercado, consulta.moneda)
                        for c in crudos)
            if r is not None
        ]
        log.info(
            "kiwi ventana %s->%s %s..%s (%d noches): %d itinerarios en 1 petición",
            consulta.origen, consulta.destino, consulta.ventana_ini, consulta.ventana_fin,
            consulta.duracion_noches, len(resultados),
        )
        return resultados

    def peticiones_por_ventana(self, consulta: ConsultaVentana) -> int:
        return 1

    # ---------------------------------------------------------------- mapeo

    @staticmethod
    def _fecha_de(sector: dict | None) -> date | None:
        tramos = (sector or {}).get("sectorSegments") or []
        if not tramos:
            return None
        crudo = (((tramos[0] or {}).get("segment") or {}).get("source") or {}).get("localTime")
        if not crudo:
            return None
        return datetime.fromisoformat(crudo.replace("Z", "+00:00")).date()

    def _a_resultado(
        self, crudo: dict, mercado: str, moneda: str,
        salida: date | None = None, regreso: date | None = None,
    ) -> Resultado | None:
        precio = (crudo.get("price") or {}).get("amount")
        devuelta = ((crudo.get("price") or {}).get("currency") or {}).get("code")
        if precio is None:
            return None
        if devuelta and devuelta.upper() != moneda.upper():
            raise MercadoIncorrecto(
                f"Kiwi devolvió {devuelta} habiendo pedido {moneda}: el precio no es "
                "comparable con la serie y se descarta"
            )

        ida = self._fecha_de(crudo.get("outbound")) or salida
        vuelta = self._fecha_de(crudo.get("inbound")) or regreso
        if ida is None or vuelta is None:
            return None

        bolsas = crudo.get("bagsInfo") or {}
        truco = crudo.get("travelHack") or {}
        etiquetas: set[Etiqueta] = set()
        if truco.get("isVirtualInterlining"):
            etiquetas.add(Etiqueta.BILLETES_SEPARADOS)
        if truco.get("isTrueHiddenCity"):
            etiquetas.add(Etiqueta.CIUDAD_OCULTA)
        if truco.get("isThrowawayTicket"):
            etiquetas.add(Etiqueta.BILLETE_DESECHADO)
        if not (bolsas.get("includedCheckedBags") or 0):
            etiquetas.add(Etiqueta.SIN_EQUIPAJE_FACTURADO)

        tramos = (crudo.get("outbound") or {}).get("sectorSegments") or []
        aerolineas = tuple(
            dict.fromkeys(
                ((t.get("segment") or {}).get("carrier") or {}).get("name")
                for t in tramos
                if ((t.get("segment") or {}).get("carrier") or {}).get("name")
            )
        )

        enlaces = ((crudo.get("bookingOptions") or {}).get("edges")) or []
        ruta = ((enlaces[0] or {}).get("node") or {}).get("bookingUrl") if enlaces else None
        enlace = _absoluto(ruta)

        return Resultado(
            salida=ida, regreso=vuelta, precio=float(precio),
            moneda=(devuelta or moneda).upper(), mercado=mercado,
            escalas=max(len(tramos) - 1, 0), aerolineas=aerolineas,
            etiquetas=frozenset(etiquetas), enlace=enlace,
        )


def consulta_de_control(mercado: str, moneda: str, hoy: date | None = None) -> Consulta:
    """Consulta fija y conocida para comprobar que la fuente sigue viva."""
    hoy = hoy or date.today()
    return Consulta(
        origen="BOG", destino="MDE",
        salida=hoy + timedelta(days=30), regreso=hoy + timedelta(days=37),
        mercado=mercado, moneda=moneda, filtros=Filtros(),
    )
