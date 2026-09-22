"""Convierte lo que devuelve una fuente en precios registrables.

Es el punto donde se decide qué entra en el histórico y qué no. Tres reglas,
y las tres existen para que una alerta nunca se dispare por un precio que el
usuario no podría pagar:

1. Un precio obtenido bajo un mercado distinto del configurado se descarta.
2. Un resultado que incumple los filtros duros de la búsqueda se descarta
   antes de entrar en la serie, no después.
3. Un precio en otra moneda se convierte, conservando el importe original y
   el cambio aplicado; si no hay tipo de cambio, se descarta en vez de
   estimarlo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from vuelos.modelos import Filtros, Precio
from vuelos.proveedores.base import Resultado
from vuelos.proveedores.cambio import FuenteDeCambio, SinTipoDeCambio, convertir

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Descartado:
    """Un resultado que no entra en el histórico, y por qué."""

    resultado: Resultado
    motivo: str


@dataclass(frozen=True)
class Ingesta:
    aceptados: list[Precio]
    descartados: list[Descartado]

    @property
    def hubo_resultados(self) -> bool:
        """Si la fuente devolvió algo utilizable.

        Se distingue de "no devolvió nada": una fuente que responde con
        resultados que se descartan por filtros no está caída.
        """
        return bool(self.aceptados)


def preparar(
    resultados: list[Resultado],
    *,
    busqueda_id: int,
    fuente: str,
    mercado: str,
    moneda_ref: str,
    filtros: Filtros,
    tipo_de_cambio: FuenteDeCambio | None = None,
) -> Ingesta:
    """Filtra, valida y convierte resultados en precios listos para guardar."""
    aceptados: list[Precio] = []
    descartados: list[Descartado] = []

    for r in resultados:
        if r.mercado.upper() != mercado.upper():
            descartados.append(Descartado(r, f"mercado {r.mercado}, se esperaba {mercado}"))
            continue

        if not r.cumple(filtros):
            descartados.append(Descartado(r, "incumple los filtros de la búsqueda"))
            continue

        try:
            convertido = convertir(r.precio, r.moneda, moneda_ref, tipo_de_cambio)
        except SinTipoDeCambio as exc:
            descartados.append(Descartado(r, str(exc)))
            continue

        aceptados.append(
            Precio(
                busqueda_id=busqueda_id, fuente=fuente,
                salida=r.salida, regreso=r.regreso,
                precio=r.precio, moneda=r.moneda.upper(),
                precio_ref=convertido.importe, moneda_ref=convertido.moneda,
                cambio_aplicado=convertido.cambio_aplicado,
                mercado=r.mercado.upper(), escalas=r.escalas,
                aerolineas=list(r.aerolineas), etiquetas=r.etiquetas,
                enlace=r.enlace, obtenido_en=r.obtenido_en,
            )
        )

    if descartados:
        log.info(
            "%s busqueda %d: %d aceptados, %d descartados (%s)",
            fuente, busqueda_id, len(aceptados), len(descartados),
            "; ".join(sorted({d.motivo for d in descartados})),
        )
    return Ingesta(aceptados=aceptados, descartados=descartados)
