"""Pruebas de qué entra en el histórico y qué no."""

from __future__ import annotations

from datetime import date

from vuelos.ingesta import preparar
from vuelos.modelos import Etiqueta, Filtros
from vuelos.proveedores.base import Resultado


def _resultado(**kw) -> Resultado:
    base = dict(salida=date(2026, 11, 20), regreso=date(2026, 12, 4), precio=631.0,
                moneda="USD", mercado="CO", escalas=1, aerolineas=("Delta",),
                enlace="https://ejemplo/x")
    return Resultado(**{**base, **kw})


def _preparar(resultados, **kw):
    argumentos = dict(busqueda_id=1, fuente="google", mercado="CO", moneda_ref="USD",
                      filtros=Filtros())
    return preparar(resultados, **{**argumentos, **kw})


# --------------------------------------------------------------- mercado

def test_un_precio_de_otro_mercado_no_entra():
    r = _preparar([_resultado(mercado="US")])
    assert r.aceptados == []
    assert "se esperaba CO" in r.descartados[0].motivo


def test_el_mercado_correcto_entra():
    r = _preparar([_resultado(mercado="CO")])
    assert len(r.aceptados) == 1
    assert r.aceptados[0].mercado == "CO"


def test_la_comparacion_de_mercado_no_distingue_mayusculas():
    assert len(_preparar([_resultado(mercado="co")]).aceptados) == 1


# --------------------------------------------------------- filtros duros

def test_un_resultado_que_incumple_no_entra_en_la_serie():
    """Si entrara, podria disparar una alerta por un vuelo que no sirve."""
    r = _preparar([_resultado(escalas=3)], filtros=Filtros(max_escalas=1))
    assert r.aceptados == []
    assert "incumple" in r.descartados[0].motivo


def test_el_filtro_de_maleta_descarta_los_que_no_la_llevan():
    sin = _resultado(etiquetas={Etiqueta.SIN_EQUIPAJE_FACTURADO})
    con = _resultado(precio=900.0)
    r = _preparar([sin, con], filtros=Filtros(requiere_maleta=True))
    assert [p.precio for p in r.aceptados] == [900.0]


def test_se_aceptan_y_descartan_a_la_vez():
    r = _preparar([_resultado(escalas=0), _resultado(escalas=4)],
                  filtros=Filtros(max_escalas=1))
    assert len(r.aceptados) == 1
    assert len(r.descartados) == 1


# ------------------------------------------------------------- conversion

def test_misma_moneda_no_convierte():
    p = _preparar([_resultado()]).aceptados[0]
    assert p.precio == p.precio_ref == 631.0
    assert p.cambio_aplicado == 1.0


def test_otra_moneda_se_convierte_conservando_el_original():
    r = _preparar([_resultado(precio=2148639.0, moneda="COP")],
                  tipo_de_cambio=lambda o, d: 1 / 3159.76)
    p = r.aceptados[0]
    assert p.precio == 2148639.0 and p.moneda == "COP"
    assert p.moneda_ref == "USD"
    assert 679 < p.precio_ref < 681
    assert p.cambio_aplicado != 1.0


def test_sin_tipo_de_cambio_se_descarta_en_vez_de_estimar():
    r = _preparar([_resultado(precio=2148639.0, moneda="COP")])
    assert r.aceptados == []
    assert "tipos de cambio" in r.descartados[0].motivo


# ------------------------------------------------------- señal de vida

def test_descartar_todo_no_es_lo_mismo_que_no_recibir_nada():
    """Una fuente que responde pero cuyos resultados se filtran no esta caida."""
    r = _preparar([_resultado(escalas=5)], filtros=Filtros(max_escalas=0))
    assert r.hubo_resultados is False
    assert r.descartados, "la fuente si respondio"


def test_las_etiquetas_llegan_al_precio():
    r = _preparar([_resultado(etiquetas={Etiqueta.BILLETES_SEPARADOS})])
    assert Etiqueta.BILLETES_SEPARADOS in r.aceptados[0].etiquetas
