"""Registro de eventos: consola más fichero rotado.

El fichero es lo que queda cuando el bot lleva semanas solo en el VPS, así que
rota por tamaño y conserva histórico suficiente para reconstruir qué pasó.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)-8s %(name)-28s %(message)s"
BYTES_POR_FICHERO = 5 * 1024 * 1024
FICHEROS_CONSERVADOS = 5


def configurar(ruta_logs: Path, nivel: int = logging.INFO) -> Path:
    """Deja el registro listo. Devuelve la ruta del fichero de log."""
    ruta_logs.mkdir(parents=True, exist_ok=True)
    fichero = ruta_logs / "vuelos.log"

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for anterior in list(raiz.handlers):
        raiz.removeHandler(anterior)

    formato = logging.Formatter(FORMATO)

    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    disco = RotatingFileHandler(
        fichero, maxBytes=BYTES_POR_FICHERO, backupCount=FICHEROS_CONSERVADOS, encoding="utf-8"
    )
    disco.setFormatter(formato)
    raiz.addHandler(disco)

    # Estas librerías son ruidosas en INFO y no aportan nada que necesitemos leer.
    for ruidosa in ("httpx", "httpcore", "apscheduler.executors", "telegram.ext"):
        logging.getLogger(ruidosa).setLevel(logging.WARNING)

    return fichero
