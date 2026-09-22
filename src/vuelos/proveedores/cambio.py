"""Conversión a la moneda de referencia.

Las dos fuentes admiten fijar la moneda, así que en el camino normal no hay
nada que convertir y el cambio aplicado es 1. Esta pieza existe para el caso
en que alguna devuelva otra moneda: entonces hay que dejar constancia del
importe original y del cambio usado, para que una variación del tipo de
cambio no se confunda nunca con una bajada de tarifa.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

#: Devuelve cuántas unidades de `destino` vale una de `origen`.
FuenteDeCambio = Callable[[str, str], float]


class SinTipoDeCambio(Exception):
    """Hay que convertir y no hay de dónde sacar el tipo.

    Se falla en vez de inventar un tipo o de guardar el importe sin convertir:
    un precio mal convertido entraría en la serie y dispararía alertas falsas.
    """


@dataclass(frozen=True)
class Convertido:
    importe: float
    moneda: str
    cambio_aplicado: float


def convertir(
    importe: float, origen: str, destino: str, fuente: FuenteDeCambio | None = None
) -> Convertido:
    """Convierte `importe` a la moneda `destino`."""
    if origen.upper() == destino.upper():
        return Convertido(importe=importe, moneda=destino.upper(), cambio_aplicado=1.0)

    if fuente is None:
        raise SinTipoDeCambio(
            f"hay que convertir {origen} a {destino} y no hay fuente de tipos de cambio "
            "configurada; se descarta el precio en vez de estimarlo"
        )

    tipo = fuente(origen.upper(), destino.upper())
    if tipo <= 0:
        raise SinTipoDeCambio(f"tipo de cambio inválido para {origen}->{destino}: {tipo}")

    return Convertido(
        importe=round(importe * tipo, 2), moneda=destino.upper(), cambio_aplicado=tipo
    )
