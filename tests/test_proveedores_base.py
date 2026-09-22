"""Pruebas del contrato de proveedores."""

from __future__ import annotations

from datetime import date

import pytest

from vuelos.modelos import Etiqueta, Filtros
from vuelos.proveedores.base import Consulta, ConsultaVentana, Resultado
from vuelos.proveedores.simulado import ProveedorSimulado


def _resultado(precio=631.0, **kw) -> Resultado:
    base = dict(salida=date(2026, 11, 20), regreso=date(2026, 12, 4), precio=precio,
                moneda="USD", mercado="CO", escalas=1, aerolineas=("Delta",),
                enlace="https://ejemplo/x")
    return Resultado(**{**base, **kw})


# ------------------------------------------------------------------- bloques

def test_por_cada_salida_se_consultan_los_dos_regresos_posibles():
    """La duracion son noches en destino, y la llegada depende del vuelo.

    Un vuelo diurno que sale el 20 llega el 20 y vuelve el 1; uno nocturno
    que sale el 20 llega el 21 y vuelve el 2. Ambos son 12 noches alli, y no
    se sabe cual aplica hasta preguntar.
    """
    c = ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 16),
                        duracion_noches=12, mercado="CO", moneda="USD")
    assert c.dias_de_ventana == 27
    bloques = c.bloques()
    assert bloques[0] == (date(2027, 1, 20), date(2027, 2, 1))   # llega el mismo dia
    assert bloques[1] == (date(2027, 1, 20), date(2027, 2, 2))   # llega al dia siguiente
    assert len({salida for salida, _ in bloques}) == 16          # 16 fechas de salida
    assert len(bloques) == 31                                    # menos de 32: el ultimo no cabe


def test_ningun_bloque_se_sale_de_la_ventana():
    c = ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 1), ventana_fin=date(2027, 1, 10),
                        duracion_noches=3, mercado="CO", moneda="USD")
    for salida, regreso in c.bloques():
        assert salida >= c.ventana_ini
        assert regreso <= c.ventana_fin
        assert (regreso - salida).days in (3, 4)


def test_no_se_repiten_pares():
    c = ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 1), ventana_fin=date(2027, 1, 20),
                        duracion_noches=1, mercado="CO", moneda="USD")
    bloques = c.bloques()
    assert len(bloques) == len(set(bloques))


def test_noches_en_destino_con_vuelo_nocturno():
    """El caso que motivo todo esto, medido contra Kiwi el 21-sep-2026."""
    nocturno = _resultado(salida=date(2026, 11, 17), llegada_ida=date(2026, 11, 18),
                          regreso=date(2026, 11, 23))
    assert (nocturno.regreso - nocturno.salida).days == 6   # entre despegues
    assert nocturno.noches_en_destino == 5                  # en destino
    assert nocturno.dura(5)
    assert not nocturno.dura(6)


def test_noches_en_destino_con_vuelo_diurno():
    diurno = _resultado(salida=date(2026, 11, 18), llegada_ida=date(2026, 11, 18),
                        regreso=date(2026, 11, 23))
    assert diurno.noches_en_destino == 5
    assert diurno.dura(5)


def test_sin_fecha_de_llegada_no_se_descarta():
    """Falta el dato, no consta que incumpla: tirarlo seria perder un precio bueno."""
    sin_dato = _resultado(llegada_ida=None)
    assert sin_dato.noches_en_destino is None
    assert sin_dato.dura(5) and sin_dato.dura(99)


def test_duracion_que_no_cabe():
    with pytest.raises(ValueError, match="no cabe"):
        ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 1, 25),
                        duracion_noches=12, mercado="CO", moneda="USD")


def test_regreso_antes_que_salida():
    with pytest.raises(ValueError, match="anterior a la salida"):
        Consulta(origen="BOG", destino="RDU", salida=date(2026, 12, 4),
                 regreso=date(2026, 11, 20), mercado="CO", moneda="USD")


# ----------------------------------------------------------------- resultado

def test_sin_enlace_se_marca_no_verificable():
    r = _resultado(enlace=None)
    assert Etiqueta.NO_VERIFICABLE in r.etiquetas


def test_con_enlace_no_se_marca():
    assert Etiqueta.NO_VERIFICABLE not in _resultado().etiquetas


# ------------------------------------------------------------- filtros duros

def test_filtro_de_escalas():
    r = _resultado(escalas=2)
    assert r.cumple(Filtros(max_escalas=2))
    assert not r.cumple(Filtros(max_escalas=1))


def test_filtro_de_maleta():
    sin_maleta = _resultado(etiquetas={Etiqueta.SIN_EQUIPAJE_FACTURADO})
    assert not sin_maleta.cumple(Filtros(requiere_maleta=True))
    assert sin_maleta.cumple(Filtros(requiere_maleta=False))


def test_filtro_de_aerolineas():
    r = _resultado(aerolineas=("Avianca", "COPA"))
    assert r.cumple(Filtros(aerolineas=("AVIANCA",)))
    assert not r.cumple(Filtros(aerolineas=("LATAM",)))


def test_sin_filtros_todo_cumple():
    assert _resultado(escalas=5, etiquetas={Etiqueta.SIN_EQUIPAJE_FACTURADO}).cumple(Filtros())


# ---------------------------------------------- coste de resolver la ventana

def test_proveedor_con_ventana_nativa_gasta_una_peticion():
    """Kiwi: outboundDepartureDate como rango mas nightsCount."""
    p = ProveedorSimulado(respuestas=[_resultado()], ventana_nativa=True)
    c = ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 16),
                        duracion_noches=12, mercado="CO", moneda="USD")
    assert p.peticiones_por_ventana(c) == 1
    p.buscar_ventana(c)
    assert p.peticiones == 1


def test_proveedor_sin_ventana_nativa_gasta_una_por_bloque():
    """Google Flights: hay que preguntar par de fechas a par de fechas."""
    p = ProveedorSimulado(respuestas=[_resultado()], ventana_nativa=False)
    c = ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 16),
                        duracion_noches=12, mercado="CO", moneda="USD")
    assert p.peticiones_por_ventana(c) == 31
    p.buscar_ventana(c)
    assert p.peticiones == 31


def test_la_ventana_devuelve_un_resultado_por_bloque():
    p = ProveedorSimulado(respuestas=[_resultado()], ventana_nativa=True)
    c = ConsultaVentana(origen="BOG", destino="RDU",
                        ventana_ini=date(2027, 1, 1), ventana_fin=date(2027, 1, 10),
                        duracion_noches=3, mercado="CO", moneda="USD")
    resultados = p.buscar_ventana(c)
    assert len(resultados) == len(c.bloques())
    assert {(r.salida, r.regreso) for r in resultados} == set(c.bloques())
