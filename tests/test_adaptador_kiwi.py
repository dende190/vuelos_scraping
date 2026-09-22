"""Pruebas del adaptador de Kiwi, sobre la respuesta real guardada.

No tocan la red: usan `herramientas/referencia-respuesta-kiwi.json`, que es
una respuesta real capturada el 21-sep-2026 (tarea 1.5).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from vuelos.modelos import Etiqueta, Filtros, Franja
from vuelos.proveedores.base import (
    Consulta,
    ConsultaVentana,
    ErrorProveedor,
    LimiteDePeticiones,
    MercadoIncorrecto,
)
from vuelos.proveedores.kiwi import AdaptadorKiwi

REFERENCIA = Path(__file__).parent.parent / "herramientas" / "referencia-respuesta-kiwi.json"


@pytest.fixture
def respuesta_real() -> dict:
    return json.loads(REFERENCIA.read_text(encoding="utf-8"))["respuesta"]


@pytest.fixture
def consulta() -> Consulta:
    return Consulta(origen="BOG", destino="RDU", salida=date(2026, 11, 20),
                    regreso=date(2026, 12, 4), mercado="CO", moneda="USD")


def _adaptador(respuesta, registro: list | None = None) -> AdaptadorKiwi:
    def transporte(cuerpo):
        if registro is not None:
            registro.append(cuerpo)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta
    return AdaptadorKiwi(transporte=transporte)


# ------------------------------------------- mapeo de una respuesta real

def test_mapea_la_respuesta_real(respuesta_real, consulta):
    resultados = _adaptador(respuesta_real).buscar(consulta)
    assert resultados
    for r in resultados:
        assert r.precio > 0
        assert r.moneda == "USD"
        assert r.mercado == "CO"
        assert r.escalas >= 0
        assert r.aerolineas


def test_detecta_billetes_separados(respuesta_real, consulta):
    """En BOG-RDU los baratos de Kiwi salieron con isVirtualInterlining."""
    resultados = _adaptador(respuesta_real).buscar(consulta)
    assert any(Etiqueta.BILLETES_SEPARADOS in r.etiquetas for r in resultados)


def test_detecta_falta_de_equipaje_facturado(respuesta_real, consulta):
    resultados = _adaptador(respuesta_real).buscar(consulta)
    assert all(Etiqueta.SIN_EQUIPAJE_FACTURADO in r.etiquetas for r in resultados)


def test_trae_enlace_de_reserva_absoluto(respuesta_real, consulta):
    """La fuente da la ruta relativa; un enlace asi no se abre desde Telegram."""
    resultados = _adaptador(respuesta_real).buscar(consulta)
    assert all(r.enlace and r.enlace.startswith("https://www.kiwi.com/") for r in resultados)
    assert all(Etiqueta.NO_VERIFICABLE not in r.etiquetas for r in resultados)


def test_un_itinerario_sin_enlace_se_marca_no_verificable(consulta):
    sin_enlace = {"data": {"returnItineraries": {"__typename": "Itineraries", "itineraries": [
        {"price": {"amount": "700", "currency": {"code": "USD"}},
         "bagsInfo": {"includedCheckedBags": 1}, "travelHack": {},
         "outbound": {"sectorSegments": [{"segment": {
             "carrier": {"name": "Avianca"},
             "source": {"localTime": "2026-11-20T09:00:00"}}}]},
         "inbound": {"sectorSegments": [{"segment": {
             "carrier": {"name": "Avianca"},
             "source": {"localTime": "2026-12-04T09:00:00"}}}]},
         "bookingOptions": {"edges": []}}]}}}
    r = _adaptador(sin_enlace).buscar(consulta)[0]
    assert r.enlace is None
    assert Etiqueta.NO_VERIFICABLE in r.etiquetas


# ------------------------------------------------- mercado, moneda, filtros

def test_la_peticion_fija_mercado_moneda_e_idioma(respuesta_real, consulta):
    enviado: list = []
    _adaptador(respuesta_real, enviado).buscar(consulta)
    opciones = enviado[0]["variables"]["options"]
    assert opciones["market"] == "co"
    assert opciones["currency"] == "usd"
    assert opciones["locale"] == "es"


def test_se_excluyen_las_practicas_que_invalidan_el_billete(respuesta_real, consulta):
    enviado: list = []
    _adaptador(respuesta_real, enviado).buscar(consulta)
    filtro = enviado[0]["variables"]["filter"]
    assert filtro["enableThrowAwayTicketing"] is False
    assert filtro["enableTrueHiddenCity"] is False


def test_una_moneda_distinta_de_la_pedida_se_rechaza(respuesta_real):
    otra = Consulta(origen="BOG", destino="RDU", salida=date(2026, 11, 20),
                    regreso=date(2026, 12, 4), mercado="CO", moneda="EUR")
    with pytest.raises(MercadoIncorrecto, match="USD habiendo pedido EUR"):
        _adaptador(respuesta_real).buscar(otra)


def test_los_filtros_viajan_en_la_peticion(respuesta_real):
    consulta = Consulta(
        origen="BOG", destino="RDU", salida=date(2026, 11, 20), regreso=date(2026, 12, 4),
        mercado="CO", moneda="USD",
        filtros=Filtros(max_escalas=1, max_escala_minutos=240, requiere_maleta=True,
                        franja_horaria=Franja.MANANA, aerolineas=("AV", "CM")))
    enviado: list = []
    _adaptador(respuesta_real, enviado).buscar(consulta)
    filtro = enviado[0]["variables"]["filter"]
    pasajeros = enviado[0]["variables"]["search"]["passengers"]
    assert filtro["maxStopsCount"] == 1
    assert filtro["stopoverTime"] == {"start": 0, "end": 240 * 60}
    assert filtro["showNoCheckedBags"] is False
    assert filtro["carriers"] == ["AV", "CM"]
    assert "outbound" in filtro
    assert pasajeros["adultsHoldBags"] == 1


# ------------------------------------------------------- ventana flexible

def test_la_ventana_cuesta_una_sola_peticion(respuesta_real):
    ventana = ConsultaVentana(origen="BOG", destino="RDU",
                              ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 16),
                              duracion_noches=12, mercado="CO", moneda="USD")
    enviado: list = []
    adaptador = _adaptador(respuesta_real, enviado)
    assert adaptador.peticiones_por_ventana(ventana) == 1
    adaptador.buscar_ventana(ventana)
    assert len(enviado) == 1


def test_la_ventana_usa_nightsCount_y_un_rango_de_salida(respuesta_real):
    ventana = ConsultaVentana(origen="BOG", destino="RDU",
                              ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 16),
                              duracion_noches=12, mercado="CO", moneda="USD")
    enviado: list = []
    _adaptador(respuesta_real, enviado).buscar_ventana(ventana)
    itinerario = enviado[0]["variables"]["search"]["itinerary"]
    assert itinerario["nightsCount"] == {"start": 12, "end": 12}
    assert itinerario["outboundDepartureDate"]["start"].startswith("2027-01-20")
    assert itinerario["outboundDepartureDate"]["end"].startswith("2027-02-16")
    assert "inboundDepartureDate" not in itinerario


# ------------------------------------------------------------------ errores

def test_errores_de_graphql_se_reportan(consulta):
    adaptador = _adaptador({"errors": [{"message": "campo desconocido"}]})
    with pytest.raises(ErrorProveedor, match="campo desconocido"):
        adaptador.buscar(consulta)


def test_el_limite_de_peticiones_se_propaga(consulta):
    adaptador = _adaptador(LimiteDePeticiones("429"))
    with pytest.raises(LimiteDePeticiones):
        adaptador.buscar(consulta)


def test_respuesta_vacia_no_rompe(consulta):
    adaptador = _adaptador({"data": {"returnItineraries": {"__typename": "Itineraries",
                                                           "itineraries": []}}})
    assert adaptador.buscar(consulta) == []
