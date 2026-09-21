"""Pruebas de la copia de seguridad."""

from __future__ import annotations

from datetime import date

from vuelos.db.conexion import abrir
from vuelos.db.repositorio import Repositorio
from vuelos.db.respaldo import respaldar
from vuelos.modelos import Busqueda, Modo, Precio


def _con_datos(tmp_path):
    repo = Repositorio(abrir(tmp_path / "vuelos.db"))
    b = repo.crear_busqueda(Busqueda(
        chat_id=111, origen="BOG", destino="RDU", modo=Modo.EXACTAS,
        salida=date(2026, 11, 20), regreso=date(2026, 12, 4)))
    repo.registrar_precio(Precio(
        busqueda_id=b.id, fuente="google", salida=date(2026, 11, 20),
        regreso=date(2026, 12, 4), precio=631, moneda="USD",
        precio_ref=631, moneda_ref="USD", mercado="CO"))
    return repo


def test_la_copia_se_genera_y_se_puede_abrir(tmp_path):
    repo = _con_datos(tmp_path)
    fichero = respaldar(repo.con, tmp_path / "copias")

    assert fichero.exists() and fichero.stat().st_size > 0

    copia = Repositorio(abrir(fichero))
    assert copia.minimo_historico(1, "google").precio_ref == 631


def test_solo_se_conservan_las_ultimas(tmp_path):
    repo = _con_datos(tmp_path)
    destino = tmp_path / "copias"
    for _ in range(5):
        respaldar(repo.con, destino, copias_conservadas=3)
    assert len(list(destino.glob("vuelos-*.db"))) == 3


def test_la_copia_no_arrastra_escrituras_posteriores(tmp_path):
    repo = _con_datos(tmp_path)
    fichero = respaldar(repo.con, tmp_path / "copias")
    repo.registrar_precio(Precio(
        busqueda_id=1, fuente="google", salida=date(2026, 11, 20),
        regreso=date(2026, 12, 4), precio=500, moneda="USD",
        precio_ref=500, moneda_ref="USD", mercado="CO"))

    copia = Repositorio(abrir(fichero))
    assert copia.minimo_historico(1, "google").precio_ref == 631
    assert repo.minimo_historico(1, "google").precio_ref == 500


def test_copias_seguidas_no_se_pisan(tmp_path):
    """Dos respaldos en el mismo instante deben producir dos ficheros."""
    repo = _con_datos(tmp_path)
    destino = tmp_path / "copias"
    ficheros = {respaldar(repo.con, destino) for _ in range(5)}
    assert len(ficheros) == 5
    assert all(f.exists() for f in ficheros)
