"""Pruebas de persistencia."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from vuelos.db.conexion import abrir
from vuelos.db.repositorio import Repositorio
from vuelos.modelos import (
    Busqueda,
    Estado,
    Etiqueta,
    Filtros,
    Franja,
    Modo,
    Motivo,
    Precio,
)


@pytest.fixture
def repo(tmp_path):
    return Repositorio(abrir(tmp_path / "prueba.db"))


def _busqueda_a(**kw) -> Busqueda:
    base = dict(chat_id=111, origen="BOG", destino="RDU", modo=Modo.EXACTAS,
                salida=date(2026, 11, 20), regreso=date(2026, 12, 4))
    return Busqueda(**{**base, **kw})


def _precio(busqueda_id: int, fuente: str, importe: float, **kw) -> Precio:
    base = dict(busqueda_id=busqueda_id, fuente=fuente, salida=date(2026, 11, 20),
                regreso=date(2026, 12, 4), precio=importe, moneda="USD",
                precio_ref=importe, moneda_ref="USD", mercado="CO")
    return Precio(**{**base, **kw})


# --------------------------------------------------------------------- esquema

def test_wal_activo(repo):
    modo = repo.con.execute("PRAGMA journal_mode").fetchone()[0]
    assert modo.lower() == "wal"


def test_indices_creados(repo):
    nombres = {f["name"] for f in repo.con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_precios_serie", "idx_precios_bloque", "idx_precios_minimo",
            "idx_notificaciones_serie", "idx_busquedas_activas"} <= nombres


def test_la_serie_se_lee_por_indice(repo):
    plan = repo.con.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM precios WHERE busqueda_id = 1 AND fuente = 'google' "
        "ORDER BY obtenido_en DESC"
    ).fetchall()
    assert any("idx_precios_serie" in str(fila["detail"]) for fila in plan), plan


# ------------------------------------------------------------------- búsquedas

def test_alta_y_lectura(repo):
    b = repo.crear_busqueda(_busqueda_a())
    assert b.id is not None
    leida = repo.obtener_busqueda(b.id)
    assert leida.origen == "BOG" and leida.destino == "RDU"
    assert leida.modo is Modo.EXACTAS
    assert leida.estado is Estado.ACTIVA


def test_modo_ventana(repo):
    b = repo.crear_busqueda(Busqueda(
        chat_id=111, origen="BOG", destino="RDU", modo=Modo.VENTANA,
        ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 15), duracion_noches=12))
    leida = repo.obtener_busqueda(b.id)
    assert leida.duracion_noches == 12
    assert leida.ventana_fin == date(2027, 2, 15)


def test_duracion_que_no_cabe_en_la_ventana(repo):
    with pytest.raises(ValueError, match="no cabe"):
        Busqueda(chat_id=1, origen="BOG", destino="RDU", modo=Modo.VENTANA,
                 ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 1, 25),
                 duracion_noches=12)


def test_modo_exactas_sin_fechas(repo):
    with pytest.raises(ValueError, match="exige salida y regreso"):
        Busqueda(chat_id=1, origen="BOG", destino="RDU", modo=Modo.EXACTAS)


def test_solo_las_activas_se_consultan(repo):
    a = repo.crear_busqueda(_busqueda_a())
    b = repo.crear_busqueda(_busqueda_a())
    c = repo.crear_busqueda(_busqueda_a())
    repo.cambiar_estado(b.id, Estado.PAUSADA, pausada_hasta=datetime.now(UTC) + timedelta(days=7))
    repo.cambiar_estado(c.id, Estado.TERMINADA)
    assert [x.id for x in repo.listar_activas()] == [a.id]


def test_contar_activas_por_chat(repo):
    for _ in range(3):
        repo.crear_busqueda(_busqueda_a())
    repo.crear_busqueda(_busqueda_a(chat_id=999))
    assert repo.contar_activas(111) == 3
    assert repo.contar_activas(999) == 1


def test_contador_de_fallos(repo):
    b = repo.crear_busqueda(_busqueda_a())
    assert repo.registrar_sondeo_fallido(b.id) == 1
    assert repo.registrar_sondeo_fallido(b.id) == 2
    repo.reiniciar_sondeos_fallidos(b.id)
    assert repo.obtener_busqueda(b.id).sondeos_fallidos == 0


# --------------------------------------------------------------------- precios

def test_series_independientes_por_fuente(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "google", 631))
    repo.registrar_precio(_precio(b.id, "kiwi", 818))
    assert repo.minimo_historico(b.id, "google").precio_ref == 631
    assert repo.minimo_historico(b.id, "kiwi").precio_ref == 818


def test_minimo_historico(repo):
    b = repo.crear_busqueda(_busqueda_a())
    for importe in (700, 631, 840):
        repo.registrar_precio(_precio(b.id, "google", importe))
    assert repo.minimo_historico(b.id, "google").precio_ref == 631
    assert repo.ultimo_precio(b.id, "google").precio_ref == 840


def test_etiquetas_y_aerolineas_van_y_vuelven(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(
        b.id, "kiwi", 818, escalas=2, aerolineas=["LATAM", "Delta"],
        etiquetas={Etiqueta.BILLETES_SEPARADOS, Etiqueta.SIN_EQUIPAJE_FACTURADO},
        enlace="https://ejemplo/reserva"))
    p = repo.ultimo_precio(b.id, "kiwi")
    assert p.escalas == 2
    assert p.aerolineas == ["LATAM", "Delta"]
    assert Etiqueta.BILLETES_SEPARADOS in p.etiquetas
    assert p.enlace == "https://ejemplo/reserva"


def test_conversion_conserva_original_y_cambio(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "google", 2148639.0, moneda="COP",
                                  precio_ref=680.0, cambio_aplicado=3159.76))
    p = repo.ultimo_precio(b.id, "google")
    assert p.precio == 2148639.0 and p.moneda == "COP"
    assert p.precio_ref == 680.0 and p.moneda_ref == "USD"
    assert p.cambio_aplicado == pytest.approx(3159.76)


def test_mejores_bloques(repo):
    b = repo.crear_busqueda(_busqueda_a())
    bloques = [(date(2027, 1, 20), date(2027, 2, 1), 900),
               (date(2027, 1, 22), date(2027, 2, 3), 700),
               (date(2027, 1, 25), date(2027, 2, 6), 800)]
    for salida, regreso, importe in bloques:
        repo.registrar_precio(_precio(b.id, "kiwi", importe, salida=salida, regreso=regreso))
    mejores = repo.mejor_bloque(b.id, "kiwi", limite=2)
    assert mejores[0] == (date(2027, 1, 22), date(2027, 2, 3))
    assert len(mejores) == 2


# -------------------------------------------------------------- notificaciones

def test_el_umbral_se_mide_contra_lo_notificado_no_contra_lo_registrado(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "google", 700))
    repo.registrar_notificacion(b.id, "google", 700, "USD", Motivo.REFERENCIA_INICIAL)
    # Baja poco varias veces: se registra, pero no se notifica.
    for importe in (695, 690, 688):
        repo.registrar_precio(_precio(b.id, "google", importe))
    assert repo.ultimo_precio_notificado(b.id, "google") == 700
    assert repo.minimo_historico(b.id, "google").precio_ref == 688


def test_notificado_por_fuente(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_notificacion(b.id, "google", 631, "USD", Motivo.REFERENCIA_INICIAL)
    assert repo.ultimo_precio_notificado(b.id, "google") == 631
    assert repo.ultimo_precio_notificado(b.id, "kiwi") is None


def test_el_cierre_no_cuenta_como_referencia_de_umbral(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_notificacion(b.id, "google", 631, "USD", Motivo.BAJADA)
    repo.registrar_notificacion(b.id, "google", 999, "USD", Motivo.CIERRE)
    assert repo.ultimo_precio_notificado(b.id, "google") == 631


# ------------------------------------------------------- conservación y borrado

def test_terminar_conserva_el_historico(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "google", 631))
    repo.cambiar_estado(b.id, Estado.TERMINADA)
    assert repo.obtener_busqueda(b.id).estado is Estado.TERMINADA
    assert repo.minimo_historico(b.id, "google").precio_ref == 631


def test_borrar_elimina_tambien_los_precios(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "google", 631))
    repo.registrar_notificacion(b.id, "google", 631, "USD", Motivo.BAJADA)
    repo.borrar_busqueda(b.id)
    assert repo.obtener_busqueda(b.id) is None
    assert repo.con.execute("SELECT COUNT(*) FROM precios").fetchone()[0] == 0
    assert repo.con.execute("SELECT COUNT(*) FROM notificaciones").fetchone()[0] == 0


# ------------------------------------------------------------- estado fuentes

def test_cambio_de_estado_de_fuente(repo):
    assert repo.marcar_fuente("google", operativa=True) is False   # primera vez, no es cambio
    assert repo.marcar_fuente("google", operativa=True) is False   # sigue igual
    assert repo.marcar_fuente("google", operativa=False) is True   # cae: sí es cambio
    assert repo.fuentes_caidas() == ["google"]
    assert repo.marcar_fuente("google", operativa=True) is True    # se restablece
    assert repo.fuentes_caidas() == []


# ------------------------------------------------- filtros en columnas propias

def test_filtros_se_guardan_en_columnas(repo):
    b = repo.crear_busqueda(_busqueda_a(filtros=Filtros(
        max_escalas=1, max_escala_minutos=240, requiere_maleta=True,
        franja_horaria=Franja.MANANA, aerolineas=("AV", "CM"))))
    leida = repo.obtener_busqueda(b.id)
    assert leida.filtros.max_escalas == 1
    assert leida.filtros.max_escala_minutos == 240
    assert leida.filtros.requiere_maleta is True
    assert leida.filtros.franja_horaria is Franja.MANANA
    assert leida.filtros.aerolineas == ("AV", "CM")


def test_filtros_son_consultables_en_sql(repo):
    """El motivo de sacarlos de JSON: poder preguntarlo a la base."""
    repo.crear_busqueda(_busqueda_a(filtros=Filtros(requiere_maleta=True)))
    repo.crear_busqueda(_busqueda_a())
    n = repo.con.execute(
        "SELECT COUNT(*) FROM busquedas WHERE requiere_maleta = 1").fetchone()[0]
    assert n == 1


def test_la_base_rechaza_una_franja_inventada(repo):
    import sqlite3
    b = repo.crear_busqueda(_busqueda_a())
    with pytest.raises(sqlite3.IntegrityError):
        repo.con.execute(
            "UPDATE busquedas SET franja_horaria = 'madrugada' WHERE id = ?", (b.id,))


def test_las_aerolineas_se_borran_con_la_busqueda(repo):
    b = repo.crear_busqueda(_busqueda_a(filtros=Filtros(aerolineas=("AV", "CM"))))
    repo.borrar_busqueda(b.id)
    assert repo.con.execute("SELECT COUNT(*) FROM busqueda_aerolineas").fetchone()[0] == 0


# -------------------------------------------- etiquetas en columnas propias

def test_etiquetas_se_guardan_en_columnas(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "kiwi", 818,
                                  etiquetas={Etiqueta.BILLETES_SEPARADOS}))
    fila = repo.con.execute(
        "SELECT billetes_separados, sin_equipaje_facturado FROM precios").fetchone()
    assert fila["billetes_separados"] == 1
    assert fila["sin_equipaje_facturado"] == 0


def test_excluir_etiquetas_al_buscar_el_minimo(repo):
    """Lo que con JSON habria obligado a filtrar en Python."""
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "kiwi", 700,
                                  etiquetas={Etiqueta.BILLETES_SEPARADOS}))
    repo.registrar_precio(_precio(b.id, "kiwi", 850))
    assert repo.minimo_historico(b.id, "kiwi").precio_ref == 700
    solo_directos = repo.minimo_historico(
        b.id, "kiwi", excluir=[Etiqueta.BILLETES_SEPARADOS])
    assert solo_directos.precio_ref == 850


def test_excluir_etiquetas_en_los_mejores_bloques(repo):
    b = repo.crear_busqueda(_busqueda_a())
    repo.registrar_precio(_precio(b.id, "kiwi", 600, salida=date(2027, 1, 20),
                                  regreso=date(2027, 2, 1),
                                  etiquetas={Etiqueta.SIN_EQUIPAJE_FACTURADO}))
    repo.registrar_precio(_precio(b.id, "kiwi", 750, salida=date(2027, 1, 22),
                                  regreso=date(2027, 2, 3)))
    con_todo = repo.mejor_bloque(b.id, "kiwi", limite=1)
    assert con_todo[0] == (date(2027, 1, 20), date(2027, 2, 1))
    con_maleta = repo.mejor_bloque(b.id, "kiwi", limite=1,
                                   excluir=[Etiqueta.SIN_EQUIPAJE_FACTURADO])
    assert con_maleta[0] == (date(2027, 1, 22), date(2027, 2, 3))


# ------------------------------------------------- instantes siempre con zona

def test_pausar_sin_zona_horaria_se_rechaza(repo):
    b = repo.crear_busqueda(_busqueda_a())
    with pytest.raises(ValueError, match="sin zona horaria"):
        repo.cambiar_estado(b.id, Estado.PAUSADA,
                            pausada_hasta=datetime(2027, 1, 1, 12, 0))


def test_pausar_con_zona_se_normaliza_a_utc(repo):
    from zoneinfo import ZoneInfo
    b = repo.crear_busqueda(_busqueda_a())
    bogota = datetime(2027, 1, 1, 12, 0, tzinfo=ZoneInfo("America/Bogota"))
    repo.cambiar_estado(b.id, Estado.PAUSADA, pausada_hasta=bogota)
    guardado = repo.obtener_busqueda(b.id).pausada_hasta
    assert guardado.tzinfo is not None
    assert guardado == bogota                 # mismo instante
    assert guardado.hour == 17                # expresado en UTC


def test_comparar_lo_guardado_contra_ahora_no_revienta(repo):
    """El fallo que motivo el cambio: naive contra aware lanzaba TypeError."""
    b = repo.crear_busqueda(_busqueda_a())
    repo.cambiar_estado(b.id, Estado.PAUSADA,
                        pausada_hasta=datetime.now(UTC) + timedelta(days=7))
    hasta = repo.obtener_busqueda(b.id).pausada_hasta
    assert (hasta <= datetime.now(UTC)) is False


def test_un_precio_sin_zona_se_rechaza(repo):
    b = repo.crear_busqueda(_busqueda_a())
    with pytest.raises(ValueError, match="sin zona horaria"):
        _precio(b.id, "google", 631, obtenido_en=datetime(2026, 11, 20, 10, 0))
