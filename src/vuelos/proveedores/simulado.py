"""Proveedor simulado: sirve al contrato sin tocar la red.

Existe para que las pruebas del planificador, las alertas y el ciclo de vida
no dependan de que Google o Kiwi estén disponibles ni de qué precio tengan hoy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from .base import Consulta, ConsultaVentana, ErrorProveedor, Proveedor, Resultado


class ProveedorSimulado(Proveedor):
    """Devuelve lo que se le diga y cuenta las peticiones que recibe."""

    def __init__(
        self,
        nombre: str = "simulado",
        *,
        respuestas: Iterable[Resultado] | None = None,
        generador: Callable[[date, date], list[Resultado]] | None = None,
        ventana_nativa: bool = False,
        fallo: Exception | None = None,
    ) -> None:
        self.nombre = nombre
        self._respuestas = list(respuestas or [])
        self._generador = generador
        self._ventana_nativa = ventana_nativa
        self._fallo = fallo
        self.peticiones = 0

    def _responder(self, salida: date, regreso: date) -> list[Resultado]:
        self.peticiones += 1
        if self._fallo is not None:
            raise self._fallo
        if self._generador is not None:
            return self._generador(salida, regreso)
        return [
            Resultado(
                salida=salida, regreso=regreso, precio=r.precio, moneda=r.moneda,
                mercado=r.mercado, escalas=r.escalas, aerolineas=r.aerolineas,
                etiquetas=r.etiquetas, enlace=r.enlace,
            )
            for r in self._respuestas
        ]

    def buscar(self, consulta: Consulta) -> list[Resultado]:
        return self._responder(consulta.salida, consulta.regreso)

    def buscar_ventana(self, consulta: ConsultaVentana) -> list[Resultado]:
        if self._ventana_nativa:
            # Una sola peticion cubre toda la ventana, como hace Kiwi.
            self.peticiones += 1
            if self._fallo is not None:
                raise self._fallo
            resultados: list[Resultado] = []
            for salida, regreso in consulta.bloques():
                if self._generador is not None:
                    resultados.extend(self._generador(salida, regreso))
                else:
                    resultados.extend(
                        Resultado(salida=salida, regreso=regreso, precio=r.precio,
                                  moneda=r.moneda, mercado=r.mercado, escalas=r.escalas,
                                  aerolineas=r.aerolineas, etiquetas=r.etiquetas,
                                  enlace=r.enlace)
                        for r in self._respuestas
                    )
            return resultados

        resultados = []
        for salida, regreso in consulta.bloques():
            try:
                resultados.extend(self._responder(salida, regreso))
            except ErrorProveedor:
                continue
        return resultados

    def peticiones_por_ventana(self, consulta: ConsultaVentana) -> int:
        return 1 if self._ventana_nativa else len(consulta.bloques())
