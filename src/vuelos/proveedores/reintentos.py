"""Reintentos con esperas crecientes.

Cuando una fuente pide bajar el ritmo, insistir al mismo ritmo es la forma
más rápida de que deje de responder del todo. Las esperas crecen, y se les
añade una fracción aleatoria para que varias búsquedas que fallan a la vez no
vuelvan a la vez.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from .base import ErrorProveedor, LimiteDePeticiones

log = logging.getLogger(__name__)

T = TypeVar("T")

INTENTOS = 3
ESPERA_BASE_SEGUNDOS = 2.0
FACTOR = 3.0


def con_reintentos(
    operacion: Callable[[], T],
    *,
    intentos: int = INTENTOS,
    espera_base: float = ESPERA_BASE_SEGUNDOS,
    factor: float = FACTOR,
    dormir: Callable[[float], None] = time.sleep,
    aleatorio: Callable[[], float] = random.random,
) -> T:
    """Ejecuta `operacion`, reintentando los errores de la fuente.

    `dormir` y `aleatorio` se inyectan para que las pruebas no esperen de
    verdad ni dependan del azar.
    """
    ultimo: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            return operacion()
        except LimiteDePeticiones as exc:
            ultimo = exc
            espera = espera_base * (factor ** (intento - 1)) * (2 + aleatorio())
        except ErrorProveedor as exc:
            ultimo = exc
            espera = espera_base * (factor ** (intento - 1)) * (1 + aleatorio())

        if intento == intentos:
            break
        log.warning(
            "intento %d/%d fallido (%s); esperando %.1f s",
            intento, intentos, type(ultimo).__name__, espera,
        )
        dormir(espera)

    assert ultimo is not None
    raise ultimo
