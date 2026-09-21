"""Persistencia en SQLite."""

from .conexion import abrir, aplicar_esquema

__all__ = ["abrir", "aplicar_esquema"]
