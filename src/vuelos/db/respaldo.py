"""Copia de seguridad de la base de datos.

El histórico de precios es el activo del sistema y no se puede reconstruir: si
se pierde, se pierden meses de observaciones. Se usa la API de respaldo de
SQLite en vez de copiar el fichero, porque con WAL activo una copia a mano
puede capturar un estado incoherente mientras hay escrituras en curso.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

COPIAS_CONSERVADAS = 7


def _nombre_libre(destino: Path, ahora: datetime) -> Path:
    """Elige un nombre que no exista todavía.

    Derivar el nombre solo del reloj no basta: dos respaldos dentro de la misma
    unidad de tiempo comparten nombre y el segundo pisa al primero en silencio.
    Subir la resolución solo mueve el problema, así que se comprueba y se añade
    un discriminante cuando hace falta.
    """
    base = f"vuelos-{ahora:%Y%m%d-%H%M%S}"
    fichero = destino / f"{base}.db"
    secuencia = 1
    while fichero.exists():
        fichero = destino / f"{base}-{secuencia:03d}.db"
        secuencia += 1
    return fichero


def respaldar(con: sqlite3.Connection, destino: Path,
              copias_conservadas: int = COPIAS_CONSERVADAS) -> Path:
    """Copia la base a `destino` y descarta las copias más antiguas."""
    destino.mkdir(parents=True, exist_ok=True)
    fichero = _nombre_libre(destino, datetime.now(UTC))

    copia = sqlite3.connect(fichero)
    try:
        con.backup(copia)
    finally:
        copia.close()

    log.info("respaldo escrito en %s (%d bytes)", fichero, fichero.stat().st_size)
    _descartar_antiguas(destino, copias_conservadas)
    return fichero


def _descartar_antiguas(destino: Path, copias_conservadas: int) -> None:
    """Conserva las N más recientes.

    Se ordena por fecha de modificación, no por nombre: el discriminante de
    `_nombre_libre` rompe el orden alfabético, y el reloj del fichero es la
    verdad que nos interesa.
    """
    copias = sorted(destino.glob("vuelos-*.db"), key=lambda f: f.stat().st_mtime_ns, reverse=True)
    for sobrante in copias[copias_conservadas:]:
        sobrante.unlink(missing_ok=True)
        log.info("respaldo antiguo descartado: %s", sobrante.name)
