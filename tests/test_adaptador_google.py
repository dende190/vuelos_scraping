"""Pruebas del adaptador de Google Flights, sin tocar la red."""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from vuelos.modelos import Filtros, Franja
from vuelos.proveedores.base import Consulta, ConsultaVentana, ErrorProveedor
from vuelos.proveedores.google import AdaptadorGoogle


@pytest.fixture
def consulta() -> Consulta:
    return Consulta(origen="BOG", destino="RDU", salida=date(2026, 11, 20),
                    regreso=date(2026, 12, 4), mercado="CO", moneda="USD")


def _adaptador(html: str = "", registro: list | None = None) -> AdaptadorGoogle:
    def transporte(params):
        if registro is not None:
            registro.append(params)
        return html
    return AdaptadorGoogle(transporte=transporte)


def _peticiones(consulta_o_ventana) -> list[dict]:
    """Los parámetros que el adaptador enviaría, sin importar la respuesta.

    El transporte devuelve HTML vacío, y ante eso el adaptador lanza
    `ErrorProveedor` a propósito: un HTML que no se puede analizar no debe
    confundirse con "no hay vuelos". Aquí solo interesa lo que se envió.
    """
    enviado: list = []
    adaptador = _adaptador(registro=enviado)
    metodo = (adaptador.buscar_ventana if isinstance(consulta_o_ventana, ConsultaVentana)
              else adaptador.buscar)
    try:
        metodo(consulta_o_ventana)
    except ErrorProveedor:
        pass
    return enviado


# ------------------------------------------------ el mercado va en la peticion

def test_la_peticion_lleva_el_pais(consulta):
    """El motivo de no usar get_flights: esa funcion no envia gl."""
    enviado = _peticiones(consulta)
    assert enviado[0]["gl"] == "CO"
    assert enviado[0]["curr"] == "USD"
    assert "tfs" in enviado[0]


def test_otro_mercado_viaja_en_la_peticion():
    otra = Consulta(origen="BOG", destino="RDU", salida=date(2026, 11, 20),
                    regreso=date(2026, 12, 4), mercado="US", moneda="USD")
    assert _peticiones(otra)[0]["gl"] == "US"


def test_cada_bloque_de_la_ventana_lleva_el_pais():
    ventana = ConsultaVentana(origen="BOG", destino="RDU",
                              ventana_ini=date(2027, 1, 1), ventana_fin=date(2027, 1, 10),
                              duracion_noches=3, mercado="CO", moneda="USD")
    enviado = _peticiones(ventana)
    assert enviado, "no se emitio ninguna peticion"
    assert all(p["gl"] == "CO" for p in enviado)


# ------------------------------------------------------- enlace de verificacion

def test_el_enlace_apunta_a_google_flights_con_el_mercado(consulta):
    enlace = _adaptador().enlace(consulta)
    partes = urlparse(enlace)
    parametros = parse_qs(partes.query)
    assert partes.netloc == "www.google.com"
    assert partes.path.startswith("/travel/flights")
    assert parametros["gl"] == ["CO"]
    assert parametros["curr"] == ["USD"]
    assert parametros["tfs"]


def test_el_enlace_cambia_con_las_fechas(consulta):
    otra = Consulta(origen="BOG", destino="RDU", salida=date(2027, 3, 1),
                    regreso=date(2027, 3, 15), mercado="CO", moneda="USD")
    adaptador = _adaptador()
    assert adaptador.enlace(consulta) != adaptador.enlace(otra)


# ------------------------------------------------------------ coste y filtros

def test_la_ventana_cuesta_una_peticion_por_bloque():
    ventana = ConsultaVentana(origen="BOG", destino="RDU",
                              ventana_ini=date(2027, 1, 20), ventana_fin=date(2027, 2, 16),
                              duracion_noches=12, mercado="CO", moneda="USD")
    assert _adaptador().peticiones_por_ventana(ventana) == 16
    assert len(_peticiones(ventana)) == 16


def test_pedir_maleta_cambia_la_peticion(consulta):
    """El equipaje no se lee de la respuesta; solo se puede pedir."""
    con_maleta = Consulta(origen="BOG", destino="RDU", salida=date(2026, 11, 20),
                          regreso=date(2026, 12, 4), mercado="CO", moneda="USD",
                          filtros=Filtros(requiere_maleta=True))
    assert _peticiones(consulta)[0]["tfs"] != _peticiones(con_maleta)[0]["tfs"]


def test_los_filtros_cambian_la_peticion(consulta):
    con_filtros = Consulta(
        origen="BOG", destino="RDU", salida=date(2026, 11, 20), regreso=date(2026, 12, 4),
        mercado="CO", moneda="USD",
        filtros=Filtros(max_escalas=1, max_escala_minutos=240, franja_horaria=Franja.MANANA,
                        aerolineas=("AV",)))
    assert _peticiones(consulta)[0]["tfs"] != _peticiones(con_filtros)[0]["tfs"]


# ------------------------------------------------------------------- errores

def test_html_ilegible_es_error_y_no_lista_vacia(consulta):
    """Lo contrario seria el fallo silencioso que este diseno quiere evitar.

    Si Google cambia el HTML y el adaptador devolviera [], el sistema lo
    interpretaria como "no hay vuelos baratos" y callaria para siempre.
    """
    adaptador = _adaptador("<html>no es lo que espera el analizador</html>")
    with pytest.raises(ErrorProveedor):
        adaptador.buscar(consulta)


def test_un_fallo_de_bloque_no_aborta_la_ventana():
    intentos = {"n": 0}

    def transporte(params):
        intentos["n"] += 1
        if intentos["n"] == 2:
            raise ErrorProveedor("bloque caido")
        return ""

    ventana = ConsultaVentana(origen="BOG", destino="RDU",
                              ventana_ini=date(2027, 1, 1), ventana_fin=date(2027, 1, 10),
                              duracion_noches=3, mercado="CO", moneda="USD")
    AdaptadorGoogle(transporte=transporte).buscar_ventana(ventana)
    assert intentos["n"] == len(ventana.bloques())
