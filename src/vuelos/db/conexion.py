"""Apertura de la base de datos y aplicación del esquema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ESQUEMA = Path(__file__).parent / "esquema.sql"


def abrir(ruta: Path) -> sqlite3.Connection:
    """Abre la base, la crea si no existe y deja el esquema aplicado.

    WAL permite que el sondeo escriba mientras el bot lee, que es justo lo que
    pasa cuando llega un mensaje durante un sondeo.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    aplicar_esquema(con)
    return con


def aplicar_esquema(con: sqlite3.Connection) -> None:
    """Aplica el esquema. Es idempotente: se puede llamar en cada arranque."""
    con.executescript(ESQUEMA.read_text(encoding="utf-8"))
